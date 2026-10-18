"""Later actions identify a schedule; their shops, boards and outcomes never value it."""
from datetime import timedelta
import tomllib

import tomli_w
import pytest

from tft_engine import Board, Unit
from tft_core.storage import SessionStore
from tft_review import ReplayProducer, ReviewPolicy
from tests.test_replay_contracts import NOW, ROOT, historical_data, log_snapshot, GuideFeed


def observed_level_game(tmp_path, *, later_gold=10, later_stars=1, placement=4, gap=False):
    store,data = historical_data(tmp_path)
    # A small declared held-gold correction keeps this synthetic placement
    # objective informative. It is not an owner fit or a production default.
    path = tmp_path/'patch'/'tunables.toml'
    tunables = tomllib.loads(path.read_text())
    tunables['fields']['terminal_gold_weight']['value'] = .001
    path.write_text(tomli_w.dumps(tunables))
    static_path=path.parent/'static.toml'
    static=tomllib.loads(static_path.read_text())
    static['fields']['rules_flags']['value']['passive_xp']=0
    static_path.write_text(tomli_w.dumps(static))
    data = store.refresh(path.parent,sources=(GuideFeed(),),now=NOW).snapshot
    sessions = SessionStore(tmp_path/'logs',tmp_path/'config',live_installed=True)
    sessions.set_mode('baseline')
    sessions.start_game('901',patch=data.patch,data_snapshot_id=data.snapshot_id,timestamp=NOW.isoformat())
    financial={'remaining_effects':[],'remaining_effects_complete':True,'held_augments':[],'held_augments_complete':True,'owned_copies':{'unit':1}}
    sessions.append_event('snapshot',log_snapshot(data,**financial),timestamp=NOW.isoformat())
    at = NOW+timedelta(seconds=.25)
    sessions.append_event('level_up', {'before':{'level':1,'xp':0,'xp_to_level':2},
        'after':{'level':3,'xp':2,'xp_to_level':6},'before_read_at':NOW.isoformat(),
        'after_read_at':at.isoformat(),'confidence':.95,'sources':{'level':'external-fixture'}},
        timestamp=at.isoformat())
    sessions.append_event('snapshot',log_snapshot(data,at=at,snapshot_id='observed-level',level=3,xp=2,**financial,
        gold=later_gold,board=Board((),bench=(Unit('unit',1),)) if later_stars!=1 else Board((Unit('unit',1),))),timestamp=at.isoformat())
    rounds = tuple(data.value('round_order'))
    horizon = rounds[rounds.index('3-2')+1:rounds.index('4-7')+1]
    for index, round_id in enumerate(horizon):
        later_gold += 5 + min(later_gold//10,5)
        at = NOW+timedelta(seconds=index+1)
        raw = log_snapshot(data,at=at,snapshot_id=round_id,level=3,xp=2,gold=later_gold,**financial,
            board=Board((),bench=(Unit('unit',1),)) if later_stars!=1 else Board((Unit('unit',1),))) | {'round_id':round_id}
        sessions.append_event('snapshot',raw,timestamp=at.isoformat())
    if gap:
        sessions.append_event('capture_gap',{'start':(NOW+timedelta(seconds=1)).isoformat(),
            'end':(NOW+timedelta(seconds=2)).isoformat(),'reason':'missing action interval'},
            timestamp=(at+timedelta(seconds=.5)).isoformat())
    sessions.end_game(placement=placement,timestamp=(at+timedelta(seconds=1)).isoformat())
    return sessions,store


def first_econ(sessions,store):
    batch = ReplayProducer(sessions,store,repository=ROOT,decision_segmentation='semantic').produce('901')
    report = ReviewPolicy(min_cost=.05).build(batch,data=store.get(batch.identity['data_snapshot_id']))
    return next(row for row in report.timeline if row['category']=='econ'),report,batch


def test_observed_line_is_an_extra_same_seed_candidate_without_future_state_or_outcome_leakage(tmp_path):
    (tmp_path/'normal').mkdir(); (tmp_path/'changed-truth').mkdir()
    first,first_store = observed_level_game(tmp_path/'normal')
    row,report,batch = first_econ(first,first_store)
    assert row['player_choice'] is not None
    player = row['player_choice']
    assert player['payload']['levels'] == {'3-2':3}
    assert player['payload']['valuation_policy'] == 'ex_post_action_schedule/original_snapshot_data_history_seed'
    assert player['payload']['after']['seed'] == batch.contexts[0].seed
    assert player['payload']['initial_snapshot_id'] == 'original'
    assert row['cost'] == pytest.approx(row['engine_choice']['expected_placement']-player['expected_placement'])
    assert row['paired_uncertainty'] is not None
    changed,changed_store = observed_level_game(tmp_path/'changed-truth',later_gold=10,later_stars=3,placement=1)
    other,_,_ = first_econ(changed,changed_store)
    assert other['player_choice']['expected_placement'] == player['expected_placement']
    assert other['cost'] == row['cost']
    assert report.lines[0]['actual_policy'] is not None


def test_observed_line_stays_unavailable_across_unobserved_action_interval(tmp_path):
    sessions,store = observed_level_game(tmp_path,gap=True)
    row,_,_ = first_econ(sessions,store)
    assert row['player_choice'] is None and row['cost'] is None
    assert row['unavailable']['player_choice'] == 'observed_policy_crosses_capture_gap'


def captured_roll_game(tmp_path, *, changed_truth=False, broken=None, purchase=False, multiple=False, initial_stars=1, fast=False, held=False):
    """Real CapturePipeline with recorded external OCR/vision at 4 Hz, then a full horizon."""
    import json
    from PIL import Image
    from tft_capture.pipeline import CapturePipeline
    from tft_capture.ocr import NameCatalog, TextLine
    from tft_data import TaggedValue
    from tests.test_capture_complete import OCRFrames, VisualFrames
    store, _ = historical_data(tmp_path)
    path = tmp_path/'patch'
    entities = json.loads((path/'entities.json').read_text())
    entities['entities'].append(dict(entities['entities'][0], id='other', name='Other'))
    if held:
        entities['entities'].append({'id':'combat-augment','kind':'augment','name':'Combat augment','values':{'augment_tier':{'value':'silver','source':'owner'}}})
    (path/'entities.json').write_text(json.dumps(entities))
    tunables = tomllib.loads((path/'tunables.toml').read_text())
    tunables['fields']['terminal_gold_weight']['value'] = .001
    tunables['fields']['augment_tier_delta']['value'] = {'silver':0}
    (path/'tunables.toml').write_text(tomli_w.dumps(tunables))
    if broken == 'cost_change':
        static = tomllib.loads((path/'static.toml').read_text())
        static['fields']['rules_flags']['value']['roll_cost'] = 3
        (path/'static.toml').write_text(tomli_w.dumps(static))
    # A source-qualified fixture with no passive XP keeps level evidence explicit.
    static = tomllib.loads((path/'static.toml').read_text())
    static['fields']['rules_flags']['value']['passive_xp'] = 0
    (path/'static.toml').write_text(tomli_w.dumps(static))
    data = store.refresh(path, sources=(GuideFeed(),), now=NOW).snapshot
    sessions = SessionStore(tmp_path/'logs',tmp_path/'config',live_installed=True)
    sessions.set_mode('baseline')
    sessions.start_game('901',patch=data.patch,data_snapshot_id=data.snapshot_id,timestamp=NOW.isoformat())
    base = log_snapshot(data)['fields']
    values = {name: row['value'] for name,row in base.items() if name not in ('board','bench','inventory_complete','gold')}
    observation = {'zone':'board','position':0,'unit_id':'unit','identity_confidence':.99,'stars':initial_stars,'items':[]}
    values.update(board_observations=[observation], trait_panel_empty=True,
        slot_inventory={'board_occupied':[0],'board_empty':list(range(1,28)),
            'bench_occupied':[],'bench_empty':list(range(9))}, remaining_effects=[], remaining_effects_complete=True, held_augments=['combat-augment'] if held else [], held_augments_complete=True)
    class CadencedVision(VisualFrames):
        def read(self, image, *, regions, own_view):
            from tft_capture.vision import VisionRead
            if 'board' not in regions:
                return VisionRead({'shop_empty_slots': self.values.get('shop_empty_slots',[])}, self.source,.95)
            return super().read(image,regions=regions,own_view=own_view)

    visual = CadencedVision(values, complete=True)
    ocr = OCRFrames({'scouted':[TextLine('Owner Level 1')], 'unit_count':[TextLine('1/1')],
        'gold':[TextLine('18')], 'stage':[TextLine('3-2')]})
    pipeline = CapturePipeline('901',ocr=ocr,sink=sessions,visual_reader=visual,own_player_name='Owner',
        data_snapshot_id=data.snapshot_id,unit_traits={'unit':{},'other':{}},
        unit_counter=TaggedValue({'region':'unit_count','semantic':'physical_units'},'owner',citation='Fixture independent counter'),
        catalog=NameCatalog({'units':{'unit':'Unit','other':'Other'}}),
        regions={name:(0,0,1,1) for name in ('scouted','unit_count','gold','stage','shop','board')})
    visual.values['xp_to_level'] = 2
    for step in range(34 if multiple else 17):
        at = NOW+timedelta(seconds=step*.25)
        shop_id = 'other' if step in ((1,20) if multiple else (1,)) else 'unit'
        if broken == 'unregistered_roll':shop_id='unit'
        gold = 18 if step == 0 else 16 if step == 1 else 14
        if multiple and step >= 18:
            ocr.values['stage'] = [TextLine('3-3')]
            gold = 20 if step == 18 else 12 if step == 19 else 10 if step == 20 else 8
            if step >= 19:
                visual.values['level'] = 3
                visual.values['xp'] = 2
                visual.values['xp_to_level'] = 6
        if purchase and step >= 3:
            gold -= 1
            visual.values['shop_empty_slots'] = [0]
            visual.values['board_observations'] = [observation, dict(observation, zone='bench')]
            visual.values['slot_inventory'].update(bench_occupied=[0],bench_empty=list(range(1,9)))
        if broken == 'free_roll' and step == 5:
            shop_id = 'other'
        visual.values['remaining_effects_complete'] = not (broken == 'effects_unknown' and step == 5)
        ocr.values['gold'] = [TextLine(str(gold))]
        ocr.values['shop'] = [line for slot in range(5) if not (purchase and step >= 3 and slot == 0)
            for line in (TextLine('Other' if shop_id == 'other' else 'Unit',box=(slot/5,.74,(slot+1)/5,.8)),
                         TextLine('1',box=(slot/5,.85,(slot+1)/5,.95)))]
        if broken == 'incomplete' and step == 5:
            visual.complete = False
        else:
            visual.complete = True
        if broken == 'gap' and step == 6:
            pipeline.tick(None,timestamp=at)
        elif broken != 'missing_stop' or step < 10:
            frame = Image.new('RGB',(20,20),(step,step,step))
            pipeline.tick(frame,timestamp=at)
            if fast and step < 16:
                for offset in (.08,.16):
                    pipeline.tick(frame,timestamp=at+timedelta(seconds=offset))
    events = sessions.read_events('901')
    assert len([event for event in events if event['kind']=='roll']) == (0 if broken=='unregistered_roll' else 4 if multiple else 2)
    assert not [event for event in events if event['kind']=='tracking_ambiguity'] or broken in ('gap','free_roll')
    pipeline.close(timestamp=NOW+timedelta(seconds=8.5 if multiple else 4.25))
    rounds = list(data.value('round_order'))
    later_gold = (8 if multiple else 14) - int(purchase)
    for index, round_id in enumerate(rounds[rounds.index('3-3' if multiple else '3-2')+1:rounds.index('4-7')+1]):
        later_gold += 5 + min(later_gold//10,5)
        if broken == 'offset_income' and index == 0:
            later_gold -= 2
        at = NOW+timedelta(seconds=index+(9 if multiple else 5))
        raw = log_snapshot(data,at=at,snapshot_id=round_id,gold=later_gold,
            hp=1 if changed_truth else 73, level=3 if multiple else 1, xp=2 if multiple else 0,
            owned_copies={'unit':(3 if initial_stars==2 else 1)+int(purchase)},
            remaining_effects=[],remaining_effects_complete=True,held_augments=['combat-augment'] if held else [],held_augments_complete=True,
            shop=[{'slot':0,'unit_id':'other','cost':1}] if changed_truth else None,
            board=Board((),bench=(Unit('unit',initial_stars),)) if changed_truth else Board((Unit('unit',initial_stars),)))|{'round_id':round_id}
        sessions.append_event('snapshot',raw,timestamp=at.isoformat())
    sessions.append_event('fight_start',{'round_id':'4-7','opponent_id':'rival'},timestamp=(at+timedelta(seconds=.2)).isoformat())
    sessions.append_event('fight_result',{'round_id':'4-7','opponent_id':'rival',
        'result':'loss' if changed_truth else 'win','hp_lost':30 if changed_truth else 0},
        timestamp=(at+timedelta(seconds=.4)).isoformat())
    sessions.end_game(placement=1 if changed_truth else 4,timestamp=(at+timedelta(seconds=1)).isoformat())
    return sessions,store


def test_captured_paid_roll_down_is_valued_by_certified_refresh_count_without_invented_floor(tmp_path):
    sessions,store = captured_roll_game(tmp_path,purchase=True)
    row,report,batch = first_econ(sessions,store)
    assert row['player_choice'] is not None, dict(row['unavailable'])
    payload = row['player_choice']['payload']
    assert payload['rolls'] == {}
    assert payload['observed_rolls'] == {'3-2':2}
    certificate, = payload['stop_certificates']
    assert certificate['reason'] == 'observed_idle_3s'
    assert certificate['paid_roll_count'] == 2
    assert certificate['purchase_count'] == 1
    assert certificate['complete'] is True
    assert payload['after']['seed'] == batch.contexts[0].seed
    assert row['cost'] is not None and row['paired_uncertainty'] is not None
    assert report.lines[0]['actual_policy'] is not None
    from tft_review import ReviewService
    service = ReviewService(sessions,store,repository=ROOT)
    service.produce('901')
    assert service.detail('901',path=('surface','lines',0,'actual'))['kind'] == 'object'


def test_paid_roll_schedule_valuation_ignores_future_boards_shops_hp_and_placement(tmp_path):
    results=[]
    for name, changed in (('normal',False),('changed',True)):
        path = tmp_path/name
        path.mkdir()
        sessions,store = captured_roll_game(path,changed_truth=changed)
        row,_,_ = first_econ(sessions,store)
        assert row['player_choice'] is not None, dict(row['unavailable'])
        results.append((row['player_choice']['payload']['after'],row['cost']))
    assert results[0] == results[1]


@pytest.mark.parametrize('broken', ['gap','incomplete','missing_stop','free_roll','effects_unknown','cost_change'])
def test_paid_roll_without_complete_positive_stop_stays_unavailable(tmp_path, broken):
    sessions,store = captured_roll_game(tmp_path,broken=broken)
    row,_,_ = first_econ(sessions,store)
    assert row['player_choice'] is None
    assert row['cost'] is None


def test_certified_multiple_bursts_and_later_level_up_keep_the_observed_round_schedule(tmp_path):
    sessions,store = captured_roll_game(tmp_path,multiple=True)
    row,_,_ = first_econ(sessions,store)
    assert row['player_choice'] is not None, dict(row['unavailable'])
    payload = row['player_choice']['payload']
    assert payload['observed_rolls'] == {'3-2':2,'3-3':2}
    assert payload['levels'] == {'3-3':3}
    assert len(payload['stop_certificates']) == 2


def test_observed_refreshes_are_paid_even_when_original_keys_have_already_hit(tmp_path):
    sessions,store = captured_roll_game(tmp_path,initial_stars=2)
    row,_,_ = first_econ(sessions,store)
    assert row['player_choice'] is not None, dict(row['unavailable'])
    # Initial 18 gold, two paid refreshes at 2 gold, no copies needed or sales.
    assert row['player_choice']['payload']['after']['projections'][0]['planned_gold'] == 14


def test_real_shop_only_rolling_polls_keep_bounded_ownership_ledger_coverage(tmp_path):
    sessions,store = captured_roll_game(tmp_path,purchase=True,fast=True)
    snapshots = [row['payload'] for row in sessions.read_events('901') if row['kind']=='snapshot']
    assert any(row['fields'].get('owned_copies',{}).get('read_at') != row['captured_at'] for row in snapshots)
    row,_,_ = first_econ(sessions,store)
    assert row['player_choice'] is not None, dict(row['unavailable'])
    assert row['player_choice']['payload']['observed_rolls'] == {'3-2':2}


def test_future_observed_paid_refresh_is_additional_to_the_natural_shop(tmp_path):
    from tft_engine import GameHistory, GameSnapshot, Line, simulate_lines
    store,data = historical_data(tmp_path)
    snapshot = GameSnapshot.from_dict(log_snapshot(data,slot_count=1))
    program = Line.from_dict({'id':'observed:future','observed_rolls':{'3-3':1}})
    result = simulate_lines(snapshot,GameHistory(),data,'guide',(program,),seed=42)[0]
    # Only one unit is in this public fixture's pool. Starting with one copy,
    # the natural shop plus one paid single-slot shop must complete three copies.
    assert result.projections[1].hit_probability == 1
    assert result.projections[1].planned_gold == 20


def test_ordinary_paid_roll_with_a_known_non_econ_augment_is_valued(tmp_path):
    sessions,store = captured_roll_game(tmp_path,held=True)
    row,_,_ = first_econ(sessions,store)
    assert row['player_choice'] is not None, dict(row['unavailable'])
    assert row['player_choice']['payload']['observed_rolls'] == {'3-2':2}
    assert row['cost'] is not None

@pytest.mark.parametrize('step', [12, 15])
def test_unexplained_identical_offer_spend_anywhere_in_observed_horizon_is_unavailable(tmp_path, monkeypatch, step):
    from tests.test_capture_complete import OCRFrames
    from tft_capture.ocr import TextLine
    original = OCRFrames.read
    calls = 0
    def read(self, image, *, region):
        nonlocal calls
        result = original(self, image, region=region)
        if region == 'gold':
            calls += 1
            if calls > step:
                return [TextLine('12')]
        return result
    monkeypatch.setattr(OCRFrames, 'read', read)
    sessions, store = captured_roll_game(tmp_path, initial_stars=2)
    row, _, _ = first_econ(sessions, store)
    assert row['player_choice'] is None
    assert row['cost'] is None


def test_round_income_cannot_mask_an_unobserved_paid_refresh(tmp_path):
    sessions,store=captured_roll_game(tmp_path,broken='offset_income')
    row,_,_=first_econ(sessions,store)
    assert row['player_choice'] is None
    assert row['unavailable']['player_choice']=='observed_roll_ledger_unsupported'


def test_unexplained_spend_between_certified_bursts_is_unavailable(tmp_path, monkeypatch):
    from tests.test_capture_complete import OCRFrames
    from tft_capture.ocr import TextLine
    original=OCRFrames.read
    calls=0
    def read(self,image,*,region):
        nonlocal calls
        result=original(self,image,region=region)
        if region=='gold':
            calls+=1
            if calls==18:return [TextLine('12')]
        return result
    monkeypatch.setattr(OCRFrames,'read',read)
    sessions,store=captured_roll_game(tmp_path,multiple=True)
    row,_,_=first_econ(sessions,store)
    assert row['player_choice'] is None and row['cost'] is None


def test_absence_of_confirmed_roll_events_does_not_certify_a_zero_roll_program(tmp_path):
    sessions,store=captured_roll_game(tmp_path,broken='unregistered_roll')
    assert not [event for event in sessions.read_events('901') if event['kind']=='roll']
    row,_,_=first_econ(sessions,store)
    assert row['player_choice'] is None and row['cost'] is None


def test_unexplained_finances_cannot_certify_a_level_only_actual_program(tmp_path):
    sessions,store=observed_level_game(tmp_path,later_gold=999)
    row,_,_=first_econ(sessions,store)
    assert row['player_choice'] is None and row['cost'] is None
