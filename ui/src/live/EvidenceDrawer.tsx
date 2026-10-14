import {useEffect,useState} from 'react'
import type {EvidencePage,LiveState} from '../shared/messages'

type Path=readonly(string|number)[]
export function EvidenceDrawer({view,path,onClose}:{view:LiveState;path:Path;onClose:()=>void}):React.JSX.Element{
 const [location,setLocation]=useState<Path>(path)
 const [cursor,setCursor]=useState(0)
 const [response,setResponse]=useState<EvidencePage|null>(null)
 const [error,setError]=useState<string|null>(null)
 useEffect(()=>{
  let active=true
  setResponse(null);setError(null)
  if(!view.content||!view.revision){setError('Live evidence unavailable');return}
  void window.coach.evidencePage({game_id:view.content.game_id,revision:view.revision,path:[...location],cursor,limit:32})
   .then(next=>{if(active)setResponse(next)}).catch((error:unknown)=>{if(active)setError(error instanceof Error?error.message:String(error))})
  return()=>{active=false}
 },[view.revision,location,cursor])
 const page=response?.page as {items?:{path?:(string|number)[];reference?:boolean;value?:unknown;offset?:number}[];next_cursor?:number|null;kind?:string}|undefined
 return <section className="evidence-drawer panel" aria-label="Engine evidence">
  <header><h2>Recorded Engine evidence</h2><button onClick={onClose}>Close evidence</button></header>
  <p className="subtle">{location.join(' / ')||'Evaluation'} · original scores and paired distributions</p>
  {location.length?<button onClick={()=>{setLocation(location.slice(0,-1));setCursor(0)}}>Parent</button>:null}
  {error?<p role="alert">{error}</p>:!page?<p role="status">Loading authenticated page…</p>:<>
   <ol>{page.items?.map((item,index)=><li key={`${cursor}:${index}`}><strong>{item.path?.at(-1)??item.offset??index}</strong>{item.reference&&item.path?<button onClick={()=>{setLocation(item.path!);setCursor(0)}}>Open {item.path.at(-1)}</button>:<pre>{typeof item.value==='string'?item.value:JSON.stringify(item.value,null,2)}</pre>}</li>)}</ol>
   <div className="page-controls"><button disabled={cursor===0} onClick={()=>setCursor(Math.max(0,cursor-32))}>Previous page</button><button disabled={page.next_cursor===null||page.next_cursor===undefined} onClick={()=>setCursor(page.next_cursor!)}>Next page</button></div>
  </>}
 </section>
}
