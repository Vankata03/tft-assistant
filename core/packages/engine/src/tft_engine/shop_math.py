"""Closed-form absorbing shop chain; pool depletion includes owned and inferred copies only."""
from math import floor
import numpy as np
from .power import static, keyed
from tft_data.models import DataError


def canonical_id(unit_id,data):
    entity=data.entities[unit_id]
    value=entity.values.get('pool_id') or entity.values.get('canonical_id')
    return str(value.value) if value else unit_id


def owned_copies(board,data=None):
    result={}
    for unit in board.units+board.bench:
        id=canonical_id(unit.unit_id,data) if data is not None else unit.unit_id
        result[id]=result.get(id,0)+(1,3,9)[unit.stars-1]
    return result


def key_goals(guide,data=None):
    stars={id:2 for id in set(guide.carry_ids)|set(getattr(guide,'key_ids',()))}
    for point in guide.line:
        stars.update(point.get('target_stars',{}))
    return {(canonical_id(id,data) if data is not None else id):(1,3,9)[int(star)-1] for id,star in stars.items()}


def hit_probability(unit_id,copies_needed,shops,slots,level,data,*,owned=None,contested=None):
    if copies_needed<=0:
        return 1.0
    if shops<=0 or slots<=0:
        return 0.0
    unit_id=canonical_id(unit_id,data)
    owned,contested=owned or {},contested or {}
    cost=data.entities[unit_id].cost
    odds=keyed(static(data,'shop_odds'),level)
    pool=float(keyed(static(data,'pool_sizes'),cost))
    roster=[id for id,e in data.entities.items() if e.kind=='unit' and e.cost==cost]
    total=sum(max(0,pool-owned.get(id,0)-contested.get(id,0)) for id in roster)
    available=max(0,pool-owned.get(unit_id,0)-contested.get(unit_id,0))
    transition=np.zeros((copies_needed+1,copies_needed+1))
    for acquired in range(copies_needed):
        denominator=total-acquired
        chance=float(odds[cost-1])*max(0,available-acquired)/denominator if denominator>0 else 0.0
        transition[acquired,acquired]=1-chance
        transition[acquired,acquired+1]=chance
    transition[-1,-1]=1
    whole=floor(slots); fraction=slots-whole
    shop=np.linalg.matrix_power(transition,whole)@((1-fraction)*np.eye(len(transition))+fraction*transition)
    result=np.linalg.matrix_power(shop,int(shops))[0,-1]
    return float(result)
