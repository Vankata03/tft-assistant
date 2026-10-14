"""Later actions identify a schedule; their shops, boards and outcomes never value it."""
from datetime import timedelta
import tomllib

import tomli_w
import pytest

from tft_engine import Board, Unit
from tft_core.storage import SessionStore
from tft_review import ReplayProducer, ReviewPolicy
from tests.test_replay_contracts import NOW, ROOT, historical_data, log_snapshot, GuideFeed


def observed_level_game(tmp_path, *, later_gold=18, later_stars=1, placement=4, gap=False):
    store,data = historical_data(tmp_path)
    # A small declared held-gold correction keeps this synthetic placement
    # objective informative. It is not an owner fit or a production default.
    path = tmp_path/'patch'/'tunables.toml'
    tunables = tomllib.loads(path.read_text())
    tunables['fields']['terminal_gold_weight']['value'] = .001
    path.write_text(tomli_w.dumps(tunables))
    data = store.refresh(path.parent,sources=(GuideFeed(),),now=NOW).snapshot
    sessions = SessionStore(tmp_path/'logs',tmp_path/'config',live_installed=True)
    sessions.set_mode('baseline')
    sessions.start_game('901',patch=data.patch,data_snapshot_id=data.snapshot_id,timestamp=NOW.isoformat())
    sessions.append_event('snapshot',log_snapshot(data),timestamp=NOW.isoformat())
    at = NOW+timedelta(seconds=.25)
    sessions.append_event('level_up', {'before':{'level':1,'xp':0,'xp_to_level':2},
        'after':{'level':3,'xp':0,'xp_to_level':6},'before_read_at':NOW.isoformat(),
        'after_read_at':at.isoformat(),'confidence':.95,'sources':{'level':'external-fixture'}},
        timestamp=at.isoformat())
    sessions.append_event('snapshot',log_snapshot(data,at=at,snapshot_id='observed-level',level=3,
        gold=later_gold,board=Board((Unit('unit',later_stars),))),timestamp=at.isoformat())
    rounds = tuple(data.value('round_order'))
    horizon = rounds[rounds.index('3-2')+1:rounds.index('4-7')+1]
    for index, round_id in enumerate(horizon):
        at = NOW+timedelta(seconds=index+1)
        raw = log_snapshot(data,at=at,snapshot_id=round_id,level=3,gold=later_gold,
            board=Board((Unit('unit',later_stars),))) | {'round_id':round_id}
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
    changed,changed_store = observed_level_game(tmp_path/'changed-truth',later_gold=999,later_stars=3,placement=1)
    other,_,_ = first_econ(changed,changed_store)
    assert other['player_choice']['expected_placement'] == player['expected_placement']
    assert other['cost'] == row['cost']
    assert report.lines[0]['actual_policy'] is not None


def test_observed_line_stays_unavailable_across_unobserved_action_interval(tmp_path):
    sessions,store = observed_level_game(tmp_path,gap=True)
    row,_,_ = first_econ(sessions,store)
    assert row['player_choice'] is None and row['cost'] is None
    assert row['unavailable']['player_choice'] == 'observed_policy_crosses_capture_gap'
