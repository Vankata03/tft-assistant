import type {LiveState,LiveAdviceDisplay} from '../shared/messages'
export interface LiveVoiceCue {id:string;text:string;row:LiveAdviceDisplay}
export function liveVoiceCue(view:LiveState|null|undefined,now:number):LiveVoiceCue|null{
 if(view?.mode!=='live'||!view.content||['combat','end','unknown'].includes(view.observed_phase??view.content.phase))return null
 const content=view.content,minimum=content.confidence_medium_min
 if(minimum===null)return null
 for(const row of content.advice){
  if(row.confidence<minimum||row.payload.paused||view.invalidated?.[row.decision_id]||(row.valid_until!==null&&Date.parse(row.valid_until)<now))continue
  let text:string|null=null,id=row.decision_id
  if(row.domain==='augment'&&row.payload.operation==='pick')text=row.action
  else if(row.domain==='carousel'&&row.urgency!=='information')text=`Carousel: ${row.action}`
  else if(row.domain==='pivot')text=row.action
  else if(row.domain==='positioning'&&row.payload.voice===true){
   const on=Array.isArray(row.payload.turns_on)?row.payload.turns_on:[]
   const calls=on.flatMap(tag=>tag==='aoe'?['Anti-AoE on']:tag==='backline_access'?['Anti-dive on']:[])
   const scout=content.opponents.filter(opponent=>opponent.scout_due)
   if(calls.length)text=[...calls,...scout.map(opponent=>`scout ${String(opponent.name)}`)].join('. ')
  }else if(row.domain==='econ'&&content.phase==='roll_down'&&typeof row.payload.gold_floor==='number'){
   text=`Roll down to ${row.payload.gold_floor}`;id=`${content.game_id}:${content.round_id}:roll-start:${row.payload.gold_floor}`
  }
  if(text)return{id,text,row}
 }
 return null
}
