"""Greedy strongest-owned selection followed by strict swap improvement."""
from .models import Board, Advice
from .power import strength, tunable, static, estimate_strength, stage_tunable
from .lines import guide_line
from .opponents import round_index
from .shop_math import canonical_id
from dataclasses import replace


def main_roll_down(guide,data):
    rolls=guide_line(guide,data).rolls
    return min(rolls,key=lambda r:round_index(r,data)) if rolls else None


def strongest_owned_board(board,level,data,*,target=None,round_id=None,capacity=None,generic_item_power=None):
    from .capacity import CapacityModel
    model=CapacityModel(data)
    model.check(board,level,capacity)
    units=board.units+board.bench
    costs=[model.cost(u.unit_id) for u in units]
    guide=data.guides.get(target) if target else None
    deadline=main_roll_down(guide,data) if guide else None
    forced=bool(deadline and round_id and round_index(round_id,data)>=round_index(deadline,data))
    tolerance=stage_tunable(data,'transition_tolerance',round_id)
    weights=tunable(data,'classifier_weights')
    target_pools={canonical_id(id,data) for id in guide.units} if guide else set()
    carry_pools={canonical_id(id,data) for id in guide.carry_ids} if guide else set()
    key_pools={canonical_id(id,data) for id in getattr(guide,'key_ids',())} if guide else set()
    def progress(indices):
        if not guide:
            return 0
        return sum(float(weights['carry'] if canonical_id(units[i].unit_id,data) in carry_pools else weights['key'] if canonical_id(units[i].unit_id,data) in key_pools else weights['other']) for i in indices if canonical_id(units[i].unit_id,data) in target_pools)
    def candidate(indices):
        selected=tuple(units[i] if i<len(board.units) else replace(units[i],position=None) for i in sorted(indices))
        counts=board.trait_counts if selected==board.units else None
        return Board(selected,tuple(replace(units[i],position=None) if i<len(board.units) else units[i] for i in range(len(units)) if i not in indices),counts)
    def score(indices):
        value=estimate_strength(candidate(indices),level,data,capacity=capacity)
        return value.power if generic_item_power is None else value.unit_term+value.trait_term+generic_item_power
    def can_add(indices,new):
        before=model.state(candidate(indices),level,capacity)
        after=model.state(candidate(indices+[new]),level,capacity)
        return len(indices)<28 and before.occupied_slots<=before.maximum_slots and before.occupied_slots+costs[new]<=before.maximum_slots and after.occupied_slots<=after.maximum_slots
    def fill(indices):
        indices=list(indices)
        while True:
            possibilities=[i for i in available if i not in indices and can_add(indices,i)]
            if not possibilities:
                return indices
            evaluated=[(score(indices+[i]),progress(indices+[i]),i) for i in possibilities]
            maximum=max(v[0] for v in evaluated)
            eligible=[v for v in evaluated if v[0]>=maximum-tolerance]
            chosen=max(eligible,key=lambda v:(v[1],v[0],-v[2]))
            indices.append(chosen[2])
    selected=[]
    available=list(range(len(units)))
    if forced:
        # Comp membership outranks power only after the explicit Guide deadline.
        required=[i for i in available if canonical_id(units[i].unit_id,data) in target_pools]
        required.sort(key=lambda i:(-progress([i]),-score([i]) if can_add([],i) else float('inf'),i))
        for i in required:
            if can_add(selected,i):
                selected.append(i)
    selected=fill(selected)
    current_indices=list(range(len(board.units)))
    if (not forced or progress(current_indices)>=progress(selected)) and score(current_indices)>score(selected)+tolerance:
        selected=current_indices
    # Strict progress-or-power improvement keeps the search finite and deterministic.
    seen={tuple(sorted(selected))}
    best_power=score(selected)
    while selected:
        current=score(selected); current_progress=progress(selected)
        best=None
        for old in selected:
            if forced and canonical_id(units[old].unit_id,data) in target_pools:
                continue
            for new in available:
                if new in selected:
                    continue
                remaining=[i for i in selected if i!=old]
                if not can_add(remaining,new):
                    continue
                proposal=fill(remaining+[new])
                key=tuple(sorted(proposal))
                if key in seen:
                    continue
                value=score(proposal); towards=progress(proposal)
                if value>current+tolerance or (value>=best_power-tolerance and towards>current_progress):
                    choice=(towards if value>=current-tolerance else -1,value,key,proposal)
                    if best is None or choice[:3]>best[:3]:
                        best=choice
        if best is None:
            break
        selected=best[3]; best_power=max(best_power,best[1]); seen.add(tuple(sorted(selected)))
    return candidate(selected)


def transition_advice(snapshot,recommended,plan,data):
    from .planning import read
    from .capacity import CapacityModel
    from .capacity_fields import evidence_from_snapshot
    evidence=evidence_from_snapshot(snapshot,data)
    current=read(snapshot,data,'board')
    old=list(current.units); new=list(recommended.units)
    for unit in tuple(old):
        if unit in new:
            old.remove(unit); new.remove(unit)
    value=estimate_strength(recommended,int(read(snapshot,data,'level')),data,capacity=evidence)
    validity={'round':snapshot.round_id,'board':current.to_dict()}
    advice=[]
    if old or new:
        current=Board(current.units,tuple(read(snapshot,data,'bench')),current.trait_counts)
        steps=CapacityModel(data).transition(current,recommended,int(read(snapshot,data,'level')),evidence)
        # The kept board's power is what transition_tolerance compared the swap against.
        kept=estimate_strength(current,int(read(snapshot,data,'level')),data,capacity=evidence)
        advice.append(Advice('transition','Swap owned units','act_this_phase',value.confidence,'strongest_owned_board',{'power':value.power,'current_power':kept.power},('board','bench','round'),decision_id=f'{snapshot.snapshot_id}:transition',option_id='transition',payload={'swap_out':[u.unit_id for u in old],'swap_in':[u.unit_id for u in new],'board':recommended.to_dict(),'steps':steps},validity_state=validity))
    from .bench import bench_priority, roll_sale_indices
    priorities=bench_priority(recommended,data,target=plan.target,backup=plan.backup,recommended=recommended)
    capacity=int(static(data,'bench_size'))
    kept={index for _,_,index in priorities[:capacity]}
    sales={index for _,_,index in priorities[capacity:]}
    rolling=bool(plan.line and snapshot.round_id in plan.line.rolls)
    if rolling:
        sales.update(roll_sale_indices(recommended,data,target=plan.target,backup=plan.backup))
    holds=tuple(recommended.bench[index].unit_id for category,_,index in priorities if index in kept and index not in sales and category<4)
    if holds:
        advice.append(Advice('transition','Hold flexible bench units','information',value.confidence,'bench_priority',{},('board','bench','round'),decision_id=f'{snapshot.snapshot_id}:transition:hold',option_id='transition:hold',payload={'hold':holds},validity_state=validity))
    if sales:
        advice.append(Advice('transition','Sell bench units, roll' if rolling else 'Sell bench overflow','act_this_phase',value.confidence,'bench_priority',{},('board','bench','round'),decision_id=f'{snapshot.snapshot_id}:transition:sell',option_id='transition:sell',payload={'sell':tuple(recommended.bench[i].unit_id for i in sorted(sales)),'reason':'roll_gold' if rolling else 'bench_overflow'},validity_state=validity))
    return tuple(advice)
