"""Capture validation tables projected from the immutable pinned data snapshot.

This projection uses source trait rules and refund tables. It supplies no patch
fallbacks or recognition guesses; missing tables leave their validations closed.
"""
from itertools import combinations

from tft_capture.ocr import NameCatalog


def project_data(data):
    names = {kind: {} for kind in ('units', 'traits', 'augments', 'items', 'wisps', 'effects')}
    kinds = {'unit': 'units', 'trait': 'traits', 'augment': 'augments', 'item': 'items', 'wisp': 'wisps'}
    rules = data.static.get('trait_rules')
    refunds = data.static.get('sell_values')
    unit_variants, sale_values, effect_sources = {}, {}, {}
    for entity in data.entities.values():
        if entity.kind in kinds:
            names[kinds[entity.kind]][entity.id] = entity.name
        if entity.kind in {'augment', 'wisp', 'opening_encounter'}:
            names['effects'][entity.id] = entity.name
            effect_sources[entity.id] = entity.kind
        if entity.kind != 'unit':
            continue
        if refunds and str(entity.cost) in refunds.value:
            sale_values[entity.id] = dict(refunds.value[str(entity.cost)])
        if rules is None:
            continue
        rule = rules.value.get(entity.id, {})
        if 'replace' in rule:
            unit_variants[entity.id] = [dict(choice) for choice in rule['replace']]
            continue
        counts = {trait: 1 for trait in entity.traits}
        counts.update(rule.get('counts', {}))
        variants = []
        optional = tuple(rule.get('optional_traits', ()))
        for choice in rule.get('choose_one', ({},)):
            for size in range(len(optional)+1):
                for subset in combinations(optional, size):
                    variant = dict(counts)
                    for trait, count in choice.items():
                        variant[trait] = variant.get(trait, 0) + count
                    for trait in subset:
                        variant[trait] = variant.get(trait, 0) + 1
                    variants.append(variant)
        unit_variants[entity.id] = variants
    return {'catalog': NameCatalog(names), 'unit_variants': unit_variants, 'sale_values': sale_values, 'effect_sources': effect_sources}
