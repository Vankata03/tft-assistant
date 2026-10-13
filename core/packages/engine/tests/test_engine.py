"""Engine public behavior; synthetic data is never live-game evidence."""
from datetime import datetime, timezone
import json
import pytest
from tft_engine.models import Board, Unit, FieldValue, GameSnapshot

NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)

def test_snapshot_round_trip_keeps_field_provenance_and_owned_units():
    snapshot = GameSnapshot("game", "3-2", NOW, {"board": FieldValue(Board((Unit("carry", 2, ("sword",), 4),)), NOW, "reader", 0.9), "gold": FieldValue(40, NOW, "ocr")})
    restored = GameSnapshot.from_dict(json.loads(json.dumps(snapshot.to_dict())))
    assert restored == snapshot
    assert restored.field("board", now=NOW, max_age_seconds=2).units[0].position == 4
    with pytest.raises(TypeError):
        snapshot.fields["gold"] = FieldValue(50, NOW, "ocr")

from tft_data.models import DataSnapshot, Entity, TaggedValue, Statistic, Guide

def tagged(value):
    return TaggedValue(value, 'owner')

def data(**changes):
    values = dict(snapshot_id='fixture', patch='test', set_number=18,
        static={k: tagged(v) for k,v in {'team_capacity':{'levels':{str(l):l for l in range(1,11)},'trait_bonuses':(),'held_augment_slots':{},'inventory_item_slots':{},'transition_policy':{'deploy':'reserve_before','swap':'remove_then_reserve','bench':'validate_after'}},'lobby_top4_rate':0.5, 'shop_odds':{'3':[1,0,0,0,0]}, 'level_calendar':{'2-1':3,'3-1':4}, 'stage_items':{'2':{'finished':1,'component':0,'high_cost_finished':0},'3':{'finished':2,'component':0,'high_cost_finished':0}}}.items()},
        tunables={k:tagged(v) for k,v in {'unit_weight':1,'trait_weight':1,'item_weight':1,'unit_prior_strength':100,'cost_star_baseline':{'1':{'1':1,'2':2,'3':3},'3':{'1':3,'2':4,'3':5}},'item_values':{'finished':1,'component':0.35,'high_cost_bonus':0.25},'confidence_medium_min':0.5,'confidence_high_min':0.8,'fight_scale':1,'win_scale_by_stage':{},'survivor_scale_by_stage':{'2':1},'terminal_hp_weight':1,'classifier_weights':{'carry':3,'key':2,'other':1,'bench':0.5},'classifier_threshold':0.5,'opponent_star_mix':{'2-1':{'1':[1,0,0],'3':[1,0,0]},'3-1':{'1':[0,1,0],'3':[0,1,0]}},'emblem_slack_max':2,'emblem_count_prior':{'0':1,'1':0.1,'2':0.01},'size_level_prior':{'3':{'1':0.01,'2':1,'3':0.1},'4':{'1':0.01,'2':1,'3':0.1,'4':0.01}},'sighting_persistence_weight':2,'sighting_full_weight_rounds':2,'sighting_half_life_rounds':1}.items()},
        entities={'a': Entity('a','unit','A',1,('fire',),values={'team_slot_cost':tagged(1),'top4_rate_1':tagged(0.8),'sample_count_1':tagged(100),'play_rate':tagged(0.75)}), 'b':Entity('b','unit','B',1,('fire',),values={'team_slot_cost':tagged(1),'play_rate':tagged(0.25)}), 'c':Entity('c','unit','C',3,('water',),values={'team_slot_cost':tagged(1)}), 'fire':Entity('fire','trait','Fire',values={'breakpoints':tagged([2]),'top4_rate_2':tagged(0.8)}), 'water':Entity('water','trait','Water',values={'breakpoints':tagged([2])}), 'sword':Entity('sword','item','Sword',values={'component':tagged(True)}), 'blade':Entity('blade','item','Blade',values={'component':tagged(False)})},
        guides={'comp':Guide('comp','A',('a','c'),carry_ids=('a',))})
    values.update(changes)
    return DataSnapshot(**values)

def test_board_power_uses_top4_logit_shrinkage_and_generic_items_without_comp_matching():
    from tft_engine import strength, estimate_strength
    board = Board((Unit('a',1,('sword',)), Unit('c',2,('blade',))))
    # A cost-star prior power 1 implies rate 0.7310585786; its posterior rate is 0.7655292893.
    assert strength(board,2,data()) == pytest.approx(6.78323679709)
    estimate = estimate_strength(board,2,data())
    assert estimate.confidence < 0.8
    assert 'cost-star prior' in ' '.join(estimate.warnings)

def test_combat_projection_respects_hp_dead_opponents_and_stage_scaling():
    from tft_engine import win_probability, placement, surviving_units
    assert win_probability(2,2,2,data()) == 0.5
    assert placement(2,(2,2),50,(50,0),10,data()) == 1.5
    assert placement(2,(2,),50,(60,),10,data()) == pytest.approx(1.73105857863)
    assert surviving_units(0,2,6,data()) == 3


def test_classifier_ignores_stars_and_caps_bench_overlap_at_one():
    from tft_engine import classify
    board = Board((Unit('a',3),), (Unit('a'), Unit('c')))
    result = classify(board,data())
    assert result[0].comp_id == 'comp'
    assert result[0].similarity == 0.875
    assert classify(Board((Unit('c'),)),data())[0].label == 'no comp'

def test_trait_identical_units_split_by_prior_without_claiming_seen_units():
    from tft_engine import infer_opponent, TraitSighting
    snapshot = data()
    inferred = infer_opponent(TraitSighting('enemy','2-1',3,{'fire':1}),snapshot)
    assert dict(inferred.probabilities) == pytest.approx({'a':0.75,'b':0.25})
    assert inferred.certainty == pytest.approx(0.75)
    assert inferred.candidate_count == 2

def with_tunables(snapshot, **changes):
    from dataclasses import replace
    return replace(snapshot,tunables=dict(snapshot.tunables) | {k:tagged(v) for k,v in changes.items()})


def test_hidden_rows_are_exactly_counted_and_must_stay_inactive():
    from dataclasses import replace
    from tft_engine import infer_opponent, TraitSighting
    snapshot = data()
    snapshot = replace(snapshot, entities=dict(snapshot.entities) | {'c':Entity('c','unit','C',3,('water',),values={'team_slot_cost':tagged(1),'play_rate':tagged(0.5)})})
    snapshot = with_tunables(snapshot,emblem_slack_max=0)
    inferred = infer_opponent(TraitSighting('enemy','2-1',3,{'fire':1},1),snapshot)
    assert dict(inferred.probabilities) == pytest.approx({'a':0.75,'b':0.25,'c':1})
    assert infer_opponent(TraitSighting('enemy','2-1',3,{'fire':1},2),snapshot).candidate_count == 0


def test_emblem_slack_explains_counts_without_inventing_units():
    from tft_engine import infer_opponent, TraitSighting
    snapshot = with_tunables(data(),size_level_prior={'3':{'1':1}}, emblem_count_prior={'0':1,'1':0.1,'2':0.01})
    result = infer_opponent(TraitSighting('enemy','2-1',3,{'fire':2}),snapshot)
    assert dict(result.probabilities) == pytest.approx({'a':0.75,'b':0.25})
    assert infer_opponent(TraitSighting('enemy','2-1',3,{'fire':2}),with_tunables(snapshot,emblem_slack_max=0)).candidate_count == 0


def test_set_specific_trait_grants_and_evolutions_reproduce_sightings():
    from tft_engine import infer_opponent, TraitSighting
    from dataclasses import replace
    units = {'lux':Entity('lux','unit','Lux',3,('avatar',),values={'team_slot_cost':tagged(1),'play_rate':tagged(1)}), 'dragon':Entity('dragon','unit','Dragon',3,('rift',),values={'team_slot_cost':tagged(1),'play_rate':tagged(1)}), 'khazix':Entity('khazix','unit','Kha',3,('hunter',),values={'team_slot_cost':tagged(1),'play_rate':tagged(1)})}
    traits = {t:Entity(t,'trait',t,values={'breakpoints':tagged([2])}) for t in ('avatar','fire','water','rift','hunter','evolved')}
    snapshot = with_tunables(data(),emblem_slack_max=0,size_level_prior={'3':{'3':1}})
    snapshot = replace(snapshot,entities=units | traits, static=dict(snapshot.static) | {'trait_rules':tagged({'lux':{'choose_one':[{'fire':2},{'water':2}]},'dragon':{'counts':{'rift':2}},'khazix':{'optional_traits':['evolved']}})})
    result = infer_opponent(TraitSighting('enemy','2-1',3,{'avatar':1,'fire':2,'rift':2,'hunter':1,'evolved':1}),snapshot)
    assert dict(result.probabilities) == {'lux':1,'dragon':1,'khazix':1}
    assert result.certainty == 1


def test_duplicate_owned_units_count_power_twice_and_traits_once():
    from tft_engine import estimate_strength
    estimate = estimate_strength(Board((Unit('a'),Unit('a'))),2,data())
    assert estimate.trait_term == 0
    assert estimate.unit_term == pytest.approx(2.36647359418)

def test_growth_and_stale_opponent_power_use_expected_stars_and_fading_copies():
    from dataclasses import replace
    from tft_engine import TraitSighting, infer_opponent, estimate_opponent, growth_curve
    snapshot = data()
    snapshot = replace(snapshot,static=dict(snapshot.static) | {'shop_odds':tagged({'3':[1,0,0,0,0],'4':[1,0,0,0,0]})})
    curve = growth_curve(snapshot)
    assert curve['2-1'] == pytest.approx(4.41228279345)
    assert curve['3-1'] == 10
    sighting = TraitSighting('enemy','2-1',3,{'fire':1})
    inferred = infer_opponent(sighting,snapshot)
    estimate = estimate_opponent(sighting,inferred,'2-4',snapshot)
    assert estimate.age_weight == 0.5
    assert estimate.confidence == 0.1875
    assert dict(estimate.expected_copies) == pytest.approx({'a':0.375,'b':0.125})
    assert estimate.power == pytest.approx(4.41228279345)
    advanced = estimate_opponent(sighting,inferred,'3-1',snapshot)
    assert advanced.level == 4
    assert advanced.power > estimate.power

def test_previous_inference_persists_then_fades_and_does_not_add_new_units():
    from tft_engine import TraitSighting, infer_opponent
    snapshot = data()
    previous = infer_opponent(TraitSighting('enemy','2-1',3,{'fire':1}),snapshot)
    recent = infer_opponent(TraitSighting('enemy','2-2',3,{'fire':1}),snapshot,previous=previous)
    old = infer_opponent(TraitSighting('enemy','2-4',3,{'fire':1}),snapshot,previous=previous)
    assert recent.probabilities['a'] == pytest.approx(0.80769230769)
    assert old.probabilities['a'] == pytest.approx(0.78571428571)


def test_advice_options_preserve_scored_choices_without_parsing_action_text():
    from tft_engine import Advice, ScoredOption, rank_advice
    item = Advice('shop','Buy A','act_this_phase',0.9,'buy_template',{'power_delta':1},('shop',),0.2,decision_id='snap:shop:0',option_id='buy:a',payload={'unit_id':'a','slot':0},options=(ScoredOption('buy:a','buy',{'unit_id':'a'},3.2,0.1),ScoredOption('skip','skip',{},3.5,0.1)),anchors={'shop_slot':0},validity_state={'shop':['a']})
    restored = Advice.from_dict(json.loads(json.dumps(item.to_dict())))
    assert restored == item
    assert restored.options[0].payload['unit_id'] == 'a'
    later = Advice('level','Level','soon',0.9,'level',placement_impact=1)
    assert rank_advice((later,item))[0].decision_id == 'snap:shop:0'


def test_growth_correction_uses_sighting_confidence_without_mutating_static_data():
    from dataclasses import replace
    from tft_engine import growth_curve
    snapshot = data()
    snapshot = replace(snapshot,static=dict(snapshot.static) | {'shop_odds':tagged({'3':[1,0,0,0,0],'4':[1,0,0,0,0]})})
    corrected = growth_curve(snapshot,observations=(('2-1',6.41228279345,0.75),('2-1',4.41228279345,0.25)))
    assert corrected['2-1'] == pytest.approx(5.91228279345)
    assert corrected['3-1'] == 10

def test_exact_inference_handles_many_trait_identical_candidates_within_bounded_cpu_time():
    import os, subprocess, sys
    script = '''
from dataclasses import replace
from test_engine import data, tagged, with_tunables
from tft_data.models import Entity
from tft_engine import infer_opponent, TraitSighting
snapshot=data()
units={str(i):Entity(str(i),'unit',str(i),1,('fire',),values={'team_slot_cost':tagged(1),'play_rate':tagged(0.5)}) for i in range(45)}
snapshot=replace(snapshot,entities=units | {'fire':snapshot.entities['fire']})
snapshot=with_tunables(snapshot,emblem_slack_max=0,size_level_prior={'8':{'8':1}})
result=infer_opponent(TraitSighting('enemy','2-1',8,{'fire':8}),snapshot)
assert result.candidate_count == 215553195
assert abs(result.probabilities['0']-8/45) < 1e-12
'''
    env = dict(os.environ, PYTHONPATH=str(__import__('pathlib').Path(__file__).parent))
    subprocess.run([sys.executable,'-c',script],env=env,check=True,timeout=1)

def test_unavailable_opponent_power_statistics_lower_advice_confidence_beyond_inference_certainty():
    from tft_engine import TraitSighting, infer_opponent, estimate_opponent
    snapshot = data()
    sighting = TraitSighting('enemy','2-1',3,{'fire':1})
    inferred = infer_opponent(sighting,snapshot)
    estimate = estimate_opponent(sighting,inferred,'2-1',snapshot)
    assert estimate.inference_certainty == 0.75
    assert estimate.confidence == 0.375
    assert estimate.data_confidence == 0.5

def test_missing_game_data_is_an_actionable_error_instead_of_guessed_power():
    from tft_engine import strength
    from tft_data.models import DataError
    with pytest.raises(DataError,match='cost-star baseline'):
        strength(Board((Unit('c'),)),1,with_tunables(data(),cost_star_baseline={'1':{'1':1}}))

def test_opponent_read_ahead_of_standard_calendar_does_not_gain_an_extra_level():
    from dataclasses import replace
    from tft_engine import TraitSighting, infer_opponent, estimate_opponent
    snapshot = data()
    snapshot = replace(snapshot,static=dict(snapshot.static) | {'shop_odds':tagged({'3':[1,0,0,0,0],'4':[1,0,0,0,0],'5':[1,0,0,0,0]})})
    snapshot = with_tunables(snapshot,size_level_prior={'5':{'1':1}})
    sighting = TraitSighting('enemy','2-1',5,{'fire':1})
    estimate = estimate_opponent(sighting,infer_opponent(sighting,snapshot),'3-1',snapshot)
    assert estimate.level == 5

def test_thin_binomial_zero_and_one_rates_shrink_before_logit_without_infinite_power():
    from dataclasses import replace
    from math import isfinite
    from tft_engine import strength
    snapshot = data()
    a = snapshot.entities['a']
    perfect = replace(snapshot, entities=dict(snapshot.entities) | {'a':replace(a,values=dict(a.values) | {'top4_rate_1':tagged(1.0)})})
    zero = replace(snapshot, entities=dict(snapshot.entities) | {'a':replace(a,values=dict(a.values) | {'top4_rate_1':tagged(0.0)})})
    # Prior rate 0.7310585786, n=prior=100: posterior 0.8655292893 or 0.3655292893.
    assert strength(Board((Unit('a'),)),1,perfect) == pytest.approx(1.86199480405825)
    assert strength(Board((Unit('a'),)),1,zero) == pytest.approx(-0.551444713932051)
    assert isfinite(strength(Board((Unit('a'),)),1,perfect))

def test_trait_endpoint_rates_use_their_own_explicit_neutral_prior():
    from dataclasses import replace
    from tft_engine import estimate_strength
    snapshot = with_tunables(data(),trait_prior_strength=100)
    trait = snapshot.entities['fire']
    snapshot = replace(snapshot,entities=dict(snapshot.entities) | {'fire':replace(trait,values=dict(trait.values) | {'top4_rate_2':tagged(1),'sample_count_2':tagged(100)})})
    estimate = estimate_strength(Board((Unit('a'),Unit('b'))),2,snapshot)
    # n=prior=100, lobby prior0.5 and observed1 gives posterior0.75.
    assert estimate.trait_term == pytest.approx(1.09861228866811)
    assert estimate.confidence <= 0.5


def test_mixed_trait_variants_count_distinct_unit_sets_once_and_budget_fallback_has_no_posterior():
    from dataclasses import replace
    from tft_engine import infer_opponent, TraitSighting, estimate_opponent
    snapshot=data()
    snapshot=replace(snapshot,static=dict(snapshot.static)|{'trait_rules':tagged({'a':{'replace':[{'fire':1},{'fire':1}]}})})
    sighting=TraitSighting('enemy','2-1',3,{'fire':1})
    exact=infer_opponent(sighting,snapshot)
    assert exact.candidate_count==2
    assert exact.probabilities['a']==pytest.approx(0.75)
    bounded=infer_opponent(sighting,with_tunables(snapshot,opponent_inference_state_cap=1))
    assert bounded.candidate_count==0
    assert bounded.probabilities=={}
    assert bounded.certainty==0
    assert 'state cap' in bounded.fallback_reason
    estimate=estimate_opponent(sighting,bounded,'2-1',snapshot)
    assert estimate.confidence==0
    assert any('state cap' in warning for warning in estimate.warnings)


def test_unreferenced_source_trait_without_a_breakpoint_does_not_block_inference():
    from dataclasses import replace
    from tft_data.models import Entity, DataError
    from tft_engine import infer_opponent, TraitSighting
    snapshot=data()
    snapshot=replace(snapshot,entities=dict(snapshot.entities)|{'unused':Entity('unused','trait','Unused',values={'breakpoints':tagged([None])})})
    assert infer_opponent(TraitSighting('enemy','2-1',3,{'fire':1}),snapshot).candidate_count==2
    with pytest.raises(DataError,match='Unknown sighting trait'):
        infer_opponent(TraitSighting('enemy','2-1',3,{'unused':1}),snapshot)


def test_form_power_prefers_its_sampled_star_statistics_while_pool_identity_stays_shared():
    from dataclasses import replace
    from math import isfinite
    from tft_data.models import Entity, Statistic
    from tft_engine import estimate_strength
    snapshot=data()
    form=Entity('a_form','unit_form','A form',1,('fire',),values={'team_slot_cost':tagged(1),'pool_id':tagged('a'),'canonical_id':tagged('a')})
    stats=(Statistic('a','unit',4.5,100,'test','tactics.tools',unit_star=3,top4_rate=0),
           Statistic('a_form','unit',1,24,'test','tactics.tools',unit_star=3,top4_rate=1))
    snapshot=replace(snapshot,entities=dict(snapshot.entities)|{'a_form':form},statistics=stats)
    active=estimate_strength(Board((Unit('a_form',3),)),1,snapshot)
    base=estimate_strength(Board((Unit('a',3),)),1,snapshot)
    assert isfinite(active.power)
    assert active.unit_term>base.unit_term
