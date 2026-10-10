"""Line schedules and deterministic CPU simulations with common random numbers."""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
from math import ceil
from typing import Mapping
import numpy as np
from tft_data.models import DataError, freeze
from .models import Board, Unit, _encode
from .power import static, tunable, keyed, sigmoid, strength, estimate_strength
from .growth import growth_curve_lookup, standard_level
from .opponents import round_index

@dataclass(frozen=True)
class Line:
    id: str
    levels: Mapping[str,int] = field(default_factory=dict)
    rolls: Mapping[str,float] = field(default_factory=dict)
    stabilize: bool = False
    floor_options: tuple[float,...] = ()
    family_id: str | None = None
    def __post_init__(self):
        object.__setattr__(self,'levels',freeze(self.levels))
        object.__setattr__(self,'rolls',freeze(self.rolls))
        object.__setattr__(self,'floor_options',tuple(self.floor_options))
    def to_dict(self):
        return _encode(self)
    @classmethod
    def from_dict(cls,value):
        return cls(value['id'],value.get('levels',{}),value.get('rolls',{}),value.get('stabilize',False),tuple(value.get('floor_options',())),value.get('family_id'))

@dataclass(frozen=True)
class SimulationEffects:
    item_state: Board | None = None
    one_round_power_bonus: float = 0.0
    gold_delta: float = 0.0
    gold_reduction: float = 0.0
    xp_delta: int = 0
    free_rolls: int = 0
    gold_per_round: float = 0.0
    xp_per_round: int = 0
    roll_cost_delta: float = 0.0
    shop_slots_delta: float = 0.0

@dataclass(frozen=True)
class RoundProjection:
    round_id: str
    gold: float
    level: float
    hit_probability: float
    hp: float
    expected_placement: float
    planned_gold: float | None = None
    def to_dict(self):
        return _encode(self)

@dataclass(frozen=True)
class LineResult:
    line: Line
    expected_placement: float
    standard_error: float
    death_probability: float
    hit_probability: float
    projections: tuple[RoundProjection,...]
    rollout_placements: tuple[float,...]
    confidence: float
    seed: int
    death_placement_cost: float | None = None
    rollout_deaths: tuple[bool,...] = ()
    def to_dict(self):
        return _encode(self)


def snapshot_seed(snapshot):
    payload=json.dumps(snapshot.to_dict(),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    return int.from_bytes(sha256(payload).digest()[:8],'big')


def horizon_rounds(snapshot,data):
    order=tuple(static(data,'round_order'))
    if snapshot.round_id not in order:
        raise DataError(f'Round absent from calendar: {snapshot.round_id}')
    stage=int(snapshot.round_id.split('-')[0])+1
    result=tuple(r for r in order[order.index(snapshot.round_id):] if int(r.split('-')[0])<=stage)
    if not any(int(r.split('-')[0])==stage for r in result):
        raise DataError('Round calendar does not cover the end of the next stage')
    return result


def guide_line(guide,data):
    points=guide.line
    if not points:
        if not guide.carry_ids:
            raise DataError(f'No carry or Line for comp {guide.id}')
        points=keyed(tunable(data,'default_lines_by_carry_cost'),data.entities[guide.carry_ids[0]].cost)
        if not points:
            raise DataError(f'No default Line for comp {guide.id}')
        if isinstance(points,Mapping):
            if 'line' in points:
                points=points['line']
            elif 'roll_level' in points:
                target=int(points['roll_level'])
                calendar=static(data,'level_calendar')
                eligible=[r for r,level in calendar.items() if int(level)>=target]
                if not eligible:
                    raise DataError(f'No calendar point for default roll level {target}')
                anchor=min(eligible,key=lambda r:round_index(r,data))
                points=({'round':anchor,'level':target,'roll_floor':max(tunable(data,'gold_floors'))},)
            else:
                raise DataError(f'Invalid default Line for comp {guide.id}')
    if not all(isinstance(p,Mapping) and 'round' in p for p in points):
        raise DataError(f'Invalid Line points for comp {guide.id}')
    levels={p['round']:int(p['level']) for p in points if 'level' in p}
    rolls={p['round']:float(p['roll_floor']) for p in points if p.get('roll_floor') is not None}
    return Line(f'guide:{guide.id}',levels,rolls)


def current_level_target(line,round_id,data,level):
    eligible=[r for r in line.levels if round_index(r,data)<=round_index(round_id,data)]
    return max(level,line.levels[max(eligible,key=lambda r:round_index(r,data))]) if eligible else level


def normalize_xp(level,xp,data):
    table=static(data,'xp_table')
    upper=max(map(int,table),default=0)+1
    lookup=np.full(upper+1,np.inf)
    for id,amount in table.items():
        lookup[int(id)]=float(amount)
    for _ in range(len(table)):
        required=lookup[np.minimum(level,upper)]
        increase=xp>=required
        if not increase.any():
            break
        xp=np.where(increase,xp-required,xp)
        level=level+increase.astype(int)
    return level,xp


def _np_sigmoid(value):
    return np.exp(-np.logaddexp(0,-value))


def _terminal(power,hp,opponent_powers,opponent_hp,stage,data):
    damage=static(data,'player_damage')
    divisor=float(keyed(damage['stage_base'],stage))+float(damage['per_survivor'])*standard_level(f'{stage}-1',data)
    if divisor<=0:
        raise DataError(f'Nonpositive stage damage divisor: {stage}')
    a,b=float(tunable(data,'fight_scale')),float(tunable(data,'terminal_hp_weight'))
    result=np.ones(len(hp))
    for other,health in zip(opponent_powers,opponent_hp):
        if health>0:
            result+=_np_sigmoid(a*(other-power)+b*(health-hp)/divisor)
    return result


def simulate_lines(snapshot,history,data,comp_id,lines,*,effects=None,rollouts=None,opponents=(),seed=None,backup_id=None,assume_keys_on_time=False):
    """Return every scored concrete Line; all candidates use the same random tape."""
    from .planning import required
    missing=required(snapshot,data,('board','bench','gold','hp','level','xp','streak','lobby'))
    if missing:
        raise DataError('Simulation fields missing or stale: ' + ', '.join(missing))
    effects=effects or SimulationEffects()
    if effects.free_rolls<0 or effects.gold_reduction<0:
        raise DataError('Free rolls and gold reduction must be nonnegative')
    if float(snapshot.field('gold'))+effects.gold_delta-effects.gold_reduction<0:
        raise DataError('Simulation option is unaffordable')
    rounds=horizon_rounds(snapshot,data)
    count=int(rollouts or tunable(data,'rollouts_full'))
    if count<1:
        raise DataError('Rollout count must be positive')
    seed=snapshot_seed(snapshot) if seed is None else seed
    rules=static(data,'rules_flags')
    guide=data.guides[comp_id]
    from .shop_math import key_goals, owned_copies, canonical_id
    from .sim_board import RolloutBoard
    from .transition import main_roll_down
    from .bench import sale_value
    goals=key_goals(guide,data)
    board=snapshot.field('board')
    if effects.item_state is not None:
        board=effects.item_state
    bench=snapshot.field('bench')
    if effects.item_state is None and board.bench!=bench:
        board=Board(board.units,bench,board.trait_counts)
    prepared=RolloutBoard(board,data,guide)
    initial=strength(board,int(snapshot.field('level')),data)
    confidence=min(prepared.confidence,estimate_strength(board,int(snapshot.field('level')),data).confidence)
    for name in ('terminal_gold_weight','terminal_hp_weight','fight_scale','survivor_scale_by_stage'):
        if data.tunables[name].source in ('default','carried'):
            confidence=min(confidence,float(tunable(data,'confidence_medium_min')))
    from .lobby import alive_lobby
    hp_map=alive_lobby(snapshot)
    ids=tuple(hp_map)
    health=tuple(hp_map.values())
    by_id={p.opponent_id:p for p in opponents}
    fight_draws=np.random.default_rng(seed).random((count,len(rounds),2))
    # Shop draws are addressed by round and refresh, independent of purchases and Line actions.
    contested={}
    for opponent in opponents:
        for id,copies in opponent.expected_copies.items():
            contested[id]=contested.get(id,0)+copies
    pool=np.array([float(keyed(static(data,'pool_sizes'),int(c))) for c in prepared.costs])
    pool-=np.array([contested.get(id,0) for id in prepared.ids])
    pool=np.maximum(pool,0)
    total_income=sum(float(static(data,'gold_by_round').get(r,static(data,'gold_by_round').get('default',0)))+float(static(data,'interest')['cap'])+max(map(float,static(data,'streak_gold').values()),default=0)+float(rules['combat_win_gold'])+float(rules['pve_orb_gold'].get(r,0))+max(0,effects.gold_per_round) for r in rounds)
    roll_cost=float(rules['roll_cost'])+effects.roll_cost_delta
    if roll_cost<=0:
        raise DataError('Modified roll cost must be positive')
    max_shops=int(ceil((float(snapshot.field('gold'))+max(0,effects.gold_delta)+total_income)/roll_cost))+effects.free_rolls+1+int(sum(sale_value(u,data) for u in board.bench)/roll_cost)
    slots=float(snapshot.field('slot_count') if snapshot.field('slot_count') is not None else rules['unknown_wisp_slots'])+effects.shop_slots_delta
    if slots<=0:
        raise DataError('Champion slot count must be positive')
    max_slots=int(rules['champion_slots_max'])
    if slots>max_slots:
        raise DataError('Modified champion slots exceed the static maximum')
    from .bench import roll_sale_indices, sale_value
    sale_units=tuple(board.bench[i] for i in roll_sale_indices(board,data,target=comp_id,backup=backup_id))
    sale_copies=np.array([sum(3**(u.stars-1) for u in sale_units if canonical_id(u.unit_id,data)==id) for id in prepared.ids])
    sale_gold=sum(sale_value(u,data) for u in sale_units)
    deadline=main_roll_down(guide,data)
    goal_indices=np.array([prepared.index[id] for id in goals],dtype=int)
    goal_values=np.array(list(goals.values()))
    odds_table=static(data,'shop_odds')
    odds_lookup=np.zeros((max(map(int,odds_table))+1,5))
    for id,probabilities in odds_table.items():
        odds_lookup[int(id)]=probabilities
    for ci in range(5):
        if not (prepared.costs==ci+1).any():
            odds_lookup[:,ci]=0
    total_odds=odds_lookup.sum(axis=1)
    odds_lookup=np.divide(odds_lookup,total_odds[:,None],out=np.zeros_like(odds_lookup),where=total_odds[:,None]>0)
    desired=np.array([goals.get(id,1) for id in prepared.ids])
    key_mask=np.array([id in goals for id in prepared.ids])
    current_shop=snapshot.field('shop') if not required(snapshot,data,('shop',)) else None
    curve={r:growth_curve_lookup(r,data) for r in rounds}
    offsets={id:by_id[id].power-curve[snapshot.round_id] if id in by_id else 0.0 for id in ids}
    results=[]
    lines=tuple(lines)
    if not lines:
        return ()
    runs=count*len(lines)
    stabilizing=np.repeat([line.stabilize for line in lines],count)
    gold=np.full(runs,float(snapshot.field('gold'))+effects.gold_delta-effects.gold_reduction)
    hp=np.full(runs,float(snapshot.field('hp')))
    level=np.full(runs,int(snapshot.field('level')),dtype=int)
    xp=np.full(runs,float(snapshot.field('xp'))+effects.xp_delta)
    streak=np.full(runs,int(snapshot.field('streak')),dtype=int)
    level,xp=normalize_xp(level,xp,data)
    copies=np.broadcast_to(prepared.initial,(runs,len(prepared.ids))).copy()
    power=np.full(runs,initial)
    hit=lambda: (copies[:,goal_indices]>=goal_values).all(axis=1) if len(goal_indices) else np.ones(runs,dtype=bool)
    free_rolls=np.full(runs,effects.free_rolls,dtype=int)
    dead_placement=np.where(hp>0,0.0,1+len(ids))
    bench_sold=np.zeros(runs,dtype=bool)
    projections=[[] for _ in lines]
    for ri,round_id in enumerate(rounds):
        stage=int(round_id.split('-')[0])
        alive=hp>0
        floor=np.repeat(np.array([line.rolls.get(round_id,np.nan) for line in lines]),count)
        has_floor=np.isfinite(floor)
        selling=alive&~bench_sold&has_floor
        gold+=selling*sale_gold
        copies-=selling[:,None]*sale_copies
        bench_sold|=selling
        target=np.repeat([current_level_target(line,round_id,data,int(level.reshape(len(lines),count)[i].min())) for i,line in enumerate(lines)],count)
        cost=float(rules['xp_buy_cost']); amount=float(rules['xp_buy_amount'])
        if cost<=0 or amount<=0:
            raise DataError('XP purchase amounts must be positive')
        # Buy only to the scheduled target; interest is held outside this action.
        while ((level<target)&(gold>=cost)&alive).any():
            buying=(level<target)&(gold>=cost)&alive
            gold-=buying*cost; xp+=buying*amount
            level,xp=normalize_xp(level,xp,data)
        if assume_keys_on_time and (deadline is None or round_index(round_id,data)>=round_index(deadline,data)):
            # Optimistic reason-only counterfactual: key copies arrive at the Guide
            # deadline without shop uncertainty. It never selects or prices an action.
            copies[:,goal_indices]=np.where(alive[:,None],np.maximum(copies[:,goal_indices],goal_values),copies[:,goal_indices])
        rolling=alive & has_floor
        if ri==0 and current_shop is not None:
            # Positively captured offers are deterministic inputs; unread offers do
            # not become a fabricated current natural shop.
            for offer in current_shop:
                id=offer.get('unit_id') if isinstance(offer,Mapping) else offer
                if not id:
                    continue
                pool_id=canonical_id(id,data)
                if pool_id not in prepared.index:
                    raise DataError(f'Unsupported captured shop unit: {id}')
                index=prepared.index[pool_id]
                price=float(offer['cost']) if isinstance(offer,Mapping) and offer.get('cost') is not None else float(data.entities[id].cost)
                if price<0:
                    raise DataError('Captured unit price must be nonnegative')
                wanted=np.full(runs,prepared.target[index],dtype=bool)
                if stabilizing.any():
                    proposal=copies.copy(); proposal[:,index]+=1
                    wanted=np.where(stabilizing,(prepared.power(proposal,level)>prepared.power(copies,level))&prepared.supported[index],wanted)
                interest=static(data,'interest')
                reserve=np.minimum(gold,float(interest['cap'])/float(interest['gold_per_interest'])*float(interest['gold_per_tick']))
                minimum=0 if key_mask[index] else np.where(has_floor,floor,reserve)
                buying=alive&wanted&(stabilizing|(copies[:,index]<desired[index]))&(gold-price>=minimum)
                gold-=buying*price; copies[:,index]+=buying
        # Each later round supplies one free natural shop; current unknown shop is not fabricated.
        natural=alive&(ri>0)
        refresh=0
        while refresh<max_shops:
            stopped=np.where(stabilizing,False,hit())
            paid=rolling&~stopped&(gold>=np.where(has_floor,floor,0)+roll_cost)&(free_rolls<=0)
            free=alive&(free_rolls>0)&~stopped
            active=natural|paid|free
            if not active.any():
                break
            gold-=paid*roll_cost
            free_rolls-=free
            draws=np.tile(np.random.default_rng(np.random.SeedSequence([seed,ri,refresh,0x53484F50])).random((count,max_slots*2+1)),(len(lines),1))
            active_slots=np.floor(slots)+(draws[:,-1]<(slots-int(slots)))
            for slot in range(max_slots):
                rows=np.flatnonzero(active&(slot<active_slots))
                if not len(rows):
                    continue
                if level[rows].max()>=len(odds_lookup) or (total_odds[level[rows]]<=0).any():
                    raise DataError('Shop odds contain no available roster cost or level')
                odds=odds_lookup[level[rows]]
                remaining=np.maximum(pool[None,:]-copies[rows],0)
                cost=np.sum(draws[rows,slot*2,None]>np.cumsum(odds,axis=1),axis=1)+1
                weights=np.where(prepared.costs[None,:]==cost[:,None],remaining,0)
                totals=weights.sum(axis=1)
                cumulative=np.cumsum(weights,axis=1)
                picked=np.minimum(np.sum(draws[rows,slot*2+1,None]*totals[:,None]>=cumulative,axis=1),len(prepared.ids)-1)
                wanted=prepared.target[picked]
                if stabilizing[rows].any():
                    proposal=copies[rows].copy(); proposal[np.arange(len(rows)),picked]+=1
                    improvement=(prepared.power(proposal,level[rows])>prepared.power(copies[rows],level[rows]))&prepared.supported[picked]
                    wanted=np.where(stabilizing[rows],improvement,wanted)
                need=stabilizing[rows]|(copies[rows,picked]<desired[picked])
                interest=static(data,'interest')
                reserve=np.minimum(gold[rows],float(interest['cap'])/float(interest['gold_per_interest'])*float(interest['gold_per_tick']))
                min_gold=np.where(key_mask[picked],0,np.where(has_floor[rows],floor[rows],reserve))
                buy=(totals>0)&wanted&need&(gold[rows]-prepared.costs[picked]>=min_gold)
                gold[rows]-=buy*prepared.costs[picked]
                copies[rows,picked]+=buy
            natural[:]=False
            refresh+=1
        forced=bool(deadline and round_index(round_id,data)>=round_index(deadline,data))
        power=prepared.power(copies,level,forced=forced)
        other_powers=[curve[round_id]+offsets[id] for id in ids]
        kind=static(data,'round_types').get(round_id)
        if kind is None:
            raise DataError(f'Missing round type: {round_id}')
        won=np.zeros(runs,dtype=bool)
        if kind=='combat':
            selected=np.minimum((np.tile(fight_draws[:,ri,0],len(lines))*len(ids)).astype(int),len(ids)-1)
            opponent=np.asarray(other_powers)[selected]
            scale=keyed(tunable(data,'win_scale_by_stage'),stage)
            if scale is None:
                scale=tunable(data,'fight_scale')
            fight_power=power+(effects.one_round_power_bonus if ri==0 else 0)
            won=(np.tile(fight_draws[:,ri,1],len(lines))<_np_sigmoid(float(scale)*(fight_power-opponent)))&alive
            loss=alive&~won
            survivor_scale=keyed(tunable(data,'survivor_scale_by_stage'),stage)
            if survivor_scale is None:
                raise DataError(f'Missing survivor scale: {stage}')
            survivors=standard_level(round_id,data)*_np_sigmoid(float(survivor_scale)*(opponent-fight_power))
            damage=static(data,'player_damage')
            lost=float(keyed(damage['stage_base'],stage))+float(damage['per_survivor'])*survivors
            hp=np.maximum(0,hp-loss*lost)
            streak=np.where(won,np.where(streak>0,streak+1,1),np.where(loss,np.where(streak<0,streak-1,-1),streak))
            newly_dead=alive&(hp<=0)
            # Deterministic expected elimination rank reuses the terminal HP/power
            # model at death. Captured opponents remain in every rollout fight.
            # Their later eliminations are not sampled or treated as observations.
            rank_at_death=_terminal(fight_power,np.zeros(runs),other_powers,health,stage,data)
            dead_placement=np.where(newly_dead,rank_at_death,dead_placement)
        elif kind=='pve' and not rules['pve_preserves_streak']:
            streak=np.where(alive,0,streak)
        elif kind not in ('pve','carousel'):
            raise DataError(f'Unknown round type: {kind}')
        income=static(data,'gold_by_round')
        base=income.get(round_id,income.get('default'))
        if base is None:
            raise DataError(f'Missing base income: {round_id}')
        interest=static(data,'interest')
        interest_gold=np.minimum(np.floor(gold/float(interest['gold_per_tick']))*float(interest['gold_per_interest']),float(interest['cap']))
        streak_gold=np.zeros(runs)
        for threshold,value in sorted(static(data,'streak_gold').items(),key=lambda item:int(item[0])):
            streak_gold=np.where(np.abs(streak)>=int(threshold),float(value),streak_gold)
        orb=float(rules['pve_orb_gold'].get(round_id,0)) if kind=='pve' else 0
        planned_gold=gold.reshape(len(lines),count).mean(axis=1)
        gold+=alive*(float(base)+interest_gold+streak_gold+won*float(rules['combat_win_gold'])+orb+effects.gold_per_round)
        xp+=alive*(float(rules['passive_xp'])+effects.xp_per_round)
        level,xp=normalize_xp(level,xp,data)
        # Passive XP can raise the terminal unit cap after the current fight.
        terminal_power=prepared.power(copies,level,forced=forced)
        terminal=_terminal(terminal_power,hp,other_powers,health,stage,data)
        # Held gold approximates future buying capacity beyond this bounded horizon.
        # This explicit family-1 coefficient remains default/carried until fitted.
        gold_weight=float(tunable(data,'terminal_gold_weight'))
        if gold_weight<0:
            raise DataError('Terminal gold weight must be nonnegative')
        terminal=np.clip(terminal-gold_weight*np.maximum(gold,0),1,1+len(ids))
        terminal=np.where(hp>0,terminal,dead_placement)
        grouped=[v.reshape(len(lines),count) for v in (gold,level,hit(),hp,terminal)]
        means=[v.mean(axis=1) for v in grouped]
        for i in range(len(lines)):
            projections[i].append(RoundProjection(round_id,*[float(v[i]) for v in means],float(planned_gold[i])))
    values=terminal.reshape(len(lines),count)
    dead=(hp<=0).reshape(len(lines),count)
    for i,line in enumerate(lines):
        error=float(values[i].std(ddof=1)/np.sqrt(count)) if count>1 else 0.0
        probability=float(dead[i].mean())
        death_cost=0.0 if not dead[i].any() else probability*(float(values[i][dead[i]].mean())-float(values[i][~dead[i]].mean())) if (~dead[i]).any() else None
        results.append(LineResult(line,float(values[i].mean()),error,probability,projections[i][-1].hit_probability,tuple(projections[i]),tuple(map(float,values[i])),confidence,seed,death_cost,tuple(map(bool,dead[i]))))
    return tuple(results)


def candidate_lines(snapshot,data,guide,*,rounds_left=float('inf')):
    base=guide_line(guide,data)
    current=snapshot.round_id
    order=tuple(static(data,'round_order'))
    future=[r for r in base.levels if round_index(r,data)>round_index(current,data)]
    choices=[base]
    if future:
        next_step=min(future,key=lambda r:round_index(r,data))
        index=order.index(next_step)
        for label,shift in (('early',-1),('late',1)):
            changed=order[max(0,min(len(order)-1,index+shift))]
            levels=dict(base.levels); value=levels.pop(next_step); levels[changed]=value
            choices.append(Line(f'{base.id}:{label}',levels,base.rolls))
    floors=tuple(float(v) for v in tunable(data,'gold_floors'))
    if rounds_left<float(tunable(data,'all_in_rounds_left')) and 0 not in floors:
        floors+= (0.0,)
    choices.append(Line('roll:now',dict(base.levels)|{current:int(snapshot.field('level'))},{current:min(floors)},floor_options=floors))
    upcoming=[r for r in set(base.levels)|set(base.rolls) if round_index(r,data)>round_index(current,data)]
    if upcoming:
        next_point=min(upcoming,key=lambda r:round_index(r,data))
        choices.append(Line('roll:next',base.levels,{next_point:min(floors)},floor_options=floors))
    choices.append(Line('hold',base.levels,{}))
    if rounds_left<float(tunable(data,'stabilize_rounds_left')):
        choices.append(Line('stabilize',dict(base.levels)|{current:int(snapshot.field('level'))},{current:min(floors)},True,floors))
    cap=int(tunable(data,'line_candidate_cap'))
    if cap<1:
        raise DataError('Line candidate cap must be positive')
    result=[]; seen=set()
    for line in choices:
        signature=(tuple(sorted(line.levels.items())),tuple(sorted(line.rolls.items())),line.stabilize)
        if signature not in seen:
            seen.add(signature); result.append(line)
    # Emergency stabilization and an all-in floor survive the family cap.
    if len(result)>cap and any(l.stabilize for l in result):
        result=result[:max(0,cap-1)]+[next(l for l in result if l.stabilize)]
    else:
        result=result[:cap]
    return tuple(result)


def concrete_lines(lines):
    result=[]
    for line in lines:
        if not line.floor_options:
            result.append(line)
            continue
        for floor in line.floor_options:
            result.append(Line(f'{line.id}@{floor:g}',line.levels,{r:floor for r in line.rolls},line.stabilize,family_id=line.family_id or line.id))
    return tuple(result)


def paired_value(snapshot,history,data,comp_id,lines,effects,*,rollouts=None,opponents=()):
    seed=snapshot_seed(snapshot)
    before=simulate_lines(snapshot,history,data,comp_id,lines,rollouts=rollouts,opponents=opponents,seed=seed)
    after=simulate_lines(snapshot,history,data,comp_id,lines,effects=effects,rollouts=rollouts,opponents=opponents,seed=seed)
    # Positive means the option improves expected placement.
    base=min(before,key=lambda r:r.expected_placement)
    choice=min(after,key=lambda r:r.expected_placement)
    differences=np.asarray(base.rollout_placements)-np.asarray(choice.rollout_placements)
    error=float(differences.std(ddof=1)/np.sqrt(len(differences))) if len(differences)>1 else 0.0
    return float(differences.mean()),error,before,after
