// Describes a Line's recorded level and roll-down schedule; no projection is implied.
const entries=(value:unknown):[string,unknown][]=>typeof value==='object'&&value!==null&&!Array.isArray(value)?Object.entries(value):[]
const shown=(value:unknown):string=>typeof value==='number'||typeof value==='string'?String(value):'unavailable'

export function describeSchedule(schedule:unknown):string{
 const row=typeof schedule==='object'&&schedule!==null?schedule as Record<string,unknown>:{}
 const levels=entries(row.levels),rolls=entries(row.rolls)
 return [
  levels.length?`Levels ${levels.map(([round,level])=>`${round} → ${shown(level)}`).join(', ')}`:'No level-ups',
  rolls.length?`roll-downs ${rolls.map(([round,floor])=>`${round} to ${shown(floor)} gold`).join(', ')}`:'no roll-down',
 ].join(' · ')
}
