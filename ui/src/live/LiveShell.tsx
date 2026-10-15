import {useEffect,useRef,useState} from 'react'
import type {ShellState} from '../shared/state'
import {LiveCockpit} from './LiveCockpit'
import {LiveOverlay} from './LiveOverlay'
import {EvidenceDrawer} from './EvidenceDrawer'
import {StageVoicePlayer,localVoice} from '../renderer/src/voice'
import {liveVoiceCue} from './voiceRules'
import './live.css'

export default function LiveShell({state,surface}:{state:ShellState;surface:'cockpit'|'overlay'|'voice'}):React.JSX.Element|null{
 const [detail,setDetail]=useState<readonly(string|number)[]|null>(null)
 const [now,setNow]=useState(Date.now)
 const view=state.core==='running'&&state.mode==='live'&&state.live?.mode==='live'?state.live:null
 const latest=useRef(view);latest.current=view
 const player=useRef<StageVoicePlayer|null>(null)
 if(player.current===null)player.current=new StageVoicePlayer(localVoice())
 const cue=surface==='voice'?liveVoiceCue(view,now):null
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),100);return()=>clearInterval(timer)},[])
 useEffect(()=>{setDetail(null)},[view?.revision])
 useEffect(()=>{
  if(!cue){player.current?.cancel();return}
  const start=()=>{
   const current=latest.current
   const actual=liveVoiceCue(current,Date.now())
   if(!current?.content||!current.revision||actual?.id!==cue.id)return
   window.coach?.liveShown({game_id:current.content.game_id,revision:current.revision,decision_id:actual.row.decision_id,option_id:actual.row.option_id,surface:'voice',timestamp:new Date().toISOString()})
  }
  player.current?.play(cue,start)
  const retry=()=>player.current?.play(cue,start)
  window.speechSynthesis?.addEventListener('voiceschanged',retry)
  return()=>window.speechSynthesis?.removeEventListener('voiceschanged',retry)
 },[cue?.id])
 useEffect(()=>()=>player.current?.cancel(),[])
 if(surface==='voice')return null
 const pin=(line:Parameters<React.ComponentProps<typeof LiveCockpit>['onPin']>[0])=>{
  if(view?.content&&view.revision)window.coach?.pinLine({game_id:view.content.game_id,revision:view.revision,comp_id:line?.comp_id??null,line_id:line?.line_id??null,seed:line?.seed??null})
 }
 if(surface==='overlay')return <LiveOverlay state={state} onPin={pin} now={now}/>
 return <><LiveCockpit state={state} onMode={mode=>window.coach?.setMode(mode)} onPin={pin} onDetail={setDetail}/>{detail&&view?.content?<EvidenceDrawer key={view.revision} view={view} path={detail} onClose={()=>setDetail(null)}/>:null}</>
}
