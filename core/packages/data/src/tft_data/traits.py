"""Static, source-certified unit trait alternatives shared by power and inference."""
from itertools import combinations
from collections.abc import Mapping
from .models import DataError

def unit_trait_variants(unit_id, data):
    entity = data.entities[unit_id]
    counts = {t: 1 for t in entity.traits}
    rules = data.static.get('trait_rules')
    pool = entity.values.get('pool_id') or entity.values.get('canonical_id')
    rule = rules.value.get(unit_id, rules.value.get(pool.value, {}) if pool else {}) if rules else {}
    if not isinstance(rule,Mapping) or set(rule)-{'replace','counts','choose_one','optional_traits'} or ('replace' in rule and set(rule)!={'replace'}):
        raise DataError(f'Unsupported or conflicting unit trait grant rule: {unit_id}')
    def grants(value):
        if not isinstance(value,Mapping) or any(not isinstance(trait,str) or isinstance(count,bool)
            or not isinstance(count,int) or count<0 for trait,count in value.items()):
            raise DataError(f'Invalid integral unit trait grant: {unit_id}')
        return dict(value)
    if 'replace' in rule:
        if not isinstance(rule['replace'],(tuple,list)) or not rule['replace']:
            raise DataError(f'Empty or unsupported trait grant alternatives: {unit_id}')
        result=tuple(grants(v) for v in rule['replace'])
        if entity.kind=='unit_form':
            result=tuple(v for v in result if set(v)==set(entity.traits))
            if not result:
                raise DataError(f'No trait rule matches active form: {unit_id}')
        return result
    counts.update(grants(rule.get('counts', {})))
    choices = rule.get('choose_one', ({},))
    if not isinstance(choices,(tuple,list)) or not choices:
        raise DataError(f'Empty or unsupported trait grant choices: {unit_id}')
    optional = tuple(rule.get('optional_traits', ()))
    if any(not isinstance(trait,str) for trait in optional) or len(set(optional))!=len(optional):
        raise DataError(f'Invalid optional unit trait grants: {unit_id}')
    result = []
    for choice in choices:
        choice=grants(choice)
        for size in range(len(optional) + 1):
            for subset in combinations(optional, size):
                value = dict(counts)
                for trait, count in choice.items():
                    value[trait] = value.get(trait, 0) + int(count)
                for trait in subset:
                    value[trait] = value.get(trait, 0) + 1
                if value not in result:
                    result.append(value)
    if entity.kind=='unit_form' and pool and rule:
        result=[v for v in result if set(v)==set(entity.traits)]
        if not result:
            raise DataError(f'No trait rule matches active form: {unit_id}')
    return tuple(result)
