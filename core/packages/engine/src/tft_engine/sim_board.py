"""Prepared absolute power tables and vectorized greedy board selection for rollouts."""
from dataclasses import dataclass
import numpy as np
from tft_data.models import DataError
from .power import unit_power, trait_term, tunable, estimate_strength
from .opponents import unit_trait_variants
from .shop_math import owned_copies, canonical_id

class RolloutBoard:
    def __init__(self,board,data,guide):
        self.data=data
        self._power_cache={}
        self.ids=tuple(sorted(id for id,e in data.entities.items() if e.kind=='unit'))
        forms={}
        for unit in board.units+board.bench:
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
        self.initial=np.array([owned_copies(board,data).get(id,0) for id in self.ids],dtype=int)
        self.items=estimate_strength(board,len(board.units),data).item_term
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

    def power(self,copies,level,*,forced=False):
        # Identical owned-copy/level states have identical greedy outcomes. Memoize
        # them within this request; individual shops, fights and HP still vary.
        packed=np.ascontiguousarray(np.column_stack((copies,level)))
        signature=packed.view(np.dtype((np.void,packed.dtype.itemsize*packed.shape[1]))).reshape(-1)
        _,indices,inverse=np.unique(signature,return_index=True,return_inverse=True)
        states=packed[indices]
        keys=[(state.tobytes(),forced) for state in states]
        missing=[i for i,key in enumerate(keys) if key not in self._power_cache]
        if missing:
            fresh=states[missing]
            values=self._power(fresh[:,:-1],fresh[:,-1],forced=forced)
            self._power_cache.update((keys[i],float(value)) for i,value in zip(missing,values))
        return np.array([self._power_cache[key] for key in keys])[inverse]

    def _power(self,copies,level,*,forced=False):
        n=len(copies); rows=np.arange(n)
        # Auto-combines are exact: nine ->3-star, remaining threes ->2-star, remainder ->1-star.
        high=copies//9; rest=copies%9; middle=rest//3; low=rest%3
        available=np.stack((low,middle,high),axis=2).copy()
        counts=np.zeros((n,len(self.traits)),dtype=int)
        seen=np.zeros((n,len(self.ids)),dtype=bool)
        total=np.full(n,self.items)
        for slot in range(int(max(level))):
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
            within=(scores>=maximum[:,None]-float(tunable(self.data,'transition_tolerance')))&eligible
            preference=np.where(within,self.progress[None,:],-np.inf)
            priorities=preference.max(axis=1)
            chosen=np.argmax(np.where(within&(preference==priorities[:,None]),scores,-np.inf),axis=1)
            valid=(slot<level)&exists.any(axis=1)
            tier=best_tier[rows,chosen]
            total+=np.where(valid,scores[rows,chosen],0)
            add=valid&~seen[rows,chosen]
            counts+=add[:,None]*self.contributions[chosen]
            seen[rows,chosen]|=valid
            available[rows,chosen,tier]-=valid
        return total
