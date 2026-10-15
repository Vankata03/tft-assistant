/** Local speech boundary; acknowledgement comes from playback start, never queue acceptance. */
export interface VoiceOutput {
  speak(text: string, started: () => void, failed: () => void): boolean
  cancel(): void
}

export class StageVoicePlayer {
  private readonly spoken = new Set<string>()
  private pending: string | null = null
  private generation = 0
  unavailable = false

  constructor(private readonly output: VoiceOutput) {}

  play(cue: { id: string; text: string } | null, started?: () => void, failed?: () => void): boolean {
    if (!cue || this.spoken.has(cue.id) || this.pending === cue.id) return false
    if (this.pending !== null) this.cancel()
    const generation = this.generation
    this.pending = cue.id
    const accepted = this.output.speak(cue.text, () => {
      if (generation !== this.generation || this.pending !== cue.id) return
      this.spoken.add(cue.id)
      this.pending = null
      this.unavailable = false
      started?.()
    }, () => {
      if (generation !== this.generation) return
      this.pending = null
      this.unavailable = true
      failed?.()
    })
    if (!accepted) {
      this.pending = null
      this.unavailable = true
    }
    return accepted
  }

  cancel(): void {
    this.generation += 1
    this.pending = null
    this.output.cancel()
  }
}

export function localVoice(): VoiceOutput {
  return {
    speak(text, started, failed) {
      if (!('speechSynthesis' in window)) return false
      const voice = window.speechSynthesis.getVoices()
        .find((voice) => voice.localService && voice.lang.startsWith('en'))
      if (!voice) return false
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.voice = voice
      utterance.onstart = started
      utterance.onerror = failed
      window.speechSynthesis.speak(utterance)
      return true
    },
    cancel() {
      if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    },
  }
}
