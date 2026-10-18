"""Prepared power tables and cached greedy-plus-swap selection for rollouts."""
from dataclasses import dataclass
import numpy as np
from tft_data.models import DataError
from .power import unit_power, trait_term, tunable, estimate_strength, stage_tunable
from .trait_forms import unit_trait_variants
from .shop_math import owned_copies, canonical_id

_ROW_MULTIPLIERS=np.random.default_rng(0x524F5753).integers(1,2**63,4096,dtype=np.uint64)|np.uint64(1)


def _distinct_rows(packed):
    """Group identical integer rows. A hash only proposes groups; every row is
    compared with its representative, and any collision uses exact byte grouping."""
    if packed.dtype.kind in 'iub' and packed.shape[1]<=len(_ROW_MULTIPLIERS):
        hashes=packed.astype(np.uint64)@_ROW_MULTIPLIERS[:packed.shape[1]]
        _,indices,inverse=np.unique(hashes,return_index=True,return_inverse=True)
        if (packed==packed[indices][inverse]).all():
            return indices,inverse
    signature=packed.view(np.dtype((np.void,packed.dtype.itemsize*packed.shape[1]))).reshape(-1)
    _,indices,inverse=np.unique(signature,return_index=True,return_inverse=True)
    return indices,inverse


class RolloutBoard:
    def __init__(self,board,data,guide,*,level,capacity=None):
        self.data=data
        from .capacity import CapacityModel
        self.capacity_model=CapacityModel(data)
        self.capacity=capacity
        self.guide=guide
        self.observed_units=board.units
        self.equipment_groups=tuple((i,u) for i,u in enumerate(board.units+board.bench) if u.items)
        self._power_cache={}
        self.ids=tuple(sorted(id for id,e in data.entities.items() if e.kind=='unit'))
        forms={}
        for unit in board.units+board.bench:
            if len(unit_trait_variants(unit.unit_id,data))!=1:
                raise DataError(f'Rollout requires resolved own trait form: {unit.unit_id}')
            pool=canonical_id(unit.unit_id,data)
            if unit.unit_id!=pool:
                if pool in forms and forms[pool]!=unit.unit_id:
                    raise DataError(f'Conflicting active forms share one pool: {pool}')
                forms[pool]=unit.unit_id
        for id in guide.units:
            pool=canonical_id(id,data)
            if pool!=id and pool not in forms:
                forms[pool]=id
        self.active_ids=tuple(forms.get(id,id) for id in self.ids)
        self.slot_costs=tuple(self.capacity_model.cost(id) for id in self.active_ids)
        self.general_capacity=(any(cost!=1 for cost in self.slot_costs) or bool(self.capacity_model.traits) or bool(self.capacity_model.augments) or bool(self.capacity_model.items))
        self.index={id:i for i,id in enumerate(self.ids)}
        self.costs=np.array([data.entities[id].cost for id in self.ids])
        estimates=[[unit_power(id,s,data) for s in (1,2,3)] for id in self.active_ids]
        self.confidence=min(value[1] for row in estimates for value in row)
        self.powers=np.asarray([[value[0]*float(tunable(data,'unit_weight')) for value in row] for row in estimates])
        self.traits=tuple(sorted({t for id in self.active_ids for variant in unit_trait_variants(id,data) for t in variant}))
        self.contributions=np.zeros((len(self.ids),len(self.traits)),dtype=int)
        self.supported=np.ones(len(self.ids),dtype=bool)
        target_pools={canonical_id(id,data) for id in guide.units}
        held=owned_copies(board,data)
        for ui,id in enumerate(self.active_ids):
            variants=unit_trait_variants(id,data)
            if len(variants)!=1:
                pool=self.ids[ui]
                if held.get(pool,0) or pool in target_pools:
                    raise DataError(f'Rollout requires resolved own trait form: {id}')
                self.supported[ui]=False
                continue
            self.contributions[ui]=[variants[0].get(t,0) for t in self.traits]
        self.trait_values=[]
        for t in self.traits:
            points=data.entities[t].values['breakpoints'].value
            self.trait_values.append(tuple((int(p),trait_term({t:int(p)},data)[0]*float(tunable(data,'trait_weight'))) for p in points))
        self.initial=np.array([held.get(id,0) for id in self.ids],dtype=int)
        self.items=estimate_strength(board,level,data,capacity=capacity).item_term
        self.target=np.array([id in target_pools for id in self.ids])
        weights=tunable(data,'classifier_weights')
        carries={canonical_id(id,data) for id in guide.carry_ids}
        keys={canonical_id(id,data) for id in getattr(guide,'key_ids',())}
        self.progress=np.array([float(weights['carry'] if id in carries else weights['key'] if id in keys else weights['other']) if id in target_pools else 0 for id in self.ids])

    def traits_power(self,counts):
        result=np.zeros(counts.shape[:-1])
        for ti,points in enumerate(self.trait_values):
            value=np.zeros_like(result)
            for threshold,power in points:
                value=np.where(counts[...,ti]>=threshold,power,value)
            result+=value
        return result

    def power(self,copies,level,*,forced=False,equipment_retained=None,round_id=None):
        # Identical owned-copy/level states have identical greedy outcomes. Memoize
        # them within this request; individual shops, fights and HP still vary.
        if equipment_retained is None:
            equipment_retained=np.ones((len(copies),len(self.equipment_groups)),dtype=int)
        packed=np.ascontiguousarray(np.column_stack((copies,level,equipment_retained)))
        indices,inverse=_distinct_rows(packed)
        states=packed[indices]
        keys=[(state.tobytes(),forced,round_id.split('-')[0] if round_id else None) for state in states]
        missing=[i for i,key in enumerate(keys) if key not in self._power_cache]
        if missing:
            fresh=states[missing]
            width=len(self.ids)
            values=self._power(fresh[:,:width],fresh[:,width],forced=forced,equipment_retained=fresh[:,width+1:],round_id=round_id)
            self._power_cache.update((keys[i],float(value)) for i,value in zip(missing,values))
        return np.array([self._power_cache[key] for key in keys])[inverse]

    def _power(self,copies,level,*,forced=False,equipment_retained=None,round_id=None):
        if self.general_capacity:
            from dataclasses import replace
            from .models import Board, Unit
            from .transition import strongest_owned_board, main_roll_down
            result=[]
            for amounts,slots,retained in zip(copies,level,equipment_retained):
                owned=[]
                loose=list(self.capacity.item_bench or ()) if self.capacity else []
                equipped={}
                for keep,(_,unit) in zip(retained,self.equipment_groups):
                    pool=canonical_id(unit.unit_id,self.data)
                    if keep:
                        equipped[pool]=equipped.get(pool,())+unit.items
                    else:
                        loose.extend(unit.items)
                for id,amount in zip(self.active_ids,amounts):
                    high,rest=divmod(int(amount),9);middle,low=divmod(rest,3)
                    first=len(owned)
                    for star,quantity in ((3,high),(2,middle),(1,low)):
                        owned.extend(Unit(id,star) for _ in range(quantity))
                    equipment=equipped.get(canonical_id(id,self.data),())
                    if equipment:
                        if len(owned)==first:
                            # A sale returns that holder's equipment to inventory;
                            # equipped scopes disappear, owned scope remains.
                            loose.extend(equipment)
                        else:
                            limit=self.data.value('rules_flags').get('item_slots_max')
                            if limit is None:
                                raise DataError('Rollout equipment merge capacity requires sourced item slots and overflow handling')
                            from .capacity import integral
                            integral(limit,'equipment slots',1)
                            if len(equipment)>limit:
                                raise DataError('Rollout equipment merge capacity requires sourced item slots and overflow handling')
                            owned[first]=replace(owned[first],items=equipment)
                evidence=replace(self.capacity,item_bench=tuple(loose)) if self.capacity else None
                # Preserve observed deployed identities when still owned. An
                # already legal self-supporting trait board cannot be rebuilt
                # as though its active capacity vanished between frames.
                anchor=[];remaining=list(owned)
                for old in self.observed_units:
                    match=next((u for u in remaining if canonical_id(u.unit_id,self.data)==canonical_id(old.unit_id,self.data)),None)
                    if match is not None:
                        anchor.append(match);remaining.remove(match)
                anchored=Board(tuple(anchor),tuple(remaining))
                if self.capacity_model.state(anchored,int(slots),evidence).occupied_slots>self.capacity_model.budget(anchored,int(slots),evidence):
                    raise DataError('Rollout owned-state change collapses deployed capacity; sourced overflow rule unavailable')
                selected=strongest_owned_board(anchored,int(slots),self.data,
                    target=self.guide.id if forced else None,
                    round_id=round_id,
                    capacity=evidence,generic_item_power=self.items)
                estimate=estimate_strength(selected,int(slots),self.data,capacity=evidence)
                result.append(estimate.unit_term+estimate.trait_term+self.items)
            return np.asarray(result)
        n=len(copies); rows=np.arange(n)
        # Auto-combines are exact: nine ->3-star, remaining threes ->2-star, remainder ->1-star.
        high=copies//9; rest=copies%9; middle=rest//3; low=rest%3
        available=np.stack((low,middle,high),axis=2).copy()
        selected=np.zeros_like(available)
        counts=np.zeros((n,len(self.traits)),dtype=int)
        seen=np.zeros((n,len(self.ids)),dtype=bool)
        total=np.full(n,self.items)
        budgets=np.minimum(28,np.asarray([self.capacity_model.base(int(value)) for value in level]))
        for slot in range(int(max(budgets))):
            best_tier=np.argmax(np.where(available>0,self.powers[None,:,:],-np.inf),axis=2)
            unit_values=np.take_along_axis(np.broadcast_to(self.powers,(n,)+self.powers.shape),best_tier[:,:,None],axis=2)[:,:,0]
            absent=~seen
            proposed=counts[:,None,:]+absent[:,:,None]*self.contributions[None,:,:]
            delta=self.traits_power(proposed)-self.traits_power(counts)[:,None]
            scores=unit_values+delta
            exists=available.sum(axis=2)>0
            eligible=exists.copy()
            if forced:
                preferred=exists&self.target[None,:]
                eligible=np.where(preferred.any(axis=1)[:,None],preferred,eligible)
            scores=np.where(eligible,scores,-np.inf)
            maximum=scores.max(axis=1)
            within=(scores>=maximum[:,None]-stage_tunable(self.data,'transition_tolerance',round_id))&eligible
            preference=np.where(within,self.progress[None,:],-np.inf)
            priorities=preference.max(axis=1)
            chosen=np.argmax(np.where(within&(preference==priorities[:,None]),scores,-np.inf),axis=1)
            if forced:
                # The deadline forces target members in carry/key/other order,
                # matching transition's initial forced subset before greedy fill.
                forced_progress=np.where(preferred,self.progress[None,:],-np.inf)
                priority=forced_progress.max(axis=1)
                solo=unit_values+self.traits_power(self.contributions)[None,:]
                forced_choice=np.argmax(np.where(preferred&(forced_progress==priority[:,None]),solo,-np.inf),axis=1)
                chosen=np.where(preferred.any(axis=1),forced_choice,chosen)
            valid=(slot<budgets)&exists.any(axis=1)
            tier=best_tier[rows,chosen]
            total+=np.where(valid,scores[rows,chosen],0)
            add=valid&~seen[rows,chosen]
            counts+=add[:,None]*self.contributions[chosen]
            seen[rows,chosen]|=valid
            available[rows,chosen,tier]-=valid
            selected[rows,chosen,tier]+=valid
        return self._refine(selected,available,forced=forced,round_id=round_id)

    def _refine(self,selected,available,*,forced,round_id):
        """Batch every one-unit swap; reuse the transition's strict improvement rule."""
        n=len(selected); rows=np.arange(n)
        tolerance=stage_tunable(self.data,'transition_tolerance',round_id)
        seen=[{state.tobytes()} for state in selected]
        def score():
            present=selected.sum(axis=2)>0
            return (selected*self.powers[None,:,:]).sum(axis=(1,2))+self.traits_power(present@self.contributions)+self.items
        current=score(); anchor=current.copy()
        while True:
            quantities=selected.sum(axis=2)
            counts=(quantities>0)@self.contributions
            progress=(quantities*self.progress).sum(axis=1)
            tiers=np.argmax(np.where(available>0,self.powers[None,:,:],-np.inf),axis=2)
            new_power=np.take_along_axis(np.broadcast_to(self.powers,(n,)+self.powers.shape),tiers[:,:,None],axis=2)[:,:,0]
            exists=available.sum(axis=2)>0
            best_priority=np.full(n,-np.inf); best_value=np.full(n,-np.inf)
            old_choice=np.full(n,-1); old_tier=np.zeros(n,dtype=int); new_choice=np.zeros(n,dtype=int)
            for old,tier in np.argwhere(selected.any(axis=0)):
                if forced and self.target[old]:
                    continue
                removing=selected[:,old,tier]>0
                after=counts-(quantities[:,old]==1)[:,None]*self.contributions[old]
                remaining=quantities.copy(); remaining[:,old]-=1
                proposed=after[:,None,:]+(remaining==0)[:,:,None]*self.contributions[None,:,:]
                values=current[:,None]-self.powers[old,tier]+new_power+self.traits_power(proposed)-self.traits_power(counts)[:,None]
                towards=progress[:,None]-self.progress[old]+self.progress[None,:]
                improves=(values>current[:,None]+tolerance)|((values>=anchor[:,None]-tolerance)&(towards>progress[:,None]))
                eligible=removing[:,None]&exists&improves
                priorities=np.where(values>=current[:,None]-tolerance,towards,-1)
                priorities=np.where(eligible,priorities,-np.inf)
                maximum=priorities.max(axis=1)
                chosen=np.argmax(np.where(eligible&(priorities==maximum[:,None]),values,-np.inf),axis=1)
                candidate_value=values[rows,chosen]
                better=(maximum>best_priority)|((maximum==best_priority)&(candidate_value>best_value))
                better&=eligible[rows,chosen]
                for row in np.flatnonzero(better):
                    proposal=selected[row].copy(); proposal[old,tier]-=1; proposal[chosen[row],tiers[row,chosen[row]]]+=1
                    if proposal.tobytes() in seen[row]:
                        better[row]=False
                best_priority=np.where(better,maximum,best_priority)
                best_value=np.where(better,candidate_value,best_value)
                old_choice=np.where(better,old,old_choice)
                old_tier=np.where(better,tier,old_tier)
                new_choice=np.where(better,chosen,new_choice)
            changing=np.flatnonzero(old_choice>=0)
            if not len(changing):
                return current
            for row in changing:
                old=old_choice[row]; tier=old_tier[row]; new=new_choice[row]; incoming=tiers[row,new]
                selected[row,old,tier]-=1; available[row,old,tier]+=1
                selected[row,new,incoming]+=1; available[row,new,incoming]-=1
                seen[row].add(selected[row].tobytes())
            current=score(); anchor=np.maximum(anchor,current)
