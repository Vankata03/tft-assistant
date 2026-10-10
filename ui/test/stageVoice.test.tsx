import { expect, it } from 'vitest'
import { StageVoicePlayer } from '../src/renderer/src/voice'

it('stage voice plays once, survives ordinary capture updates and cancels on suppression', () => {
  const spoken: string[] = []
  let cancellations = 0
  const player = new StageVoicePlayer({
    speak(text) {
      spoken.push(text)
      return true
    },
    cancel() {
      cancellations += 1
    },
  })
  const cue = { id: 'game:stage:3', text: 'Fixture Guide stage step.' }
  expect(player.play(cue)).toBe(true)
  expect(player.play(cue)).toBe(false)
  expect(player.play(null)).toBe(false)
  expect(spoken).toEqual([cue.text])
  expect(cancellations).toBe(0)
  player.cancel()
  expect(cancellations).toBe(1)
  expect(player.play(cue)).toBe(false)
})
