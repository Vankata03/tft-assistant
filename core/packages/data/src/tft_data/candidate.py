"""Deterministic review artifacts and explicitly tagged entity corrections."""
from hashlib import sha256
import json
from pathlib import Path

from .models import DataError, plain
from .entity_overlay import apply_entity_overlay, entities_payload, render


def consumer_inputs():
    """Review-only shape ledger; missing evidence is not a production value."""
    rows=[
        ('static.team_capacity','levels; continuous trait bonuses; held augment slots; owned/equipped-anywhere/deployed item slots; declared transition policy','reviewed_patch_data'),
        ('Entity.values.team_slot_cost','tagged nonnegative nonboolean integer; shared-pool forms agree','reviewed_patch_data'),
        ('static.capture_unit_counter','tagged reviewed region and physical_units/occupied_team_slots semantics','reviewed_hud_data'),
        ('fields.team_slot_budget','fresh positive observed own budget checks sourced model; cannot invent future modifiers','capture_runtime'),
        ('TraitSighting.team_slot_budget','positive same-frame scoped remote budget; own/viewer budgets cannot substitute','remote_capture_unavailable'),
        ('owned_active_form','typed canonical unit_form from positive ownership resolution; Guide targets cannot certify base ownership','capture_resolution_unavailable'),
        ('fields.inventory_complete','fresh literal True, complete board and bench identities/stars/equipment','capture_runtime'),
        ('fields.lobby_complete','fresh literal True and aligned alive roster; partial rows do not certify coverage','capture_runtime'),
        ('fields.phase','planning/roll_down plus literal planning_phase True; augment/carousel are declared choice phases','capture_runtime'),
        ('fields.remaining_effects','complete observed counters with source_kind; initial grants already reflected; expired effects do not replay','capture_runtime'),
        ('fields.recent_opponent_fights_complete','gap-aware positive first-round chronological persisted prefix, no invented recovery','capture_runtime'),
        ('Entity.values.trait_grants','canonical trait IDs to positive integer grants; explicit empty requires a no-grant certificate','reviewed_patch_data'),
        ('Entity.values.category','component/finished/tool; optional literal component certificate must agree','reviewed_patch_data'),
        ('Entity.values.item_class','unit/item class with sourced prior and item reference; absent support remains unavailable','qualified_source_data'),
        ('Entity.values.item_reference','qualified usual-item placement benefit or qualified sample-derived reference','qualified_source_data'),
        ('Entity.values.tool_kind','remover/reforger; exact consumption and explicit outcome pools','reviewed_patch_data'),
        ('static.rules_flags.item_slots_max','positive nonboolean integer; missing merge/overflow rules pause','reviewed_patch_data'),
        ('static.reforge_pools','item ID to positive finite outcome probabilities summing to one','reviewed_patch_data'),
        ('static.rules_flags.wisp_purchase_shop_slots_delta','nonnegative nonboolean refill policy; no guessed zero','reviewed_patch_data'),
        ('static.rules_flags.recent_opponent_exclusion_count','nonnegative policy; chronology and completeness separately observed','reviewed_patch_data'),
        ('static.wisps','explicit effect_kind/values, price and offer_stages; stage-only price cannot encode round/gold conditions','reviewed_patch_data'),
        ('static.econ_augments','explicit recurring scopes/durations and supported grants; remaining counters separately observed','reviewed_patch_data'),
        ('static.opening_encounters','pinned identities and modeled effects with observed remaining counters','reviewed_patch_data'),
        ('static.augment_pick_rounds','round to canonical pick stage 1/2/3','reviewed_patch_data'),
        ('Statistic.pick_stage','optional canonical 1/2/3; provider order 0/1/2 explicitly converts','qualified_source_data'),
        ('Entity.values.global_baseline_placement','same qualified augment cohort baseline; no assumed neutral placement','qualified_source_data'),
        ('Entity.values.statistics_min_samples','tagged augment policy 500; distinct from provider cohort evidence','accepted_application_policy'),
        ('wisp_standard_states','stage-matching locked Guide, sourced median HP and stage-average ownership; no synthetic production state','qualified_source_data'),
        ('source_provenance','own payload identity/publication/patch/cohort; donor hint not authoritative; accepted state separate from rejected attempts','qualified_source_data'),
    ]
    return {'qualification_status':'unresolved_consumer_review',
        'rows':[{'path':path,'shape':shape,'producer':producer,'value':None,'installed':False}
            for path,shape,producer in rows]}


def prepare_review(review_dir, patch, set_number, cdragon_file, ddragon_file, *, entity_overlay_file=None):
    """Prepare offline review inputs; unresolved values never become valid TOML."""
    import os
    import re
    import tempfile
    from collections import Counter
    from .adapters import CommunityDragon, DataDragon, merge_entities, dragon_bundle
    from .config import REQUIRED_STATIC, TUNABLE_FAMILIES, STATISTICS_MIN_SAMPLES

    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',patch):
        raise DataError('Invalid review patch label')
    inputs={'cdragon':Path(cdragon_file),'ddragon':Path(ddragon_file)}
    if entity_overlay_file is not None:
        inputs['entity_overlay']=Path(entity_overlay_file)
    target=Path(review_dir)
    if target.exists():
        raise DataError(f'Review destination already exists: {target}')
    consumed={name:path.read_bytes() for name,path in inputs.items()}
    adapter=CommunityDragon(json.loads(consumed['cdragon']),set_number)
    entities=adapter.entities()
    bundle=dragon_bundle(json.loads(consumed['ddragon']))
    for kind,payload in sorted(bundle.items()):
        entities=merge_entities(entities,DataDragon(payload,payload.get('version','unknown'),kind,allowed_ids=set(entities)).entities())
    entities,report=apply_entity_overlay(entities,entity_overlay_file,patch,set_number,
        overlay_bytes=consumed.get('entity_overlay'))
    from .capacity import unit_slot_cost
    for entity in entities.values():
        if entity.kind in ('unit','unit_form') and 'team_slot_cost' in entity.values:
            unit_slot_cost(entities,entity.id)
    unresolved=lambda name,**extra: {'name':name,'value':None,'source':None,'citation':None,'installed':False,**extra}
    artifacts={
        'entities.json':entities_payload(entities),
        'requirements.json':{
            'qualification_status':'incomplete_review_input','patch':patch,'set_number':set_number,
            'eune_live_at':None,'static':[unresolved(name) for name in REQUIRED_STATIC],
            'tunables':[unresolved(name,family=family) for name,family in sorted(TUNABLE_FAMILIES.items())
                if set_number==18 or name!='wisp_buy_margin'],
            'application_policy':{'statistics_min_samples':STATISTICS_MIN_SAMPLES,'provider_observation':False,'fit':False}},
        'catalog-summary.json':{'counts':dict(sorted(Counter(e.kind for e in entities.values()).items())),
            'warnings':adapter.warnings,'qualification_status':'identities_only'},
        'recipes.json':{'recipes':[{'item_id':id,'component_ids':plain(e.values['recipe'].value),
            'source':e.values['recipe'].source,'citation':e.values['recipe'].citation,
            'missing_ids':sorted(set(e.values['recipe'].value)-entities.keys())}
            for id,e in sorted(entities.items()) if e.kind=='item' and e.values.get('recipe') and e.values['recipe'].value]},
        'item-coverage.json':{'rows':[{'id':id,'values':{key:plain(vars(e.values[key])) if key in e.values else None
            for key in ('category','component','item_class','trait_grants','tool_kind')},
            'qualification_status':'declared_overlay_requires_review' if 'trait_grants' in e.values else 'grant_certificate_unavailable'}
            for id,e in sorted(entities.items()) if e.kind=='item']},
        'wisp-coverage.json':{'rows':[{'id':id,'source_text':plain(vars(e.values['text'])) if e.values.get('text') else None,
            'source_effects':plain(vars(e.values['effects'])) if e.values.get('effects') else None,
            'effect_kind':None,'cost':None,'offer_stages':None,
            'refill_delta':None,'exact_availability_conditions':None,'qualification_status':'mechanic_contract_unavailable'}
            for id,e in sorted(entities.items()) if e.kind=='wisp']},
        'unit-capacity-coverage.json':{'rows':[{'id':id,'kind':e.kind,
            'pool_id':plain(e.values['pool_id'].value) if e.values.get('pool_id') else id,
            'team_slot_cost':plain(vars(e.values['team_slot_cost'])) if e.values.get('team_slot_cost') else None,
            'qualification_status':'declared_overlay_requires_review' if e.values.get('team_slot_cost') else 'slot_certificate_unavailable'}
            for id,e in sorted(entities.items()) if e.kind in ('unit','unit_form')]},
        'consumer-inputs.json':consumer_inputs(),
    }
    encoded={name:render(body) for name,body in artifacts.items()}
    encoded['patch-diff.md']='\n\n'.join([
        f'# Patch {patch} offline review inputs',
        'No production patch, immutable snapshot, fitted coefficients or EUNE deployment time has been qualified. Missing fields remain null in JSON review ledgers; no static or tunables TOML is published.',
        *adapter.warnings,*report])+'\n'
    encoded={name:body.encode('utf-8') for name,body in encoded.items()}
    contract_root=next((ancestor/'docs'/'agents' for ancestor in Path(__file__).resolve().parents
        if (ancestor/'docs'/'agents'/'capacity-contracts.md').exists()),None)
    encoded['manifest.json']=render({'schema_version':1,'patch':patch,'set_number':set_number,
        'qualification_status':'incomplete_review_input',
        'inputs':{name:{'file':path.name,'sha256':sha256(consumed[name]).hexdigest()} for name,path in inputs.items()},
        'consumer_code':{name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('candidate.py','adapters.py','config.py','models.py','entity_overlay.py','capacity.py','traits.py')},
        'consumer_contracts':{name:sha256(path.read_bytes()).hexdigest() if path and path.exists() else None
            for name in ('decision-contracts.md','capacity-contracts.md','capture-boundary.md','engine-contracts.md')
            for path in (contract_root/name if contract_root else None,)},
        'outputs':{name:sha256(body).hexdigest() for name,body in encoded.items()}}).encode('utf-8')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        folder=Path(temporary)/'review';folder.mkdir()
        for name,body in encoded.items():
            (folder/name).write_bytes(body)
        os.replace(folder,target)
    return target
