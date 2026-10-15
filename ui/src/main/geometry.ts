import type {LiveSurfaceAnchor,OverlayBounds,SurfaceGeometryState} from '../shared/messages'

export interface NativeScreenGeometry {
 getAllDisplays():readonly {id:number;bounds:OverlayBounds}[]
 screenToDipRect(window:null,rectangle:OverlayBounds):OverlayBounds
 dipToScreenRect(window:null,rectangle:OverlayBounds):OverlayBounds
}
export interface OverlayGeometryProjection {
 bounds:OverlayBounds|null
 anchors:readonly LiveSurfaceAnchor[]
 reason:string|null
 displayId:number|null
}
const unavailable=(reason:string):OverlayGeometryProjection=>({bounds:null,anchors:[],reason,displayId:null})
const contains=(outer:OverlayBounds,inner:OverlayBounds):boolean=>inner.x>=outer.x&&inner.y>=outer.y&&inner.x+inner.width<=outer.x+outer.width&&inner.y+inner.height<=outer.y+outer.height
const finiteRectangle=(r:OverlayBounds):boolean=>[r.x,r.y,r.width,r.height].every(Number.isFinite)&&r.width>0&&r.height>0

/** Native Electron conversion is authoritative. A spanning mixed-DPI client stays off. */
export function projectOverlayGeometry(source:SurfaceGeometryState|null|undefined,screen:NativeScreenGeometry,now:number,platform:string):OverlayGeometryProjection {
 if(platform!=='win32')return unavailable('Native Windows desktop geometry is unavailable on this platform')
 if(!source||source.mode==='silent'||!source.geometry||!source.anchors.length)return unavailable('Checked game window or reviewed anchors unavailable')
 const geometry=source.geometry
 const age=now-Date.parse(geometry.read_at)
 if(!Number.isFinite(age)||age<0||age>2000)return unavailable('Desktop geometry is stale; overlay off')
 const layoutAge=now-Date.parse(geometry.layout_read_at)
 if(!Number.isFinite(layoutAge)||layoutAge<0||layoutAge>2000)return unavailable('Game configuration is stale; overlay off')
 if(!['windowed','borderless'].includes(geometry.window_mode))return unavailable('Exclusive fullscreen or unknown window mode · overlay off')
 const physical=geometry.client_bounds
 if(!finiteRectangle(physical))return unavailable('Physical client bounds unavailable')
 if(physical.width!==geometry.calibration.client_size[0]||physical.height!==geometry.calibration.client_size[1]||Math.abs(geometry.ui_scale-geometry.calibration.ui_scale)>1e-6)return unavailable('HUD size or scale differs from the reviewed anchor calibration')
 try{
  const displays=screen.getAllDisplays().filter(display=>contains(screen.dipToScreenRect(null,display.bounds),physical))
  if(displays.length!==1)return unavailable('Game client spans displays or has no unique physical display')
  const display=displays[0]!
  // Passing the overlay window would use its old monitor's scale. Null selects
  // the display containing the observed physical client rectangle.
  const bounds=screen.screenToDipRect(null,physical)
  if(!finiteRectangle(bounds)||!contains(display.bounds,bounds))return unavailable('Converted DIP bounds do not match the observed display')
  const roundtrip=screen.dipToScreenRect(null,bounds)
  if(['x','y','width','height'].some(key=>Math.abs(roundtrip[key as keyof OverlayBounds]-physical[key as keyof OverlayBounds])>2))return unavailable('Native physical/DIP roundtrip disagrees')
  return{bounds,anchors:source.anchors,reason:null,displayId:display.id}
 }catch{return unavailable('Native per-monitor conversion failed · overlay off')}
}
