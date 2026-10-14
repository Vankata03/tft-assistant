import {expect,it} from 'vitest'
import {liveVoiceCue} from '../src/live/voiceRules'
import type {LiveState} from '../src/shared/messages'
import fixture from './fixtures/live.json'
const base={...fixture,content:{...fixture.content,opponents:[],confidence_medium_min:.5}} as unknown as LiveState
const now=Date.parse(fixture.content.captured_at)
it('ordinary buys, holding, combat, silence and low confidence produce no Live voice',()=>{
 expect(liveVoiceCue(base,now)).toBeNull()
 const augment={...base,content:{...base.content!,phase:'augment' as const,advice:[{...base.content!.advice[0]!,domain:'augment',action:'Take Alpha',payload:{operation:'pick'}}]},observed_phase:'augment' as const}
 expect(liveVoiceCue(augment,now)?.text).toBe('Take Alpha')
 expect(liveVoiceCue({...augment,mode:'silent'},now)).toBeNull()
 expect(liveVoiceCue({...augment,observed_phase:'combat'},now)).toBeNull()
 expect(liveVoiceCue({...augment,content:{...augment.content,advice:[{...augment.content.advice[0]!,confidence:.1}]}},now)).toBeNull()
 expect(liveVoiceCue(augment,now+3000)).toBeNull()
})
it('roll-down speech is keyed to one observed start, not each capture revision',()=>{
 const roll={...base,observed_phase:'roll_down' as const,content:{...base.content!,phase:'roll_down' as const,advice:[{...base.content!.advice[0]!,payload:{gold_floor:10}}]}}
 expect(liveVoiceCue(roll,now)?.text).toBe('Roll down to 10')
 expect(liveVoiceCue({...roll,revision:'new',content:{...roll.content,snapshot_id:'new'}},now)?.id).toBe(liveVoiceCue(roll,now)?.id)
})
