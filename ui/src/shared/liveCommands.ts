import type {LiveState,RequestEvidencePage,LiveSurfaceShown,LivePreviewShown,PinLine} from './messages'

export type LiveCommand = Omit<LivePreviewShown,'v'|'type'> | Omit<RequestEvidencePage,'v'|'type'|'request_id'> | Omit<LiveSurfaceShown,'v'|'type'> | Omit<PinLine,'v'|'type'>
export function currentLiveMember(view:LiveState|null|undefined,input:unknown):input is LiveCommand {
 if(!view?.content||view.mode!=='live'||!view.revision||typeof input!=='object'||input===null)return false
 const row=input as Record<string,unknown>
 return row.game_id===view.content.game_id&&row.revision===view.revision
}
export function validEvidencePath(value:unknown):value is (string|number)[]{
 return Array.isArray(value)&&value.length<=64&&value.every(part=>typeof part==='string'?part.length<=500:typeof part==='number'&&Number.isSafeInteger(part)&&part>=0)
}
