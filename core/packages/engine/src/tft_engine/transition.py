"""Greedy strongest-owned selection followed by strict swap improvement."""
from .models import Board, Advice
from .power import strength, tunable, estimate_strength
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
    tolerance=float(tunable(data,'transition_tolerance'))
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
                if value>current+tolerance or (value>=current-tolerance and towards>current_progress):
                    choice=(towards if value>=current-tolerance else -1,value,key,proposal)
                    if best is None or choice[:3]>best[:3]:
                        best=choice
        if best is None:
            break
        selected=best[3]; seen.add(tuple(sorted(selected)))
    return candidate(selected)


def transition_advice(snapshot,recommended,plan,data):
    current=snapshot.field('board')
    old=list(current.units); new=list(recommended.units)
    for unit in tuple(old):
        if unit in new:
            old.remove(unit); new.remove(unit)
    if not old and not new:
        return ()
    value=estimate_strength(recommended,int(snapshot.field('level')),data)
    return (Advice('transition','Swap owned units','act_this_phase',value.confidence,'strongest_owned_board',{'power':value.power},('board','bench','round'),decision_id=f'{snapshot.snapshot_id}:transition',option_id='transition',payload={'swap_out':[u.unit_id for u in old],'swap_in':[u.unit_id for u in new],'board':recommended.to_dict()},validity_state={'round':snapshot.round_id,'board':current.to_dict()}),)
