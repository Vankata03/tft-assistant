import {useEffect,useRef,useState} from 'react'
import type {RequestReview} from '../../../shared/messages'

type Document=Record<string,unknown>
type Path=(string|number)[]
export type ReviewRequest=(operation:RequestReview['operation'],arguments_:Partial<Omit<RequestReview,'v'|'type'|'request_id'>>)=>Promise<Document>
const object=(value:unknown):Document=>typeof value==='object'&&value!==null&&!Array.isArray(value)?value as Document:{}
const reason=(value:unknown)=>String(value??'not recorded').replaceAll('_',' ')
const estimate=(row:Document)=>typeof row.expected_placement==='number'?`${row.expected_placement.toFixed(2)}${typeof row.standard_error==='number'?` ± ${row.standard_error.toFixed(2)}`:''}`:'Unavailable'
export function RecordedChoice({label,value,unavailable}:{label:string;value:unknown;unavailable?:unknown}):React.JSX.Element{
 const choice=object(value)
 return <article className="review-choice"><h4>{label}</h4>{typeof choice.option_id==='string'?<><strong>{choice.option_id}</strong><p>{reason(choice.action)}</p><p>Estimated placement {estimate(choice)}</p></>:<p>Unavailable · {reason(unavailable)}</p>}</article>
}
export function ReviewMoment({moment,request,onDebug}:{moment:Document;request:ReviewRequest;onDebug(path:Path):void}):React.JSX.Element{
 const [options,setOptions]=useState<Document[]>([]),[next,setNext]=useState<number|null>(null),[optionPath,setOptionPath]=useState<Path|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[comparison,setComparison]=useState<Document|null>(null)
 const [image,setImage]=useState<string|null>(null)
 const mediaGeneration=useRef(0),mediaUrl=useRef<string|null>(null)
 const generation=useRef(0)
 useEffect(()=>()=>{generation.current++;mediaGeneration.current++;if(mediaUrl.current)URL.revokeObjectURL(mediaUrl.current)},[])
 const load=async()=>{
  const token=++generation.current;setBusy(true);setError(null)
  try{
   let path=optionPath
   if(!path){
    if(!Array.isArray(moment.moment_path))throw new Error('Authenticated moment location unavailable')
    const response=await request('page',{path:[...moment.moment_path,'evidence_path'],limit:64})
    if(response.next_cursor!==null)throw new Error('Moment evidence path exceeds supported depth')
    const members=(Array.isArray(response.items)?response.items:[]).map(item=>object(item).value)
    if(!members.length||!members.every(value=>typeof value==='string'||typeof value==='number'&&Number.isSafeInteger(value)))throw new Error('Authenticated option location unavailable')
    path=[...members as Path,'options']
   }
   const page=await request('page',{path,cursor:next??0,limit:8})
   const rows:Document[]=[]
   // Sequential bounded requests avoid saturating the core's owned request queue.
   for(const member of Array.isArray(page.items)?page.items:[]){
    const row=object(member)
    if(!Array.isArray(row.path))throw new Error('Scored option membership unavailable')
    const header=row.reference?await request('page',{path:row.path as Path,limit:32}):null
    const value=header?Object.fromEntries((Array.isArray(header.items)?header.items:[]).map(item=>object(item)).filter(item=>!item.reference&&Array.isArray(item.path)).map(item=>[(item.path as Path).at(-1),item.value])):object(row.value)
    if(typeof value.option_id==='string')rows.push(value)
    if(token!==generation.current)return
   }
   if(token!==generation.current)return
   setOptionPath(path);setOptions(previous=>[...previous,...rows]);setNext(typeof page.next_cursor==='number'?page.next_cursor:null)
  }catch(caught){if(token===generation.current)setError(String(caught))}finally{if(token===generation.current)setBusy(false)}
 }
 const loadKeyframe=async()=>{
  const name=object(moment.keyframe).media_name
  if(typeof name!=='string'||!/^media\/[0-9a-f]{32}\.webp$/.test(name)){setError('Logged keyframe reference unavailable');return}
  const token=++mediaGeneration.current;setBusy(true);setError(null)
  try{
   const chunks:Uint8Array<ArrayBuffer>[]=[];let cursor=0,total:number|null=null
   do{
    const chunk=await request('media',{name,cursor,limit:49152})
    if(token!==mediaGeneration.current)return
    if(chunk.name!==name||chunk.offset!==cursor||chunk.content_type!=='image/webp'||typeof chunk.total_bytes!=='number'||!Number.isSafeInteger(chunk.total_bytes)||chunk.total_bytes<1||chunk.total_bytes>32*1024*1024||typeof chunk.base64!=='string')throw new Error('Logged image exceeds the viewer budget or has invalid chunk metadata')
    if(total!==null&&total!==chunk.total_bytes)throw new Error('Logged image changed during access')
    total=chunk.total_bytes
    const bytes=Uint8Array.from(atob(chunk.base64),char=>char.charCodeAt(0))
    if(!bytes.length||bytes.length>49152||cursor+bytes.length>total)throw new Error('Invalid logged image bytes')
    chunks.push(bytes);cursor+=bytes.length
    if(chunk.next_cursor!==null&&chunk.next_cursor!==cursor)throw new Error('Invalid logged image continuation')
    if(chunk.next_cursor===null){if(cursor!==total)throw new Error('Incomplete logged image');break}
   }while(cursor<total!)
   const url=URL.createObjectURL(new Blob(chunks,{type:'image/webp'}))
   if(mediaUrl.current)URL.revokeObjectURL(mediaUrl.current)
   mediaUrl.current=url;setImage(url)
  }catch(caught){if(token===mediaGeneration.current)setError(String(caught))}finally{if(token===mediaGeneration.current)setBusy(false)}
 }
 const compare=async(option_id:string)=>{
  const token=++generation.current;setBusy(true);setComparison(null);setError(null)
  try{const value=await request('what_if',{moment_id:String(moment.moment_id),option_id});if(token===generation.current)setComparison(value)}catch(caught){if(token===generation.current)setError(String(caught))}finally{if(token===generation.current)setBusy(false)}
 }
 return <section className="panel review-scored-moment"><h3>{String(moment.round_id)} · {String(moment.category)} scored moment</h3>
  <div className="review-choice-pair"><RecordedChoice label="Engine choice" value={moment.engine_choice} unavailable={object(moment.unavailable).engine_choice}/><RecordedChoice label="Player choice" value={moment.player_choice} unavailable={object(moment.unavailable).player_choice}/></div>
  <p className="subtle">These are historical estimates. Selecting an option reads its recorded score and does not rerun the game.</p>
  {!options.length?<button disabled={busy} onClick={()=>void load()}>Load scored options</button>:<><label>Already scored option <select disabled={busy} onChange={event=>void compare(event.target.value)}>{options.map(row=><option key={String(row.option_id)} value={String(row.option_id)}>{String(row.option_id)} · {reason(row.action)} · {estimate(row)}</option>)}</select></label>{next!==null?<button disabled={busy} onClick={()=>void load()}>More scored options</button>:null}</>}
  {busy?<p role="status">Loading protected scores…</p>:null}{error?<p role="alert">{error}</p>:null}
  {comparison?<p>Already scored · {String(comparison.option_id)} · estimated placement {estimate(comparison)}</p>:null}
  {typeof object(moment.keyframe).media_name==='string'?<><button disabled={busy} onClick={()=>void loadKeyframe()}>View logged keyframe</button>{image?<figure className="review-keyframe"><img src={image} alt={`Logged capture for ${String(moment.round_id)} decision`}/><figcaption>{String(object(moment.keyframe).timestamp??'Timestamp unavailable')} · {reason(object(moment.keyframe).logged_reason)}</figcaption></figure>:null}</>:<p>Keyframe unavailable · {reason(object(moment.keyframe).reason)}</p>}
  {Array.isArray(moment.moment_path)?<button onClick={()=>onDebug(moment.moment_path as Path)}>Debug recorded moment</button>:null}
 </section>
}
