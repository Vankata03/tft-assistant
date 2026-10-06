"""Fail-closed, source-tagged TOML contracts; no invented patch defaults."""
import json
import tomllib
from pathlib import Path
from .models import DataError, Entity, TaggedValue

REQUIRED_STATIC = ('xp_table','gold_by_round','streak_gold','interest','player_damage','shop_odds','pool_sizes','rules_flags','wisps','combat_buff_power','wisp_round_cap','opening_encounters','econ_augments','augment_pools','threat_keywords','bench_size','item_recipes')
TUNABLE_FAMILIES = {
 **dict.fromkeys(('unit_weight','trait_weight','item_weight','fight_scale','win_scale_by_stage','survivor_scale_by_stage','terminal_hp_weight','opponent_star_mix','emblem_count_prior','size_level_prior','sighting_persistence_weight','sighting_full_weight_rounds','sighting_half_life_rounds'),'1'),
 **dict.fromkeys(('pivot_margin_by_stage','pivot_reraise_extra','transition_tolerance','line_margin','comp_defining_margin','board_power_buy_min','wisp_buy_margin','threat_share_on','threat_share_off','review_min_cost'),'2'),
 **dict.fromkeys(('cost_star_baseline','unit_prior_strength','item_class_prior','item_prior_strength','augment_prior_strength','augment_flag_prior_multiplier'),'3'),
 **dict.fromkeys(('open_candidate_count','commit_latest_round','rollouts_full','rollouts_reroll','line_candidate_cap','challengers_simulated','gold_floors','all_in_rounds_left','stabilize_rounds_left','item_values','classifier_weights','classifier_threshold','emblem_slack_max','component_income_by_stage','component_discount_by_stage','slam_candidate_cap','open_candidate_temperature','augment_tier_delta','board_settle_seconds','confidence_show_min','confidence_medium_min','confidence_high_min','board_reader_identity_min','field_max_age_seconds'),'hand-set'),
 'opponent_growth_curve':'computed','default_lines_by_carry_cost':'computed',
}

def tagged(raw,label,*,families=None):
 if not isinstance(raw,dict): raise DataError(f'{label} must be a table')
 result={}
 for key,item in raw.items():
  if not isinstance(item,dict) or 'value' not in item or 'source' not in item: raise DataError(f'{label}.{key} requires value and source')
  if families and item.get('family')!=families.get(key): raise DataError(f'{label}.{key} requires family {families.get(key)}')
  result[key]=TaggedValue(item['value'],item['source'],item.get('citation',''),item.get('family',''))
 return result

def load_patch(path):
 path=Path(path)
 try:
  static=tomllib.loads((path/'static.toml').read_text());tunables=tomllib.loads((path/'tunables.toml').read_text());entities=json.loads((path/'entities.json').read_text())['entities']
 except (OSError,ValueError,KeyError) as exc: raise DataError(f'Missing or invalid patch files in {path}: {exc}') from None
 if not isinstance(static.get('patch'),str) or not isinstance(static.get('set_number'),int): raise DataError('Static file requires patch and set_number')
 if tunables.get('patch')!=static['patch']: raise DataError('Static and tunables patch labels differ')
 fields=tagged(static.get('fields'),'static');missing=set(REQUIRED_STATIC)-fields.keys()
 if missing: raise DataError(f'Missing static fields: {sorted(missing)}')
 values=tagged(tunables.get('fields'),'tunables',families=TUNABLE_FAMILIES);missing=set(TUNABLE_FAMILIES)-values.keys()
 if missing: raise DataError(f'Missing tunables: {sorted(missing)}')
 parsed={}
 for item in entities:
  try: e=Entity(item['id'],item['kind'],item['name'],item.get('cost',0),tuple(item.get('traits',[])),item.get('text',''),item.get('icon',''),tagged(item.get('values',{}),'entity'))
  except (KeyError,TypeError) as exc: raise DataError(f'Invalid entity schema: {exc}') from None
  if e.id in parsed or not e.id or not e.name: raise DataError(f'Duplicate or empty entity: {e.id}')
  if e.kind=='wisp' and e.id not in fields['wisps'].value: raise DataError(f'New Wisp {e.id} needs a static effect entry')
  parsed[e.id]=e
 return static['patch'],static['set_number'],fields,values,parsed,tuple(static.get('changed_ids',[]))
