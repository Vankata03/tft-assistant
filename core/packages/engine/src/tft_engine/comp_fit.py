"""Analytic comp screening; simulation replaces its backbone rather than adding to it."""
from dataclasses import dataclass, field
from typing import Mapping
from math import exp
from tft_data.models import DataError, freeze
from .models import Board, Unit
from .power import strength, placement, static, tunable, keyed, win_probability, surviving_units
from .growth import growth_curve_lookup, standard_level
from .shop_math import hit_probability, key_goals, owned_copies
from .lines import guide_line, current_level_target
from .opponents import round_index
from .registry import FitTerm

@dataclass(frozen=True)
class CompFit:
    comp_id: str
    score: float
    simulated: bool
    terms: Mapping[str,FitTerm]
    confidence: float
    hit_probability: float = 0.0
    death_probability: float = 0.0
    def __post_init__(self):
        object.__setattr__(self,'terms',freeze(self.terms))


def damage_divisor(round_id,data):
    stage=int(round_id.split('-')[0])
    damage=static(data,'player_damage')
    value=float(keyed(damage['stage_base'],stage))+float(damage['per_survivor'])*standard_level(round_id,data)
    if value<=0:
        raise DataError('Nonpositive stage damage for placement')
    return value


def rounds_left_to_live(snapshot,data,opponents=()):
    from .planning import read
    board=read(snapshot,data,'board'); level=int(read(snapshot,data,'level'))
    own=strength(board,level,data)
    stage=int(snapshot.round_id.split('-')[0])
    from .lobby import alive_lobby
    roster=alive_lobby(snapshot,data)
    by_id={opponent.opponent_id:opponent.power for opponent in opponents}
    powers=[by_id[id] if id in by_id else growth_curve_lookup(snapshot.round_id,data) for id in roster]
    loss=0.0
    for power in powers:
        damage=static(data,'player_damage')
        survivors=surviving_units(max(0,power-own),stage,standard_level(snapshot.round_id,data),data)
        loss+=(1-win_probability(own,power,stage,data))*(float(keyed(damage['stage_base'],stage))+float(damage['per_survivor'])*survivors)
    loss/=len(powers)
    return float(read(snapshot,data,'hp'))/loss if loss>0 else float('inf')


def screen_comp(snapshot,data,guide,context,domain_terms,*,opponents=(),rounds_left=None):
    from .planning import read
    line=guide_line(guide,data)
    owned=owned_copies(context.recommended_board,data)
    goals=key_goals(guide,data)
    rules=static(data,'rules_flags')
    slots=read(snapshot,data,'slot_count')
    if slots is None:
        slots=rules['unknown_wisp_slots']
    contested={}
    for opponent in opponents:
        for id,copies in opponent.expected_copies.items():
            contested[id]=contested.get(id,0)+copies
    order=tuple(static(data,'round_order'))
    rolls=[r for r in line.rolls if round_index(r,data)>=round_index(snapshot.round_id,data)]
    target_round=min(rolls,key=lambda r:round_index(r,data)) if rolls else snapshot.round_id
    wait=max(0,order.index(target_round)-order.index(snapshot.round_id))
    gold=float(read(snapshot,data,'gold'))
    for round_id in order[order.index(snapshot.round_id):order.index(target_round)]:
        gold+=float(static(data,'gold_by_round').get(round_id,static(data,'gold_by_round').get('default',0)))
    floor=float(line.rolls.get(target_round,gold))
    shops=int(max(0,(gold-floor)//float(rules['roll_cost'])))
    target_level=current_level_target(line,target_round,data,int(read(snapshot,data,'level')))
    # The screen cannot borrow unfunded XP: spend its explicit XP cost before roll gold.
    xp=float(read(snapshot,data,'xp'))+wait*float(rules['passive_xp'])
    level=int(read(snapshot,data,'level')); buy_cost=float(rules['xp_buy_cost']); buy_amount=float(rules['xp_buy_amount'])
    while level<target_level:
        required=keyed(static(data,'xp_table'),level)
        if required is None:
            break
        deficit=max(0,float(required)-xp)
        purchases=int(__import__('math').ceil(deficit/buy_amount))
        price=purchases*buy_cost
        if gold-price<0:
            break
        gold-=price; xp+=purchases*buy_amount-float(required); level+=1
    shops=int(max(0,(gold-floor)//float(rules['roll_cost'])))
    prior_hit=[]; actual_hit=[]
    for id,goal in goals.items():
        prior_hit.append(hit_probability(id,goal,shops,float(slots),level,data,contested=contested))
        actual_hit.append(hit_probability(id,max(0,goal-owned.get(id,0)),shops,float(slots),level,data,owned=owned,contested=contested))
    old=min(prior_hit,default=1.0); hit=min(actual_hit,default=1.0)
    hp=float(read(snapshot,data,'hp'))
    from .lobby import alive_lobby
    hp_map=alive_lobby(snapshot,data)
    health=tuple(hp_map.values())
    by_id={o.opponent_id:o.power for o in opponents}
    opposing=tuple(by_id[id] if id in by_id else growth_curve_lookup(snapshot.round_id,data) for id in hp_map)
    from .shop_math import canonical_id
    ideal=Board(tuple(Unit(id,3 if goals.get(canonical_id(id,data),0)>=9 else 2 if canonical_id(id,data) in goals else 1) for id in guide.units[:int(read(snapshot,data,'level'))]))
    ideal_power=strength(ideal,int(read(snapshot,data,'level')),data)
    missing_power=strength(read(snapshot,data,'board'),int(read(snapshot,data,'level')),data)
    divisor=damage_divisor(snapshot.round_id,data)
    ideal_placement=placement(ideal_power,opposing,hp,health,divisor,data)
    miss_placement=placement(missing_power,opposing,hp,health,divisor,data)
    miss_cost=max(0,miss_placement-ideal_placement)
    cluster=getattr(guide,'cluster_id',None) or guide.id
    statistics=[s for s in data.statistics if s.kind=='comp' and (s.entity_id in (cluster,guide.id) or s.comp_id==cluster)]
    base=statistics[0].average_placement if statistics else ideal_placement
    confidence=1.0 if statistics and not statistics[0].stale and not statistics[0].changed else float(tunable(data,'confidence_medium_min'))
    left=rounds_left_to_live(snapshot,data,opponents) if rounds_left is None else rounds_left
    survival=exp(-wait/left) if left>0 else 0.0
    last=1+len(health)
    terms={'baseline':FitTerm(base,'comp_statistics' if statistics else 'modeled_placement_without_comp_statistics',confidence=confidence),
        'hit':FitTerm((1-old)*miss_cost,'screen_hit_probability',{'probability':hit}),
        'owned_progress':FitTerm((old-hit)*miss_cost,'owned_progress_reduces_missing_key_cost'),
        'feasibility':FitTerm((1-survival)*max(0,last-base),'line_before_expected_death',{'rounds_left':left,'wait':wait})}
    terms.update(domain_terms)
    return CompFit(guide.id,sum(t.delta for t in terms.values()),False,terms,min([confidence]+[t.confidence for t in domain_terms.values()]),hit,1-survival)
