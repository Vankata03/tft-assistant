import { useEffect, useRef, useState } from 'react'
import { INITIAL_STATE, type ShellState } from '../../shared/state'
import { Cockpit } from './Cockpit'
import { BaselineOverlay } from './BaselineOverlay'
import { localVoice, StageVoicePlayer } from './voice'
import './cockpit.css'

export { SessionModeSelector } from './ModeSelector'

const isOverlay =
  typeof location !== 'undefined' &&
  new URLSearchParams(location.search).get('surface') === 'overlay'
if (isOverlay) document.documentElement.classList.add('overlay-page')

export function App(): React.JSX.Element {
  const [state, setState] = useState<ShellState>(INITIAL_STATE)
  const [voiceUnavailable, setVoiceUnavailable] = useState(false)
  const voice = useRef<StageVoicePlayer | null>(null)
  if (voice.current === null) voice.current = new StageVoicePlayer(localVoice())

  useEffect(() => {
    if (!window.coach) {
      setState({
        ...INITIAL_STATE,
        core: 'stopped',
        error: 'Electron connection unavailable.',
      })
      return
    }
    let received = false
    let active = true
    const unsubscribe = window.coach.onState((next) => {
      received = true
      setState(next)
    })
    void window.coach.getState().then((next) => {
      if (active && !received) setState(next)
    })
    return () => {
      active = false
      unsubscribe()
    }
  }, [])

  const voiceEnabled =
    !isOverlay &&
    state.core === 'running' &&
    state.mode === 'baseline' &&
    state.baseline?.mode === 'baseline'
  const cue = voiceEnabled ? (state.baseline?.voice ?? null) : null
  useEffect(() => {
    if (!voiceEnabled) voice.current?.cancel()
    return () => voice.current?.cancel()
  }, [voiceEnabled])
  useEffect(() => {
    if (!cue) return
    const timer = setTimeout(() => {
      if (voice.current?.play(cue))
        window.coach?.reportShown('voice', cue.id, new Date().toISOString())
      setVoiceUnavailable(voice.current?.unavailable ?? false)
    }, 0)
    return () => clearTimeout(timer)
  }, [cue?.id])

  if (isOverlay) return <BaselineOverlay state={state} />
  return (
    <>
      <Cockpit
        state={state}
        onMode={(mode) => window.coach?.setMode(mode)}
        onSelectGuide={(id) => window.coach?.selectGuide(id)}
      />
      {voiceUnavailable && state.mode === 'baseline' ? (
        <p className="status-banner" role="status">
          Stage voice unavailable · install a local English voice.
        </p>
      ) : null}
    </>
  )
}
