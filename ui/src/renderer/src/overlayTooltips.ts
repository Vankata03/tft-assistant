import {useEffect} from 'react'

/** Pointer dwell before an advice tag reveals its reason. */
export const TOOLTIP_DWELL_MS=400
const TAG='.overlay-tag'
const OPEN='data-tooltip'

/**
 * Hover-only tooltip path for the click-through overlay.
 *
 * Advice tags keep `pointer-events: none`, so the native window stays ignored and clicks
 * reach the game. Electron's `setIgnoreMouseEvents(true, {forward: true})` still delivers
 * mouse movement to the document; tags under the pointer are found by their rectangles,
 * and a tag that keeps the pointer for the dwell time is marked open. Nothing here
 * requests window input.
 */
export function useOverlayTooltips(enabled:boolean):void{
 useEffect(()=>{
  if(!enabled)return
  let pointer:{x:number;y:number}|null=null
  let candidate:Element|null=null
  let open:Element|null=null
  let timer:ReturnType<typeof setTimeout>|undefined
  const hit=():Element|null=>{
   if(!pointer)return null
   const tags=[...document.querySelectorAll(TAG)]
   for(let index=tags.length-1;index>=0;index--){
    const box=tags[index]!.getBoundingClientRect()
    if(pointer.x>=box.left&&pointer.x<box.right&&pointer.y>=box.top&&pointer.y<box.bottom)return tags[index]!
   }
   return null
  }
  const close=()=>{open?.removeAttribute(OPEN);open=null}
  const evaluate=()=>{
   const tag=hit()
   if(tag===candidate)return
   clearTimeout(timer)
   if(open!==tag)close()
   candidate=tag
   if(tag&&open!==tag)timer=setTimeout(()=>{if(candidate!==tag||!tag.isConnected)return;open=tag;tag.setAttribute(OPEN,'open')},TOOLTIP_DWELL_MS)
  }
  const onMove=(event:MouseEvent)=>{pointer={x:event.clientX,y:event.clientY};evaluate()}
  const onOut=(event:MouseEvent)=>{if(event.relatedTarget===null){pointer=null;evaluate()}}
  const observer=typeof MutationObserver==='undefined'?null:new MutationObserver(evaluate)
  // Tags can move without being replaced (React reuses keyed nodes and only rewrites their
  // style), so position changes re-check the still pointer as well as added or removed tags.
  observer?.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['style','class']})
  document.addEventListener('mousemove',onMove,true)
  document.addEventListener('mouseout',onOut,true)
  window.addEventListener('resize',evaluate)
  return()=>{
   observer?.disconnect()
   window.removeEventListener('resize',evaluate)
   document.removeEventListener('mousemove',onMove,true)
   document.removeEventListener('mouseout',onOut,true)
   clearTimeout(timer)
   close()
  }
 },[enabled])
}
