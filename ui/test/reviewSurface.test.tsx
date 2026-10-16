import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {it,expect} from 'vitest'
import {ReviewSummaryView} from '../src/renderer/src/review/ReviewPanel'
const callbacks={onMoment:()=>{},onTag:()=>{}}
it('locked review renders no placement, scores, moments or tag controls',()=>{
 const html=renderToStaticMarkup(createElement(ReviewSummaryView,{...callbacks,summary:{locked:true,placement:{value:1},category_costs:{shop:{value:-2}},top5:[{reason:'private-moment'}]}}))
 expect(html).toContain('Review locked')
 expect(html).not.toContain('private-moment')
 expect(html).not.toContain('-2')
 expect(html).not.toContain('agree')
})
it('review preserves signed costs and unavailable follow attribution',()=>{
 const html=renderToStaticMarkup(createElement(ReviewSummaryView,{...callbacks,summary:{game_id:'123',locked:false,placement:{value:4},follow_rate:{value:null,reason:'not_shown'},category_costs:{shop:{value:-1.1}},top5:[{moment_id:'moment',engine_decision_id:'engine',round_id:'3-2',category:'shop',cost:-1.1,reason:'buy',shown:{status:'unavailable'}}]}}))
 expect(html).toContain('-1.10')
 expect(html).toContain('Unavailable · not_shown')
 expect(html).toContain('Expand scored moment')
 expect(html).toContain('unsure')
})

it('review distinguishes player and Engine choices, uncertainty and unavailable media',()=>{
 const html=renderToStaticMarkup(createElement(ReviewSummaryView,{...callbacks,summary:{game_id:'123',locked:false,top5:[{moment_id:'m',round_id:'3-2',category:'shop',cost:-1.1,engine_choice:{option_id:'buy-shen',action:'buy',expected_placement:3.1,standard_error:.2},player_choice:{option_id:'hold-gold',action:'hold',expected_placement:4.2,standard_error:.3},unavailable:{keyframe:'capture_gap'},keyframe:{media_name:null,reason:'logged_keyframe_unavailable'},shown:{status:'unavailable'}}]}}))
 expect(html).toContain('Engine choice')
 expect(html).toContain('Player choice')
 expect(html).toContain('buy-shen')
 expect(html).toContain('hold-gold')
 expect(html).toContain('3.10 ± 0.20')
 expect(html).toContain('4.20 ± 0.30')
 expect(html).toContain('logged keyframe unavailable')
 expect(html).not.toContain('<pre>')
})

it('saved review tag is visible and pressed on its moment card',()=>{
 const html=renderToStaticMarkup(createElement(ReviewSummaryView,{...callbacks,summary:{game_id:'123',locked:false,top5:[{moment_id:'m',round_id:'3-2',category:'augment',tag:'disagree'}]}}))
 expect(html).toContain('Saved tag: disagree')
 expect(html).toContain('aria-pressed="true"')
})

it('renders category averages and the number of games behind each estimate',async()=>{
 const {ReviewAveragesView}=await import('../src/renderer/src/review/ReviewPanel')
 const html=renderToStaticMarkup(createElement(ReviewAveragesView,{aggregates:{last10:{games:10,categories:{econ:{value:-.75,games:8}}},live_run:{games:0,categories:{}}}}))
 expect(html).toContain('Last 10 logged games')
 expect(html).toContain('-0.75')
 expect(html).toContain('8 scored games')
 expect(html).toContain('Live-mode run')
})
