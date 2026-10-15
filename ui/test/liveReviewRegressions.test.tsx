// @vitest-environment jsdom
import {act,createElement} from 'react';
import {createRoot} from 'react-dom/client';
import {it,expect,vi} from 'vitest';
vi.hoisted(() => { Object.assign(globalThis, {__LIVE_ENABLED__: true}) });
import {App} from '../src/renderer/src/App';
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});
it('opens post-game review in Live mode through the mounted App',async()=>{
 const state={core:'running',mode:'live',availableModes:['silent','baseline','live'],gameflow:{clientRunning:true,phase:'EndOfGame'},live:{mode:'live',revision:null,content:null,status:'Ended'}};
 Object.assign(window,{coach:{getState:async()=>state,onState:()=>()=>{},reviewGames:vi.fn(async()=>({games:[{game_id:'123',finished:true,mode:'live',review_locked:false,placement:4}]})),requestReview:vi.fn(async()=>({value:{locked:false,top5:[],placement:{value:4},category_costs:{}}})),setMode:()=>{}}});
 const node=document.createElement('div');document.body.append(node);const root=createRoot(node);
 try{
  await act(async()=>{root.render(createElement(App));await new Promise(r=>setTimeout(r,20))});
  await act(async()=>{await new Promise(r=>setTimeout(r,20))});
  const open=[...node.querySelectorAll('button')].find(b=>b.textContent==='Post-game review');expect(open).toBeTruthy();
  await act(async()=>open!.click());
  expect(node.textContent).toContain('Logged games');
 }finally{await act(async()=>root.unmount())}
});
import {renderToStaticMarkup} from 'react-dom/server';
import {LiveOverlay} from '../src/live/LiveOverlay';
import fixture from './fixtures/live.json';
it('removes movement arrows after their advice deadline passes',()=>{
 const timestamp=Date.parse(fixture.content.captured_at);
 const row={...fixture.content.advice[0],domain:'positioning',valid_until:new Date(timestamp+2000).toISOString(),payload:{operation:'layout',layout:[{unit_id:'carry',cell:1}],arrows:[{from:0,to:1}]}};
 const state={core:'running',mode:'live',live:{...fixture,content:{...fixture.content,phase:'planning',advice:[row]},observed_phase:'planning'},overlayGeometry:{bounds:{x:0,y:0,width:1920,height:1080},anchors:[{kind:'hex',index:0,x:.1,y:.1,width:.03,height:.03},{kind:'hex',index:1,x:.2,y:.2,width:.03,height:.03}]}};
 const html=renderToStaticMarkup(createElement(LiveOverlay,{state:state as any,onPin:()=>{},now:timestamp+2500}));
 expect(html).not.toContain('marker-end');
});
it('pauses roll tracker after its ownership certificate and econ advice expire',()=>{
 const timestamp=Date.parse(fixture.content.captured_at);
 const state={core:'running',mode:'live',live:{...fixture,ownership_qualified:false,invalidated:{[fixture.content.advice[0]!.decision_id]:'inventory_complete unread or stale'},content:{...fixture.content,phase:'roll_down',roll_tracker:{available:true,gold_floor:10,rolls_left:5,units:[{unit_id:'carry',copies:1,goal:3,hit_probability:.75,in_shop:true}]}},observed_phase:'roll_down'},overlayGeometry:{bounds:{x:0,y:0,width:1920,height:1080},anchors:[{kind:'shop',index:0,x:.1,y:.1,width:.03,height:.03}]}};
 const html=renderToStaticMarkup(createElement(LiveOverlay,{state:state as any,onPin:()=>{},now:timestamp+2500}));
 expect(html).not.toContain('5 rolls left');
});
import {readFileSync} from 'node:fs';
import {EvidenceDrawer} from '../src/live/EvidenceDrawer';
it('opens the newly selected Live evidence path in the existing drawer',async()=>{
 const requests:any[]=[];
 Object.assign(window,{coach:{evidencePage:vi.fn(async(args:any)=>{requests.push(args);return {...args,page:{items:[],next_cursor:null}}})}});
 const node=document.createElement('div');document.body.append(node);const root=createRoot(node);
 try{
  await act(async()=>root.render(createElement(EvidenceDrawer,{view:fixture as any,path:['first'],onClose:()=>{}})));
  await act(async()=>root.render(createElement(EvidenceDrawer,{view:fixture as any,path:['second'],onClose:()=>{}})));
  expect(requests.at(-1).path).toEqual(['second']);
 }finally{await act(async()=>root.unmount())}
});
it('allows the overlay Line widget to receive pointer input',()=>{
 const stylesheet=document.createElement('style');
 stylesheet.textContent=readFileSync('src/renderer/src/cockpit.css','utf8')+readFileSync('src/live/live.css','utf8');document.head.append(stylesheet);
 const node=document.createElement('div');document.body.append(node);
 try{
  const state={core:'running',mode:'live',live:fixture,overlayGeometry:{bounds:{x:0,y:0,width:1920,height:1080},anchors:[{kind:'line',index:0,x:.1,y:.1,width:.1,height:.03}]}};
  node.innerHTML=renderToStaticMarkup(createElement(LiveOverlay,{state:state as any,onPin:()=>{},now:Date.parse(fixture.content.captured_at)}));
  const button=node.querySelector('.line-widget button')!;
  expect(getComputedStyle(button).pointerEvents).toBe('auto');
 }finally{stylesheet.remove();node.remove()}
});

import {LiveCockpit} from '../src/live/LiveCockpit';
it('pauses cockpit roll-tracker values when ownership evidence expires',()=>{
 const timestamp=Date.parse(fixture.content.captured_at);
 const state={core:'running',mode:'live',availableModes:['silent','baseline','live'],live:{...fixture,ownership_qualified:false,invalidated:{[fixture.content.advice[0]!.decision_id]:'inventory_complete unread or stale'},content:{...fixture.content,phase:'roll_down',roll_tracker:{available:true,gold_floor:10,rolls_left:5,units:[{unit_id:'carry',copies:1,goal:3,hit_probability:.75,in_shop:true}]}},observed_phase:'roll_down'}};
 const html=renderToStaticMarkup(createElement(LiveCockpit,{state:state as any,onMode:()=>{},onPin:()=>{},onDetail:()=>{},now:timestamp+2500}));
 expect(html).not.toContain('5 rolls left');
 expect(html).not.toContain('75%');
});
