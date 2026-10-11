"""Greedy strongest-owned selection followed by strict swap improvement."""
from .models import Board, Advice
from .power import strength, tunable, static, estimate_strength, stage_tunable
from .lines import guide_line
from .opponents import round_index
from .shop_math import canonical_id


def main_roll_down(guide,data):
    rolls=guide_line(guide,data).rolls
    return min(rolls,key=lambda r:round_index(r,data)) if rolls else None


def strongest_owned_board(board,level,data,*,target=None,round_id=None):
    units=board.units+board.bench
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
        selected=tuple(units[i] for i in sorted(indices))
        counts=board.trait_counts if selected==board.units else None
        return Board(selected,tuple(units[i] for i in range(len(units)) if i not in indices),counts)
    def score(indices):
        return strength(candidate(indices),level,data)
    selected=[]
    available=list(range(len(units)))
    if forced:
        # Comp membership outranks power only after the explicit Guide deadline.
        required=[i for i in available if canonical_id(units[i].unit_id,data) in target_pools]
        required.sort(key=lambda i:(-progress([i]),-score([i]),i))
        selected=required[:level]
    while len(selected)<min(level,len(units)):
        possibilities=[i for i in available if i not in selected]
        evaluated=[(score(selected+[i]),progress(selected+[i]),i) for i in possibilities]
        maximum=max(v[0] for v in evaluated)
        eligible=[v for v in evaluated if v[0]>=maximum-tolerance]
        chosen=max(eligible,key=lambda v:(v[1],v[0],-v[2]))
        selected.append(chosen[2])
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
                proposal=[i for i in selected if i!=old]+[new]
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
    current=read(snapshot,data,'board')
    old=list(current.units); new=list(recommended.units)
    for unit in tuple(old):
        if unit in new:
            old.remove(unit); new.remove(unit)
    value=estimate_strength(recommended,int(read(snapshot,data,'level')),data)
    validity={'round':snapshot.round_id,'board':current.to_dict()}
    advice=[]
    if old or new:
        advice.append(Advice('transition','Swap owned units','act_this_phase',value.confidence,'strongest_owned_board',{'power':value.power},('board','bench','round'),decision_id=f'{snapshot.snapshot_id}:transition',option_id='transition',payload={'swap_out':[u.unit_id for u in old],'swap_in':[u.unit_id for u in new],'board':recommended.to_dict()},validity_state=validity))
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
