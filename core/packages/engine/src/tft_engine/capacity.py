"""Sourced team-slot legality; unit count and hex positions are separate facts."""
from collections.abc import Mapping
from dataclasses import dataclass
from tft_data.models import DataError, TaggedValue
from tft_data.capacity import integral, validate_capacity, unit_slot_cost



@dataclass(frozen=True)
class CapacityState:
    physical_units: int
    occupied_slots: int
    maximum_slots: int
    def to_dict(self):
        return dict(physical_units=self.physical_units,occupied_slots=self.occupied_slots,maximum_slots=self.maximum_slots)


@dataclass(frozen=True)
class CapacityEvidence:
    held_augments: tuple | None = None
    item_bench: tuple | None = None
    observed_budget: int | None = None
    def __post_init__(self):
        for name in ('held_augments','item_bench'):
            value=getattr(self,name)
            if value is not None:
                if not isinstance(value,(tuple,list)) or any(not isinstance(id,str) for id in value):
                    raise DataError(f'Invalid capacity inventory: {name}')
                object.__setattr__(self,name,tuple(value))
        if self.observed_budget is not None:
            integral(self.observed_budget,'observed team slot budget',1)


class CapacityModel:
    def __init__(self,data):
        self.data=data
        self.rules=validate_capacity(data.static,data.entities)
        self.levels=self.rules['levels'];self.traits=self.rules['trait_bonuses']
        self.augments=self.rules['held_augment_slots'];self.items=self.rules['inventory_item_slots']

    def cost(self,unit_id):
        return unit_slot_cost(self.data.entities,unit_id)

    def base(self,level):
        integral(level,'level',1)
        value=self.levels.get(str(level))
        if value is None:
            raise DataError(f'Team slot budget unavailable at level {level}')
        return value

    def trait_bonus(self,counts):
        by_trait={}
        for rule in self.traits:
            if counts.get(rule['trait_id'],0)>=rule['breakpoint']:
                old=by_trait.get(rule['trait_id'])
                if old is None or rule['breakpoint']>old['breakpoint']:
                    by_trait[rule['trait_id']]=rule
        return sum(rule['slots'] for rule in by_trait.values())

    def counts(self,board):
        if not self.traits:
            return {}
        from .trait_forms import unit_trait_variants
        counts={}
        pools={}
        for unit_id in sorted({u.unit_id for u in board.units}):
            entity=self.data.entities[unit_id]
            pool=entity.values.get('pool_id') or entity.values.get('canonical_id')
            identity=pool.value if pool else unit_id
            if identity in pools and pools[identity]!=unit_id:
                raise DataError('Conflicting own trait forms share a capacity identity')
            pools[identity]=unit_id
            variants=unit_trait_variants(unit_id,self.data)
            if len(variants)!=1:
                raise DataError('Capacity requires a resolved own trait form')
            for trait,count in variants[0].items():
                counts[trait]=counts.get(trait,0)+count
        for unit in board.units:
            for identity in unit.items:
                entity=self.data.entities.get(identity)
                tagged=entity.values.get('trait_grants') if entity else None
                if not isinstance(tagged,TaggedValue) or not isinstance(tagged.value,Mapping):
                    raise DataError(f'Capacity item trait-grant certificate unavailable: {identity}')
                for trait,count in tagged.value.items():
                    integral(count,'item trait grant',1)
                    if trait not in self.data.entities or self.data.entities[trait].kind!='trait':
                        raise DataError('Unknown capacity item trait grant')
                    counts[trait]=counts.get(trait,0)+count
        observed=getattr(board,'trait_counts',None)
        if observed is not None:
            for trait in {rule['trait_id'] for rule in self.traits}:
                integral(observed.get(trait,0),'observed capacity trait count')
                if observed.get(trait,0)!=counts.get(trait,0):
                    raise DataError('Observed trait capacity conflicts with certified current units and grants')
        return counts

    def budget(self,board,level,evidence=None):
        evidence=evidence or CapacityEvidence()
        value=self.base(level)+self.trait_bonus(self.counts(board))
        if self.augments:
            if evidence.held_augments is None:
                raise DataError('Complete held augments required for capacity')
            if any(id not in self.data.entities or self.data.entities[id].kind!='augment' for id in evidence.held_augments):
                raise DataError('Unknown held augment capacity inventory')
            value+=sum(self.augments[id]['slots'] for id in set(evidence.held_augments) if id in self.augments)
        if self.items:
            if evidence.item_bench is None:
                raise DataError('Complete item inventory required for capacity')
            if any(id not in self.data.entities or self.data.entities[id].kind!='item' for id in evidence.item_bench):
                raise DataError('Unknown loose item capacity inventory')
            for identity,rule in self.items.items():
                deployed=sum(u.items.count(identity) for u in board.units)
                equipped=deployed+sum(u.items.count(identity) for u in getattr(board,'bench',()))
                owned=equipped+evidence.item_bench.count(identity)
                quantity={'owned':owned,'equipped_anywhere':equipped,'deployed_equipment':deployed}[rule['scope']]
                value+=rule['slots']*quantity
        return value

    def state(self,board,level,evidence=None):
        slots=sum(self.cost(u.unit_id) for u in board.units)
        return CapacityState(len(board.units),slots,self.budget(board,level,evidence))

    def check(self,board,level,evidence=None,*,check_observed=False):
        state=self.state(board,level,evidence)
        positions=[getattr(u,'position',None) for u in board.units if getattr(u,'position',None) is not None]
        if len(board.units)>28 or len(set(positions))!=len(positions) or any(isinstance(p,bool) or not isinstance(p,int) or not 0<=p<28 for p in positions):
            raise DataError('Board has invalid physical hex positions')
        if state.occupied_slots>state.maximum_slots:
            raise DataError(f'Board occupies {state.occupied_slots} team slots; budget is {state.maximum_slots}')
        if check_observed and evidence and evidence.observed_budget is not None and evidence.observed_budget!=state.maximum_slots:
            raise DataError('Observed team slot budget conflicts with sourced capacity model')
        return state

    def transition(self,board,recommended,level,evidence=None):
        """Prove a legal indexed sequence, preserving duplicate physical units."""
        from collections import deque
        from dataclasses import replace
        from .models import Board
        units=board.units+board.bench
        start=frozenset(range(len(board.units)))
        unmatched=list(range(len(units)));target=[]
        for unit in recommended.units:
            exact=[i for i in unmatched if units[i]==unit]
            moved=[i for i in unmatched if i>=len(board.units) and replace(units[i],position=None)==unit]
            match=(exact or moved or [None])[0]
            if match is None:
                raise DataError('Transition is not an owned-unit rearrangement')
            unmatched.remove(match);target.append(match)
        target=frozenset(target)
        bench_tag=self.data.static.get('bench_size')
        if not isinstance(bench_tag,TaggedValue):
            raise DataError('Sourced bench capacity unavailable')
        bench_limit=integral(bench_tag.value,'bench capacity',1)
        def candidate(indices):
            return Board(tuple(units[i] if i<len(board.units) else replace(units[i],position=None) for i in sorted(indices)),tuple(units[i] for i in range(len(units)) if i not in indices))
        def state(indices):
            value=self.check(candidate(indices),level,evidence).to_dict()
            value['bench_units']=len(units)-len(indices)
            if value['bench_units']>bench_limit:
                raise DataError('Transition exceeds sourced bench capacity')
            return value
        state(start);state(target)
        if start==target:
            return ()
        tagged=self.data.tunables.get('capacity_transition_state_cap')
        if not isinstance(tagged,TaggedValue):
            raise DataError('Capacity transition search budget unavailable')
        cap=integral(tagged.value,'capacity transition search budget',1)
        pending=deque([start]);paths={start:()}
        while pending:
            current=pending.popleft();before=state(current)
            deployed=sorted(current);benched=sorted(set(range(len(units)))-current)
            moves=[('bench',old,None) for old in deployed]
            moves += [('deploy',None,new) for new in benched]
            moves += [('swap',old,new) for old in deployed for new in benched]
            for operation,old,new in moves:
                remaining=current-({old} if old is not None else set())
                proposed=frozenset(remaining|({new} if new is not None else set()))
                if proposed in paths:
                    continue
                try:
                    # A swap reuses the incoming unit's bench slot. Capacity
                    # activation is evaluated after removal, before deployment.
                    interim=self.check(candidate(remaining),level,evidence)
                    if new is not None and interim.occupied_slots+self.cost(units[new].unit_id)>interim.maximum_slots:
                        continue
                    after=state(proposed)
                except DataError:
                    continue
                step={'operation':operation,'out_index':old,'in_index':new,
                    'out_unit_id':units[old].unit_id if old is not None else None,
                    'in_unit_id':units[new].unit_id if new is not None else None,
                    'before':before,'after':after}
                path=paths[current]+(step,)
                if proposed==target:
                    return path
                if len(paths)>=cap:
                    raise DataError('Capacity transition search budget exhausted; executable sequence unavailable')
                paths[proposed]=path;pending.append(proposed)
        raise DataError('No legal owned-board capacity transition')
