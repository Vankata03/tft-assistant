"""Source-tagged capacity metadata validation shared by patch loading and Engine."""
from collections.abc import Mapping
from .models import DataError, TaggedValue


def integral(value,label,minimum=0):
    if isinstance(value,bool) or not isinstance(value,int) or value<minimum:
        raise DataError(f'Invalid integral capacity value: {label}')
    return value


def validate_capacity(static,entities):
    counter=static.get('capture_unit_counter')
    if counter is not None and (not isinstance(counter,TaggedValue) or not isinstance(counter.value,Mapping)
        or set(counter.value)!={'region','semantic'} or not isinstance(counter.value['region'],str)
        or not counter.value['region'] or counter.value['semantic'] not in ('physical_units','occupied_team_slots')
        or not isinstance(counter.citation,str) or not counter.citation.strip()):
        raise DataError('Unsupported reviewed capture counter semantics')
    tagged=static.get('team_capacity')
    if not isinstance(tagged,TaggedValue) or not isinstance(tagged.value,Mapping):
        raise DataError('Sourced team capacity rules unavailable')
    rules=tagged.value
    if set(rules)!={'levels','trait_bonuses','held_augment_slots','inventory_item_slots','transition_policy'}:
        raise DataError('Unsupported team capacity rule shape')
    if rules['transition_policy']!={'deploy':'reserve_before','swap':'remove_then_reserve','bench':'validate_after'}:
        raise DataError('Unsupported or unavailable capacity transition policy')
    levels=rules['levels'];traits=rules['trait_bonuses']
    augments=rules['held_augment_slots'];items=rules['inventory_item_slots']
    if not all(isinstance(table,Mapping) for table in (levels,augments,items)) or not isinstance(traits,(tuple,list)):
        raise DataError('Invalid team capacity tables')
    for level,budget in levels.items():
        if not isinstance(level,str) or not level.isdigit() or int(level)<1 or level!=str(int(level)):
            raise DataError('Invalid team capacity level')
        integral(budget,'level slot budget',1)
    seen=set()
    for rule in traits:
        if not isinstance(rule,Mapping) or set(rule)!={'trait_id','breakpoint','slots','activation'} or rule['activation']!='continuous':
            raise DataError('Unsupported trait capacity activation')
        identity=rule['trait_id'];point=integral(rule['breakpoint'],'capacity breakpoint',1)
        if not isinstance(identity,str) or identity not in entities or entities[identity].kind!='trait' or (identity,point) in seen:
            raise DataError('Unknown or duplicate capacity trait breakpoint')
        points=entities[identity].values.get('breakpoints')
        if (not isinstance(points,TaggedValue) or not isinstance(points.value,(tuple,list))
            or any(isinstance(value,bool) or not isinstance(value,int) or value<1 for value in points.value)
            or point not in points.value):
            raise DataError('Capacity breakpoint lacks sourced trait support')
        integral(rule['slots'],'trait capacity bonus');seen.add((identity,point))
    for identity,rule in augments.items():
        if not isinstance(rule,Mapping) or set(rule)!={'slots','activation'} or rule['activation']!='held':
            raise DataError('Unsupported augment capacity activation')
        if identity not in entities or entities[identity].kind!='augment':
            raise DataError('Unknown capacity augment')
        integral(rule['slots'],'augment capacity bonus')
    for identity,rule in items.items():
        if not isinstance(rule,Mapping) or set(rule)!={'slots','activation','scope'} or rule['activation']!='continuous' or rule['scope'] not in ('owned','equipped_anywhere','deployed_equipment'):
            raise DataError('Unsupported item capacity activation')
        if identity not in entities or entities[identity].kind!='item':
            raise DataError('Unknown capacity item')
        integral(rule['slots'],'item capacity bonus')

    return rules


def unit_slot_cost(entities,unit_id):
    entity=entities.get(unit_id)
    if entity is None or entity.kind not in ('unit','unit_form'):
        raise DataError(f'Unknown playable team slot identity: {unit_id}')
    tagged=entity.values.get('team_slot_cost')
    if not isinstance(tagged,TaggedValue):
        raise DataError(f'Sourced team slot cost unavailable: {unit_id}')
    cost=integral(tagged.value,f'{unit_id} team slots')
    pool=entity.values.get('pool_id') or entity.values.get('canonical_id')
    if pool is not None and pool.value!=unit_id:
        base=entities.get(pool.value)
        certificate=base.values.get('team_slot_cost') if base else None
        if not isinstance(certificate,TaggedValue) or integral(certificate.value,f'{pool.value} team slots')!=cost:
            raise DataError(f'Conflicting or missing shared-pool team slot cost: {unit_id}')
    return cost
