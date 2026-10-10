/** Local text-to-speech boundary. A Piper adapter can implement the same interface. */
export interface VoiceOutput {
  speak(text: string): boolean
  cancel(): void
}

export class StageVoicePlayer {
  private readonly spoken = new Set<string>()
  unavailable = false

  constructor(private readonly output: VoiceOutput) {}

  play(cue: { id: string; text: string } | null): boolean {
    if (!cue || this.spoken.has(cue.id)) return false
    this.spoken.add(cue.id)
    this.unavailable = !this.output.speak(cue.text)
    return !this.unavailable
  }

  cancel(): void {
    this.output.cancel()
  }
}

export function localVoice(): VoiceOutput {
  return {
    speak(text) {
      if (!('speechSynthesis' in window)) return false
      const voice = window.speechSynthesis
        .getVoices()
        .find((voice) => voice.localService && voice.lang.startsWith('en'))
      if (!voice) return false
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.voice = voice
      window.speechSynthesis.speak(utterance)
      return true
    },
    cancel() {
      if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    },
  }
}
