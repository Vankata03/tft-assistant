"""Advice-change reports through logged games and the public harness boundary."""
from datetime import timedelta

import pytest

from tests.test_replay_contracts import NOW, ROOT, logged_game, log_snapshot
from tft_engine import Advice, DomainHook, ScoredOption
from tft_harness import EvaluationHarness


def diagnostic_choices(context):
    selected = 'b' if context.data.tunables['unit_weight'].value > 1 and context.snapshot.field('gold') > 10 else 'a'
    return (Advice('augment', 'Pick '+selected, 'act_this_phase', .9, 'synthetic-diagnostic',
        decision_id=context.snapshot.snapshot_id+':augment', option_id=selected,
        options=(ScoredOption('a', 'pick', {'augment_id': 'A'}, 3.1),
                 ScoredOption('b', 'pick', {'augment_id': 'B'}, 4.2))),)


def test_harness_advice_diff_aligns_original_log_points_and_ranks_changed_choices(tmp_path):
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='baseline')
    at = NOW+timedelta(seconds=1)
    raw = log_snapshot(data, at=at, snapshot_id='second', gold=8)
    sessions.append_event('snapshot', raw, timestamp=at.isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=1)).isoformat())
    original = store.get(data.snapshot_id)
    harness = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('augment', (), advice=diagnostic_choices, dependency_fields=('gold',)),))
    report = harness.advice_diff({'unit_weight': 2})
    assert report['eligible_decisions'] == 4
    assert report['changed_decisions'] == 1
    assert report['changed_share'] == .25
    assert report['excluded'] == {}
    assert len(report['largest_changes']) == 1
    change = report['largest_changes'][0]
    assert change['game_id'] == '901' and change['log_seq'] == 1
    assert change['decision'] == 'augment'
    assert change['accepted_choice'] == 'a' and change['candidate_choice'] == 'b'
    assert change['expected_placement_difference'] == pytest.approx(1.1)
    assert report['status'] == 'report_only'
    assert store.get(data.snapshot_id) == original


def information_choices(context):
    return (Advice('reference', 'High' if context.data.tunables['unit_weight'].value > 1 else 'Low',
        'information', .9, 'synthetic-diagnostic'),)


def test_harness_advice_diff_detects_changed_advice_without_scored_options(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, mode='baseline')
    report = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('reference', (), advice=information_choices),)).advice_diff({'unit_weight': 2})
    assert report['changed_decisions'] == 1
    change = report['largest_changes'][0]
    assert change['decision'] == 'reference'
    assert change['expected_placement_difference'] is None


def test_harness_advice_diff_keeps_locked_game_changes_aggregate_only(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, mode='silent')
    report = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('reference', (), advice=information_choices),)).advice_diff({'unit_weight': 2})
    assert report['changed_decisions'] == 1
    assert report['eligible_decisions'] == 2
    assert report['largest_changes'] == ()
    with pytest.raises(TypeError):
        report['changed_decisions'] = 0


@pytest.mark.parametrize('limit', [-1, 101, True, 1.5])
def test_harness_advice_diff_rejects_unbounded_or_nonintegral_examples(tmp_path, limit):
    sessions, store, _, _ = logged_game(tmp_path)
    with pytest.raises(ValueError, match='limit'):
        EvaluationHarness(sessions, store, repository=ROOT).advice_diff({'unit_weight': 2}, limit=limit)


def stable_id_choices(context):
    changed = context.data.tunables['unit_weight'].value > 1
    return (Advice('shop', 'Buy highlighted units' if changed else 'Hold shop', 'information', .9,
        'synthetic', option_id='shop', payload={'buys': [{'slot': 0, 'unit_id': 'unit'}] if changed else []}),
        Advice('positioning', 'Move to target layout', 'information', .9, 'synthetic',
            option_id='positioning:layout', payload={'layout': [{'unit_id': 'unit', 'cell': 1 if changed else 0}]}))


def test_harness_advice_diff_compares_operations_and_targets_with_stable_option_ids(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, mode='baseline')
    report = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('shop', (), advice=stable_id_choices),)).advice_diff({'unit_weight': 2})
    assert report['changed_decisions'] == 2
    assert {row['decision'] for row in report['largest_changes']} == {'shop', 'positioning'}


def test_harness_advice_diff_examples_name_unscored_actions(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, mode='baseline')
    report = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('reference', (), advice=information_choices),)).advice_diff({'unit_weight': 2})
    change = report['largest_changes'][0]
    assert change['accepted_choice'] == 'Low'
    assert change['candidate_choice'] == 'High'


def test_harness_advice_diff_refuses_candidate_that_changes_original_seed(tmp_path):
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='baseline')
    at = NOW+timedelta(seconds=1)
    raw = log_snapshot(data, at=at, snapshot_id='old-gold')
    raw['fields']['gold']['read_at'] = NOW.isoformat()
    sessions.append_event('snapshot', raw, timestamp=at.isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=1)).isoformat())
    with pytest.raises(ValueError, match='original replay seeds'):
        EvaluationHarness(sessions, store, repository=ROOT).advice_diff(
            {'field_max_age_seconds': {'default': .5, 'shop_roll_down': .5}})


def evidence_only_choices(context):
    value = context.data.tunables['unit_weight'].value
    return (Advice('positioning', 'Move to target layout', 'information', .9, 'synthetic',
        option_id='positioning:layout', numbers={'predicted_power': value},
        payload={'layout': [{'unit_id': 'unit', 'cell': 0}], 'threat_shares': {'aoe': value},
            'game_plan': {'status': 'open', 'target': 'guide', 'backup': None,
                'target_similarity': value, 'candidates': ['guide'] if value == 1 else ['guide', 'guide2']}}),)


def test_harness_advice_diff_ignores_new_scores_for_unchanged_operation(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, mode='baseline')
    report = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('positioning', (), advice=evidence_only_choices),)).advice_diff({'unit_weight': 2})
    assert report['changed_decisions'] == 0


def schedule_choices(context):
    return (Advice('econ', 'Level on schedule', 'information', .9, 'synthetic',
        option_id='scheduled-line', payload={'levels': {'3-2': 6 if context.data.tunables['unit_weight'].value > 1 else 5}}),)


def test_harness_advice_diff_retains_round_keyed_schedule_targets(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, mode='baseline')
    report = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('econ', (), advice=schedule_choices),)).advice_diff({'unit_weight': 2})
    assert report['changed_decisions'] == 1


def test_harness_advice_diff_detects_changed_builtin_nested_line_schedule(tmp_path):
    import tomllib
    import tomli_w
    from tests.test_replay_contracts import historical_data, GuideFeed
    from tft_core.storage import SessionStore
    from tft_data import DataStore

    class NoLineFeed(GuideFeed):
        def fetch(self):
            rows = super().fetch()
            rows['guides'][0].pop('line')
            return rows

    historical_data(tmp_path)
    path = tmp_path/'patch'/'tunables.toml'
    config = tomllib.loads(path.read_text())
    config['fields']['default_lines_by_carry_cost']['value'] = {'1': {'line': [{'round': '4-1', 'level': 1}]}}
    path.write_text(tomli_w.dumps(config))
    store = DataStore(tmp_path/'fresh-data')
    refreshed = store.refresh(tmp_path/'patch', now=NOW, sources=(NoLineFeed(),))
    assert refreshed.error is None
    data = refreshed.snapshot
    assert not data.guides['guide'].line
    sessions = SessionStore(tmp_path/'logs',tmp_path/'config',live_installed=True)
    sessions.set_mode('baseline')
    sessions.start_game('901',patch=data.patch,data_snapshot_id=data.snapshot_id,timestamp=NOW.isoformat())
    sessions.append_event('snapshot',log_snapshot(data),timestamp=NOW.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=1)).isoformat())
    report = EvaluationHarness(sessions,store,repository=ROOT).advice_diff(
        {'default_lines_by_carry_cost': {'1': {'line': [{'round': '4-1', 'level': 2}]}}})
    assert report['changed_decisions'] == 1
    assert report['largest_changes'][0]['decision'] == 'econ'


def transfer_choices(context):
    changed = context.data.tunables['unit_weight'].value > 1
    return (Advice('item','Sell and transfer items','information',.9,'synthetic',
        option_id='item:sell_and_transfer:donor:0',payload={'from':'donor','from_index':0,
            'item_ids':['sword'],'transfers':[{'item_id':'sword','holder':'carry-b' if changed else 'carry-a','holder_index':2 if changed else 1}]}),)


def test_harness_advice_diff_detects_builtin_transfer_recipient_changes(tmp_path):
    sessions,store,_,_ = logged_game(tmp_path,mode='baseline')
    report = EvaluationHarness(sessions,store,repository=ROOT,
        hooks=(DomainHook('item',(),advice=transfer_choices),)).advice_diff({'unit_weight':2})
    assert report['changed_decisions'] == 1
    assert 'carry-a' in report['largest_changes'][0]['accepted_recommendation']
    assert 'carry-b' in report['largest_changes'][0]['candidate_recommendation']


def test_harness_advice_diff_detects_builtin_game_plan_target_with_unchanged_hold(tmp_path):
    import tomllib
    import tomli_w
    from tests.test_replay_contracts import historical_data, GuideFeed
    from tft_core.storage import SessionStore
    from tft_data import DataStore
    from tft_engine import FitTerm
    from tft_review import ReplayProducer

    class TwoGuides(GuideFeed):
        def fetch(self):
            rows = super().fetch()
            rows['guides'].append(rows['guides'][0] | {'id': 'guide2'})
            return rows

    def preferred_comp(comp_id, context):
        preferred = 'guide2' if context.data.tunables['unit_weight'].value > 1 else 'guide'
        return FitTerm(-100 if comp_id == preferred else 100, 'fixture preference')

    historical_data(tmp_path)
    path = tmp_path/'patch'/'tunables.toml'
    config = tomllib.loads(path.read_text())
    config['fields']['open_candidate_count']['value'] = 2
    path.write_text(tomli_w.dumps(config))
    store = DataStore(tmp_path/'fresh-data')
    refreshed = store.refresh(tmp_path/'patch', now=NOW, sources=(TwoGuides(),))
    assert refreshed.error is None
    data = refreshed.snapshot
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.set_mode('baseline')
    sessions.start_game('901', patch=data.patch, data_snapshot_id=data.snapshot_id,
        timestamp=NOW.isoformat())
    sessions.append_event('snapshot', log_snapshot(data,
        pinned_line={'id': 'hold', 'levels': {}, 'rolls': {}}), timestamp=NOW.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=1)).isoformat())
    hooks = (DomainHook('preferred-comp', (), fit=preferred_comp),)
    accepted = ReplayProducer(sessions, store, repository=ROOT, hooks=hooks).produce('901')
    econ = next(row.advice for row in accepted.records if row.decision == 'econ')
    assert econ['option_id'] == 'hold' and econ['action'] == 'Hold econ'
    assert econ['payload']['game_plan']['target'] == 'guide'
    report = EvaluationHarness(sessions, store, repository=ROOT, hooks=hooks).advice_diff(
        {'unit_weight': 2})
    assert report['changed_decisions'] == 1
    change = report['largest_changes'][0]
    assert change['accepted_choice'] == change['candidate_choice'] == 'hold'
    assert '"target": "guide"' in change['accepted_recommendation']
    assert '"target": "guide2"' in change['candidate_recommendation']
