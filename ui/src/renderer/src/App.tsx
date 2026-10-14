import { lazy,Suspense,useEffect, useRef, useState } from 'react'
import { INITIAL_STATE, describeCore, type ShellState } from '../../shared/state'
import {ReviewPanel} from './review/ReviewPanel'
import {ReviewReadyNotice} from './review/ReviewReadyNotice'
import { Cockpit } from './Cockpit'
import { BaselineOverlay } from './BaselineOverlay'
import { localVoice, StageVoicePlayer } from './voice'
import './cockpit.css'

export { SessionModeSelector } from './ModeSelector'

const LiveShell=typeof __LIVE_ENABLED__!=='undefined'&&__LIVE_ENABLED__?lazy(()=>import('../../live/LiveShell')):null
const isVoice=typeof location!=='undefined'&&new URLSearchParams(location.search).get('surface')==='voice'

const isOverlay =
  typeof location !== 'undefined' &&
  new URLSearchParams(location.search).get('surface') === 'overlay'
if (isOverlay) document.documentElement.classList.add('overlay-page')

export function App(): React.JSX.Element|null {
  const [state, setState] = useState<ShellState>(INITIAL_STATE)
  const [voiceUnavailable, setVoiceUnavailable] = useState(false)
  const [reviewOpen,setReviewOpen]=useState(false)
  const reviewReplacesCockpit=reviewOpen&&!['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow?.phase??'')
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
    isVoice &&
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
      voice.current?.play(cue, () =>
        window.coach?.reportShown('voice', cue.id, new Date().toISOString()),
        () => setVoiceUnavailable(true),
      )
      setVoiceUnavailable(voice.current?.unavailable ?? false)
    }, 0)
    return () => clearTimeout(timer)
  }, [cue?.id])

  if(isOverlay)return <>{state.mode==='live'&&LiveShell?<Suspense fallback={null}><LiveShell state={state} surface="overlay"/></Suspense>:<BaselineOverlay state={state}/>}<ReviewReadyNotice state={state} overlay/></>
  if(!isOverlay&&!isVoice&&reviewReplacesCockpit)return <><header className="app-header"><h1>TFT Assistant</h1><span className="connection">{describeCore(state.core)}</span><span>{state.baseline?.status??'Finished-game review'}</span></header><ReviewReadyNotice state={state}/><ReviewPanel state={state} onOpenChange={setReviewOpen}/></>
  if(state.mode==='live'&&LiveShell)return <><Suspense fallback={isVoice||isOverlay?null:<p role="status">Loading Live surfaces…</p>}><LiveShell state={state} surface={isVoice?'voice':isOverlay?'overlay':'cockpit'}/></Suspense>{!isVoice&&!isOverlay?<><ReviewReadyNotice state={state}/><ReviewPanel state={state} onOpenChange={setReviewOpen}/></>:null}</>
  if(isVoice)return null
  return (
    <>
      <Cockpit
        state={state}
        onMode={(mode) => window.coach?.setMode(mode)}
        onSelectGuide={(id) => window.coach?.selectGuide(id)}
      />
      <ReviewReadyNotice state={state}/><ReviewPanel state={state} onOpenChange={setReviewOpen}/>
      {voiceUnavailable && state.mode === 'baseline' ? (
        <p className="status-banner" role="status">
          Stage voice unavailable · install a local English voice.
        </p>
      ) : null}
    </>
  )
}
