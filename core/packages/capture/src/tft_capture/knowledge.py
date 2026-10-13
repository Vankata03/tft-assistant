"""Capture validation tables projected from the immutable pinned data snapshot.

This projection uses source trait rules and refund tables. It supplies no patch
fallbacks or recognition guesses; missing tables leave their validations closed.
"""
from collections.abc import Mapping

from tft_capture.ocr import NameCatalog
from tft_data.models import TaggedValue


def project_data(data):
    from tft_data.capacity import unit_slot_cost
    from tft_data.models import DataError
    costs={}
    for id,entity in data.entities.items():
        if entity.kind in ('unit','unit_form'):
            try:
                unit_slot_cost(data.entities,id)
                costs[id]=entity.values['team_slot_cost']
            except DataError:
                pass # Missing certificates leave slot validation closed.
    names = {kind: {} for kind in ('units', 'traits', 'augments', 'items', 'wisps', 'effects')}
    kinds = {'unit': 'units', 'unit_form':'units', 'trait': 'traits', 'augment': 'augments', 'item': 'items', 'wisp': 'wisps'}
    rules = data.static.get('trait_rules')
    refunds = data.static.get('sell_values')
    known_items = {identity for identity, entity in data.entities.items()
        if entity.kind == 'item' and identity == entity.id and identity and identity.strip() == identity}
    known_traits = {identity for identity, entity in data.entities.items()
        if entity.kind == 'trait' and identity == entity.id and identity and identity.strip() == identity}
    unit_variants, sale_values, effect_sources, item_traits, item_trait_sources = {}, {}, {}, {}, {}
    for entity in data.entities.values():
        if entity.kind in kinds:
            names[kinds[entity.kind]][entity.id] = entity.name
        if entity.kind in {'augment', 'wisp', 'opening_encounter'}:
            names['effects'][entity.id] = entity.name
            effect_sources[entity.id] = entity.kind
        if entity.kind == 'item':
            grants = entity.values.get('trait_grants')
            if (entity.id in known_items and isinstance(grants, TaggedValue)
                and isinstance(grants.value, Mapping) and all(
                    trait in known_traits and isinstance(count, int) and not isinstance(count, bool) and count > 0
                    for trait, count in grants.value.items())):
                item_traits[entity.id] = dict(grants.value)
                item_trait_sources[entity.id] = {'value': dict(grants.value), 'source': grants.source,
                    'citation': grants.citation, 'family': grants.family,
                    'data_snapshot_id': data.snapshot_id}
        if entity.kind not in ('unit','unit_form'):
            continue
        if refunds and str(entity.cost) in refunds.value:
            sale_values[entity.id] = dict(refunds.value[str(entity.cost)])
        if rules is None:
            continue
        from tft_data.traits import unit_trait_variants
        unit_variants[entity.id]=list(unit_trait_variants(entity.id,data))
    return {'catalog': NameCatalog(names), 'unit_variants': unit_variants, 'sale_values': sale_values,
        'effect_sources': effect_sources, 'item_traits': item_traits, 'item_trait_sources': item_trait_sources,
        'unit_counter':data.static.get('capture_unit_counter'),'unit_slot_costs':costs}
