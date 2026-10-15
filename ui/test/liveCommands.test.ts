import {it,expect} from 'vitest'
import {currentLiveMember,validEvidencePath} from '../src/shared/liveCommands'
import fixture from './fixtures/live.json'
import {parseCoreMessage} from '../src/shared/protocol'
import type {LiveState} from '../src/shared/messages'
it('binds renderer commands to the current game and delivered revision',()=>{
 const view=parseCoreMessage(JSON.stringify(fixture)) as LiveState
 expect(currentLiveMember(view,{game_id:view.content!.game_id,revision:view.revision})).toBe(true)
 expect(currentLiveMember({...view,mode:'silent',content:null},{game_id:'123',revision:view.revision})).toBe(false)
 expect(currentLiveMember(view,{game_id:'old-game',revision:view.revision})).toBe(false)
 expect(currentLiveMember(view,{game_id:'123',revision:'old-revision'})).toBe(false)
 expect(validEvidencePath(['advice',0,'options',2])).toBe(true)
 expect(validEvidencePath(['advice',-1])).toBe(false)
 expect(validEvidencePath(['advice',2**64])).toBe(false)
})
