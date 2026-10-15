import {expect,it} from 'vitest'
import {projectOverlayGeometry} from '../src/main/geometry'
import type {SurfaceGeometryState} from '../src/shared/messages'

const now=Date.parse('2026-10-13T09:00:00Z')
const source:SurfaceGeometryState={v:1,type:'surface_geometry',mode:'live',status:'recorded native boundary',geometry:{
 window_id:'positive-window',coordinate_space:'physical_pixels',client_bounds:{x:-1920,y:0,width:1920,height:1080},read_at:'2026-10-13T09:00:00Z',source:'Win32-client-rectangle',layout_read_at:'2026-10-13T09:00:00Z',layout_source_sha256:'b'.repeat(64),window_mode:'borderless',ui_scale:1,
 profile_sha256:'a'.repeat(64),calibration:{client_size:[1920,1080],ui_scale:1}},
 anchors:[{kind:'shop',index:0,x:.2,y:.8,width:.1,height:.05}]}
// Recorded external screen API: left display 150%, right display 100%.
const screen={getAllDisplays:()=>[{id:1,bounds:{x:-1280,y:0,width:1280,height:720}},{id:2,bounds:{x:0,y:0,width:1920,height:1080}}],
 dipToScreenRect:(_window:null,r:{x:number;y:number;width:number;height:number})=>r.x<0?{x:Math.round(r.x*1.5),y:Math.round(r.y*1.5),width:Math.round(r.width*1.5),height:Math.round(r.height*1.5)}:r,
 screenToDipRect:(_window:null,r:{x:number;y:number;width:number;height:number})=>r.x<0?{x:Math.round(r.x/1.5),y:Math.round(r.y/1.5),width:Math.round(r.width/1.5),height:Math.round(r.height/1.5)}:r}

it('uses the observed negative origin and native per-monitor DIP conversion',()=>{
 const projected=projectOverlayGeometry(source,screen,now,'win32')
 expect(projected.bounds).toEqual({x:-1280,y:0,width:1280,height:720})
 expect(projected.reason).toBeNull()
 expect(projected.anchors).toEqual(source.anchors)
})

it('hides stale, fullscreen, spanning and uncalibrated surfaces without an origin fallback',()=>{
 expect(projectOverlayGeometry(source,screen,now+2100,'win32').bounds).toBeNull()
 expect(projectOverlayGeometry({...source,geometry:{...source.geometry!,layout_read_at:'2026-10-13T08:00:00Z'}},screen,now,'win32').bounds).toBeNull()
 expect(projectOverlayGeometry({...source,mode:'silent'},screen,now,'win32').bounds).toBeNull()
 expect(projectOverlayGeometry({...source,geometry:{...source.geometry!,window_mode:'exclusive_fullscreen'}},screen,now,'win32').bounds).toBeNull()
 const spanning={...source,geometry:{...source.geometry!,client_bounds:{x:-500,y:0,width:1920,height:1080}}}
 expect(projectOverlayGeometry(spanning,screen,now,'win32').bounds).toBeNull()
 const wrongScale={...source,geometry:{...source.geometry!,ui_scale:1.2}}
 expect(projectOverlayGeometry(wrongScale,screen,now,'win32').bounds).toBeNull()
 expect(projectOverlayGeometry(source,screen,now,'darwin').bounds).toBeNull()
})
