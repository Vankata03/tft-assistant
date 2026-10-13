"""Only explicit sourced fields and positively observed remaining counters enter simulation."""
from .planning import read
from dataclasses import fields
from collections.abc import Mapping
from math import isfinite
from .lines import SimulationEffects
from .power import static
from tft_data.models import DataError


def add_maps(left,right):
    result=dict(left)
    for key,value in right.items():
        result[key]=add_maps(result.get(key,{}),value) if isinstance(value,Mapping) else result.get(key,0)+value
    return result


def combine(base,extra):
    if base is None:
        return extra
    if extra is None:
        return base
    values={}
    for field in fields(SimulationEffects):
        a,b=getattr(base,field.name),getattr(extra,field.name)
        values[field.name]=(b if b is not None else a) if field.name in ('item_state','item_bench_state') else add_maps(a,b) if isinstance(a,Mapping) else a+b
    return SimulationEffects(**values)


def simulation(effect,data,snapshot=None,*,remaining=None):
    kind=effect['effect_kind']; values=dict(effect['values']); output={}
    duration=values.pop('duration_rounds',None); scope=values.pop('scope',None)
    if kind=='gold':
        keys={'gold':'gold_delta','gold_per_round':'gold_per_round'}
    elif kind=='xp':
        keys={'xp':'xp_delta','xp_per_round':'xp_per_round'}
    elif kind=='rolls':
        keys={'rolls':'free_rolls','roll_cost_delta':'roll_cost_delta'}
    elif kind=='shop':
        keys={'shop_slots_delta':'shop_slots_delta','roll_cost_delta':'roll_cost_delta'}
    elif kind=='sale_modifier':
        keys={'sale_gold_by_cost_star':'sale_gold_by_cost_star'}
    elif kind=='combat_buff':
        if scope not in (None,'current_round') or (duration is not None and (isinstance(duration,bool) or not isinstance(duration,int) or duration!=1)):
            raise DataError('Combat buff duration/scope has no supported single-round model')
        if remaining is not None:
            if set(remaining) != {'remaining_rounds'} or remaining['remaining_rounds'] not in (0,1):
                raise DataError('Combat buff requires an observed current-round duration of zero or one')
            if remaining['remaining_rounds']==0:
                return SimulationEffects()
        if set(values) != {'buff_id'}:
            raise DataError('Combat buff fields unavailable or unsupported')
        id=values.get('buff_id')
        if id not in static(data,'combat_buff_power'):
            raise DataError(f'Combat buff power unavailable: {id}')
        power=static(data,'combat_buff_power')[id]
        if isinstance(power,bool) or not isinstance(power,(int,float)) or not isfinite(power):
            raise DataError(f'Combat buff power invalid: {id}')
        return SimulationEffects(one_round_power_bonus=float(power))
    else:
        raise DataError(f'Effect has no simulation model: {kind}')
    if not values or set(values)-keys.keys():
        raise DataError(f'Effect fields unavailable or unsupported: {kind}')
    if remaining is not None:
        # Initial rewards are already in the captured gold/XP/ownership. Only
        # free-roll balances and positively counted future rounds remain active.
        values.pop('gold',None); values.pop('xp',None); values.pop('rolls',None)
        if 'remaining_rolls' in remaining:
            if kind!='rolls' or 'rolls' not in effect['values']:
                raise DataError('Remaining rolls counter does not match the sourced effect')
            output['free_rolls']=remaining['remaining_rolls']
        duration=remaining.get('remaining_rounds')
        if ('remaining_gold' in remaining or 'remaining_xp' in remaining):
            raise DataError('Remaining gold/XP payout timing requires a sourced model')
    recurring={name:values.pop(name) for name in tuple(values) if name in ('gold_per_round','xp_per_round')}
    if recurring:
        if duration is not None:
            if not isinstance(duration,int) or isinstance(duration,bool) or duration<0 or snapshot is None:
                raise DataError('Recurring effect requires a positive observed duration and snapshot')
            rounds=tuple(static(data,'round_order')); index=rounds.index(snapshot.round_id)
            output['round_income']={round:{'gold':recurring.get('gold_per_round',0),'xp':recurring.get('xp_per_round',0)} for round in rounds[index:index+duration]}
        elif scope=='rest_of_game' and remaining is None:
            output.update(recurring)
        else:
            raise DataError('Recurring effect remaining duration unavailable')
    modifiers={name:values.pop(name) for name in tuple(values) if name in ('roll_cost_delta','shop_slots_delta','sale_gold_by_cost_star')}
    if modifiers:
        if duration is not None:
            if not isinstance(duration,int) or isinstance(duration,bool) or duration<0 or snapshot is None:
                raise DataError('Modifier requires observed duration and snapshot')
            rounds=tuple(static(data,'round_order')); index=rounds.index(snapshot.round_id)
            output['round_modifiers']={round:modifiers for round in rounds[index:index+duration]}
        elif scope=='rest_of_game' and remaining is None:
            output.update(modifiers)
        else:
            raise DataError('Modifier remaining duration unavailable')
    output.update({keys[name]:amount for name,amount in values.items()})
    for name,value in output.items():
        if not isinstance(value,Mapping) and (isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value)):
            raise DataError(f'Effect numeric field invalid: {name}')
    def validate(value):
        if isinstance(value,Mapping):
            return all(validate(child) for child in value.values())
        return not isinstance(value,bool) and isinstance(value,(int,float)) and isfinite(value)
    if not all(validate(value) for value in output.values()):
        raise DataError('Effect contains an invalid numeric table')
    return SimulationEffects(**output)


def captured(snapshot,data):
    held=read(snapshot,data,'held_augments')
    recurring=set()
    econ=static(data,'econ_augments') if 'econ_augments' in data.static else {}
    for id in held or ():
        record=econ.get(id)
        if record and (record['effect_kind'] in ('sale_modifier','combat_buff') or any(key in record['values'] for key in ('gold_per_round','xp_per_round','roll_cost_delta','shop_slots_delta'))):
            recurring.add(id)
    projected=snapshot.fields.get('projected_effect_ids')
    if projected is not None and projected.source=='choice':
        recurring-=set(read(snapshot,data,'projected_effect_ids') or ())
    rows=read(snapshot,data,'remaining_effects')
    if recurring and (rows is None or read(snapshot,data,'remaining_effects_complete') is not True):
        raise DataError('Positive complete remaining econ effects required')
    if rows is None:
        return None
    if read(snapshot,data,'remaining_effects_complete') is not True:
        raise DataError('Remaining effect inventory is incomplete')
    result=None; seen=set()
    tables={'augment':econ,'wisp':static(data,'wisps') if 'wisps' in data.static else {},
        'opening_encounter':static(data,'opening_encounters') if 'opening_encounters' in data.static else {}}
    for row in rows:
        id=row['effect_id']; source=row['source_kind']; token=(source,id)
        if token in seen:
            raise DataError('Duplicate remaining effect observation')
        seen.add(token)
        effect=tables.get(source,{}).get(id)
        if effect is None:
            raise DataError(f'Remaining effect source unavailable: {source}/{id}')
        counters={key:value for key,value in row.items() if key.startswith('remaining_')}
        if not counters or set(counters)-{'remaining_rounds','remaining_rolls','remaining_gold','remaining_xp'} or any(not isinstance(value,int) or isinstance(value,bool) or value<0 for value in counters.values()):
            raise DataError('Positive remaining effect counters required')
        result=combine(result,simulation(effect,data,snapshot,remaining=counters))
    if recurring-{id for source,id in seen if source=='augment'}:
        raise DataError('Held recurring augment omitted from effect inventory')
    return result
