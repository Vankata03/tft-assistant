type Path=(string|number)[]

/** Serves a synthetic report in the core's bounded page format; shapes follow tft_review.sections.surface_sections. */
export function pager(document:Record<string,unknown>,calls:Path[]=[]){
 return async(_operation:'page',args:{path:Path;cursor:number;limit:number}):Promise<Record<string,unknown>>=>{
  calls.push(args.path)
  let value:unknown=document
  for(const key of args.path)value=(value as Record<string|number,unknown>)[key]
  const entries=Object.entries(value as object)
  const slice=entries.slice(args.cursor,args.cursor+args.limit)
  const next=args.cursor+slice.length
  return {kind:Array.isArray(value)?'array':'object',path:args.path,
   items:slice.map(([key,child])=>({path:[...args.path,Array.isArray(value)?Number(key):key],...(typeof child==='object'&&child!==null?{reference:true}:{value:child})})),
   next_cursor:next<entries.length?next:null}
 }
}
