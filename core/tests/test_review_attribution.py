"""Review attribution over real logs: shown advice, follow status and choices."""
from datetime import timedelta

import pytest

from tests.test_replay_contracts import NOW, ROOT, logged_game
from tests.test_review_policy import augment_choices


def _hook():
    from tft_engine import DomainHook
    return (DomainHook('augment', (), advice=augment_choices),)


def _decision_id(sessions, store, decision='augment', hooks=None):
    """The replay's own Engine decision identity; later logged display events cannot change it."""
    from tft_review import ReplayProducer
    batch = ReplayProducer(sessions, store, repository=ROOT, hooks=hooks or _hook()).produce('901')
    return next(record.decision_id for record in batch.records if record.decision == decision)


def log_delivery(sessions, *, decision_id, option_id, domain='augment', snapshot_id='original',
        at=NOW+timedelta(seconds=.2), revision='sha256:'+'1'*64, payload=None):
    """The advice_delivery event format written by LiveDeliveryController.activate."""
    return sessions.append_event('advice_delivery', {'schema_version': 1, 'delivery_revision': revision,
        'game_id': '901', 'snapshot_id': snapshot_id, 'data_snapshot_id': None, 'model_hash': None,
        'captured_at': NOW.isoformat(), 'evaluated_at': at.isoformat(), 'evidence_id': 'sha256:'+'2'*64,
        'summary': {'game_id': '901', 'snapshot_id': snapshot_id, 'advice': [{'decision_id': decision_id,
            'option_id': option_id, 'domain': domain, 'action': 'Pick', 'payload': payload or {}}]}},
        timestamp=at.isoformat())


def log_shown(sessions, *, decision_id, option_id, at=NOW+timedelta(seconds=.4),
        revision='sha256:'+'1'*64, surface='overlay'):
    """The ui_show event format written by LiveDeliveryController.shown."""
    return sessions.append_event('ui_show', {'schema_version': 1, 'mode': 'live', 'surface': surface,
        'delivery_revision': revision, 'decision_id': decision_id, 'option_id': option_id,
        'evidence_id': 'sha256:'+'2'*64, 'delivered_at': (NOW+timedelta(seconds=.2)).isoformat(),
        'received_at': at.isoformat()}, timestamp=at.isoformat())


def log_pick(sessions, augment_id, slot, at=NOW+timedelta(seconds=1)):
    sessions.append_event('augment_pick', {'slot': slot, 'augment_id': augment_id,
        'choice_token': 'offer', 'evidence': 'positive_pick_confirmation'}, timestamp=at.isoformat())


def review(sessions, store, hooks=None):
    from tft_review import ReplayProducer, ReviewPolicy
    batch = ReplayProducer(sessions, store, repository=ROOT, hooks=hooks or _hook()).produce('901')
    return ReviewPolicy(min_cost=.05).build(batch)


def augment_moment(report):
    return next(row for row in report.timeline if row['category'] == 'augment')


def test_shown_advice_the_player_did_not_take_is_ignored_and_counts_against_follow_rate(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    decision = _decision_id(sessions, store)
    log_delivery(sessions, decision_id=decision, option_id='a')
    log_shown(sessions, decision_id=decision, option_id='a')
    log_pick(sessions, 'B', 1)
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store)
    shown = augment_moment(report)['shown']
    assert shown['status'] == 'ignored'
    assert shown['shown_option_id'] == 'a'
    assert shown['surfaces'] == ('overlay',)
    assert shown['followed'] is False
    assert report.summary['follow_rate'] == {'value': 0.0, 'reason': None, 'eligible': 1, 'followed': 0}


def test_followed_shown_advice_counts_toward_follow_rate(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    decision = _decision_id(sessions, store)
    log_delivery(sessions, decision_id=decision, option_id='a')
    log_shown(sessions, decision_id=decision, option_id='a', surface='cockpit')
    log_pick(sessions, 'A', 0)
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store)
    assert augment_moment(report)['shown']['status'] == 'followed'
    assert report.summary['follow_rate']['value'] == 1.0


@pytest.mark.parametrize('show_first', [False, True])
def test_single_pick_equal_time_following_respects_logged_display_order(tmp_path, show_first):
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    decision = _decision_id(sessions, store)
    log_delivery(sessions, decision_id=decision, option_id='a')
    if show_first:
        log_shown(sessions, decision_id=decision, option_id='a', at=NOW+timedelta(seconds=1))
    log_pick(sessions, 'A', 0)
    if not show_first:
        log_shown(sessions, decision_id=decision, option_id='a', at=NOW+timedelta(seconds=1))
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store)
    shown = augment_moment(report)['shown']
    assert shown['status'] == ('followed' if show_first else 'shown')
    assert shown['followed'] is (True if show_first else None)
    if not show_first:
        assert shown['reason'] == 'display_not_confirmed_before_policy_onset'
    assert report.summary['follow_rate']['eligible'] == int(show_first)


def test_followed_advice_that_the_current_engine_values_worse_is_an_engine_error(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    decision = _decision_id(sessions, store)
    # The coach shown during the game said B; the regenerated Engine prefers A.
    log_delivery(sessions, decision_id=decision, option_id='b')
    log_shown(sessions, decision_id=decision, option_id='b')
    log_pick(sessions, 'B', 1)
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store)
    moment = augment_moment(report)
    assert moment['cost'] < 0
    assert moment['shown']['status'] == 'engine_error'
    assert moment['shown']['followed'] is True
    assert report.summary['follow_rate']['value'] == 1.0


def test_advice_the_coach_did_not_show_in_time_is_a_capture_gap_and_not_eligible(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    decision = _decision_id(sessions, store)
    log_delivery(sessions, decision_id=decision, option_id='a')
    sessions.append_event('advice_too_late', {'delivery_revision': 'sha256:'+'1'*64,
        'decision_id': decision, 'reason': 'augments changed', 'captured_at': NOW.isoformat()},
        timestamp=(NOW+timedelta(seconds=.5)).isoformat())
    log_pick(sessions, 'B', 1)
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store)
    shown = augment_moment(report)['shown']
    assert shown['status'] == 'capture_gap'
    assert shown['cause'] == 'advice_too_late'
    assert shown['would_have_said'] == 'a'
    assert report.summary['follow_rate'] == {'value': None, 'reason': 'no_shown_advice_with_known_choice',
        'eligible': 0, 'followed': 0}


def test_missing_display_is_a_capture_gap_but_a_late_display_has_unknown_following(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    decision = _decision_id(sessions, store)
    log_pick(sessions, 'B', 1)
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    assert augment_moment(review(sessions, store))['shown']['cause'] == 'not_delivered'

    late = tmp_path / 'late'
    late.mkdir()
    sessions, store, _, _ = logged_game(late, finish=False, mode='live')
    log_delivery(sessions, decision_id=decision, option_id='a')
    log_pick(sessions, 'B', 1)
    log_shown(sessions, decision_id=decision, option_id='a', at=NOW+timedelta(seconds=1.5))
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    shown = augment_moment(review(sessions, store))['shown']
    assert shown['status'] == 'shown'
    assert shown['followed'] is None
    assert shown['shown_at'] == (NOW+timedelta(seconds=1.5)).isoformat()
    assert shown['reason'] == 'display_not_confirmed_before_policy_onset'


@pytest.mark.parametrize('late_seconds', [1, 1.1])
@pytest.mark.parametrize(('choice', 'slot', 'followed'), [('A', 0, True), ('B', 1, False)])
def test_late_different_option_cannot_replace_the_latest_causal_single_pick_display(
    tmp_path, late_seconds, choice, slot, followed
):
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    decision = _decision_id(sessions, store)
    log_delivery(sessions, decision_id=decision, option_id='a')
    log_shown(sessions, decision_id=decision, option_id='a')
    revision = 'sha256:'+'3'*64
    log_delivery(sessions, decision_id=decision, option_id='b',
        at=NOW+timedelta(seconds=.6), revision=revision)
    log_pick(sessions, choice, slot)
    log_shown(sessions, decision_id=decision, option_id='b', revision=revision,
        at=NOW+timedelta(seconds=late_seconds))
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store)
    shown = augment_moment(report)['shown']
    assert shown['shown_option_id'] == 'a'
    assert shown['status'] == ('followed' if followed else 'ignored')
    assert shown['followed'] is followed
    assert report.summary['follow_rate']['value'] == float(followed)


def test_display_without_an_observable_player_choice_remains_shown_and_unknown(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    decision = _decision_id(sessions, store)
    log_delivery(sessions, decision_id=decision, option_id='a')
    log_shown(sessions, decision_id=decision, option_id='a')
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store)
    shown = augment_moment(report)['shown']
    assert shown['status'] == 'shown'
    assert shown['followed'] is None
    assert shown['reason'] == 'player_choice_unavailable'
    assert report.summary['follow_rate']['eligible'] == 0


@pytest.mark.parametrize('mode', ['silent', 'baseline'])
def test_silent_and_baseline_decisions_keep_their_mode_status(tmp_path, mode):
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode=mode)
    decision = _decision_id(sessions, store)
    log_delivery(sessions, decision_id=decision, option_id='a')
    log_shown(sessions, decision_id=decision, option_id='a')
    log_pick(sessions, 'B', 1)
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    assert augment_moment(review(sessions, store))['shown'] == {'status': f'no_advice_in_{mode}_mode'}


def purchase_choices(context):
    from tft_engine import Advice, ScoredOption
    return tuple(Advice(domain, 'Buy', 'act_this_phase', .9, 'fixture',
        option_id=f'{domain}:buy', options=(ScoredOption(f'{domain}:buy', 'buy', payload, 3.0),))
        for domain, payload in (('wisp', {'slot': 4, 'wisp_id': 'W'}),
            ('shop', {'slot': 0, 'unit_id': 'unit'})))


def test_confirmed_wisp_and_shop_purchases_attribute_without_nonexistent_evidence_fields(tmp_path):
    from tft_engine import DomainHook
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='baseline')
    sessions.append_event('wisp_purchase', {'slot': 4, 'wisp_id': 'W', 'cost': 3},
        timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.append_event('purchase', {'slot': 0, 'unit_id': 'unit', 'cost': 1, 'copies': 1},
        timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store, (DomainHook('purchases', (), advice=purchase_choices),))
    points = {row['category']: row for row in report.timeline}
    assert points['wisp']['player_choice']['option_id'] == 'wisp:buy'
    assert points['shop']['player_choice']['option_id'] == 'shop:buy'


def board_calls(context):
    from tft_engine import Advice, ScoredOption
    return (Advice('transition', 'Swap', 'act_this_phase', .9, 'fixture', option_id='transition',
        payload={'board': {'units': [{'unit_id': 'unit', 'stars': 1, 'items': [], 'position': 1}], 'bench': [], 'trait_counts': {}}}),
        Advice('pivot', 'Pivot', 'act_this_phase', .9, 'fixture', option_id='new-comp',
            payload={'target': 'new-comp', 'from': 'guide'},
            options=(ScoredOption('new-comp', 'comp', {'comp_id': 'new-comp'}, 3.0),
                ScoredOption('guide', 'comp', {'comp_id': 'guide'}, 4.0))),
        Advice('positioning', 'Move', 'act_this_phase', .9, 'fixture', option_id='layout',
            payload={'layout': [{'unit_index': 0, 'unit_id': 'unit', 'cell': 1}]}))


def test_observed_transition_pivot_and_prefight_positioning_are_linked_to_logged_fight(tmp_path):
    from tft_engine import Board, Unit, DomainHook
    from tests.test_replay_contracts import log_snapshot
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    hooks = (DomainHook('board-calls', (), advice=board_calls),)
    at = NOW+timedelta(seconds=1)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='moved',
        board=Board((Unit('unit', position=1),)), comp_lock='new-comp'), timestamp=at.isoformat())
    sessions.append_event('fight_start', {'round_id': '3-2', 'opponent_id': 'rival'},
        timestamp=(NOW+timedelta(seconds=1.1)).isoformat())
    sessions.append_event('fight_result', {'round_id': '3-2', 'opponent_id': 'rival', 'result': 'loss', 'hp_lost': 5},
        timestamp=(NOW+timedelta(seconds=2)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=3)).isoformat())
    report = review(sessions, store, hooks)
    points = {row['category']: row for row in report.timeline if row['log_seq'] == 1}
    assert points['transition']['player_choice']['option_id'] == 'transition'
    assert points['pivot']['player_choice']['option_id'] == 'new-comp'
    assert len(report.surface['positioning']) == 1
    note = report.surface['positioning'][0]
    assert note['followed'] is True
    assert note['result'] == 'loss'
    assert note['fight_path'] == ('surface', 'fights', 0)
    assert report.plan_timeline[0]['called_status'] == 'taken_without_call'


def test_later_committed_board_captured_before_decision_cannot_prove_transition_or_pivot(tmp_path):
    from tft_engine import Board, Unit, DomainHook
    from tests.test_replay_contracts import log_snapshot
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    at = NOW-timedelta(seconds=.5)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='captured-earlier',
        board=Board((Unit('unit', position=1),)), comp_lock='new-comp'), timestamp=at.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store, (DomainHook('board-calls', (), advice=board_calls),))
    points = [row for row in report.timeline
        if row['log_seq'] == 1 and row['category'] in {'transition', 'pivot'}]
    assert len(points) == 2
    assert all(row['player_choice'] is None for row in points)


def test_later_snapshot_cannot_attribute_board_fields_read_before_the_decision(tmp_path):
    from tft_engine import Board, Unit, DomainHook
    from tests.test_replay_contracts import log_snapshot
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    read_at, captured_at = NOW-timedelta(seconds=.5), NOW+timedelta(seconds=1)
    snapshot = log_snapshot(data, at=captured_at, snapshot_id='carried-board',
        board=Board((Unit('unit', position=1),)), comp_lock='new-comp')
    for field in ('board', 'comp_lock'):
        snapshot['fields'][field]['read_at'] = read_at.isoformat()
    sessions.append_event('snapshot', snapshot, timestamp=captured_at.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store, (DomainHook('board-calls', (), advice=board_calls),))
    points = [row for row in report.timeline
        if row['log_seq'] == 1 and row['category'] in {'transition', 'pivot'}]
    assert len(points) == 2
    assert all(row['player_choice'] is None for row in points)


def test_positioning_ignores_board_captured_after_fight_despite_earlier_log_sequence(tmp_path):
    from tft_engine import Board, Unit, DomainHook
    from tests.test_replay_contracts import log_snapshot
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    at = NOW+timedelta(seconds=2)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='captured-after-fight',
        board=Board((Unit('unit', position=1),))), timestamp=at.isoformat())
    sessions.append_event('fight_start', {'round_id': '3-2', 'opponent_id': 'rival'},
        timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=3)).isoformat())
    report = review(sessions, store, (DomainHook('board-calls', (), advice=board_calls),))
    points = [row for row in report.timeline if row['category'] == 'positioning']
    first = next(row for row in points if row['log_seq'] == 1)
    assert first['player_choice']['observed_log_seq'] == 1
    assert first['differed'] is True
    assert next(row for row in points if row['log_seq'] == 2)['player_choice'] is None


def test_pinned_line_is_scored_beside_engine_recommendation_in_normal_surface(tmp_path):
    from tests.test_session_controls import pin_payload
    from tests.test_replay_contracts import log_snapshot
    from tft_review import ReplayProducer, ReviewPolicy
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    sessions.append_event('line_pin', pin_payload(data), timestamp=(NOW+timedelta(seconds=.1)).isoformat())
    at = NOW+timedelta(seconds=.2)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='pinned'), timestamp=at.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=1)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    report = ReviewPolicy(min_cost=.05).build(batch, data=data)
    line = report.surface['lines'][1]
    assert line['pinned']['line_id'] == 'kept-line'
    assert line['pin_cost'] == line['recommended']['expected_placement'] - line['pinned']['expected_placement']
    assert line['pin_cost'] <= 0


def changing_choice_ids(context):
    from tft_engine import Advice, ScoredOption
    suffix = context.snapshot.snapshot_id
    return (Advice('augment', 'Pick A', 'act_this_phase', .9, 'fixture', option_id='a:'+suffix,
        options=(ScoredOption('a:'+suffix, 'pick', {'augment_id': 'A', 'slot': 0}, 3),
            ScoredOption('b:'+suffix, 'pick', {'augment_id': 'B', 'slot': 1}, 4))),)


def test_semantically_same_deviation_groups_when_scored_option_id_changes(tmp_path):
    from tft_engine import DomainHook
    from tests.test_replay_contracts import log_snapshot
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='baseline')
    log_pick(sessions, 'B', 1)
    at = NOW+timedelta(seconds=2)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='next', gold=17), timestamp=at.isoformat())
    log_pick(sessions, 'B', 1, at=NOW+timedelta(seconds=3))
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    report = review(sessions, store, (DomainHook('augment', (), advice=changing_choice_ids),))
    moments = [row for row in report.moments if row['category'] == 'augment']
    assert len(moments) == 1
    assert len(moments[0]['members']) == 2
    assert moments[0]['cost'] == -2


@pytest.mark.parametrize(('schedule_key', 'schedule_value', 'second_round', 'members'), [
    ('levels', 2, '3-4', [1, 1]),
    ('rolls', 10, '3-4', [1, 1]),
    ('levels', 2, '3-3', [2]),
    ('rolls', 10, '3-3', [2]),
])
def test_line_grouping_preserves_round_schedules_and_ignores_option_ids(
    tmp_path, schedule_key, schedule_value, second_round, members
):
    from dataclasses import replace
    from tft_engine import Line, ScoredOption, simulate_lines
    from tft_review import ReplayProducer, ReviewPolicy
    from tft_review.contracts import json_value
    from tests.test_replay_contracts import log_snapshot

    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='baseline')
    at = NOW+timedelta(seconds=.25)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='second', gold=19),
        timestamp=at.isoformat())
    rounds = list(data.value('round_order'))
    for index, round_id in enumerate(rounds[rounds.index('3-3'):rounds.index('4-7')+1]):
        at = NOW+timedelta(seconds=index+1)
        if index == 0:
            sessions.append_event('level_up', {'before': {'level': 1, 'xp': 0, 'xp_to_level': 2},
                'after': {'level': 3, 'xp': 0, 'xp_to_level': 6}, 'before_read_at': NOW.isoformat(),
                'after_read_at': at.isoformat(), 'confidence': .95,
                'sources': {'level': 'external-fixture'}}, timestamp=at.isoformat())
        sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id=round_id, level=3)
            | {'round_id': round_id}, timestamp=at.isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=1)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    contexts, records = [], []
    for index, context in enumerate(batch.contexts):
        if index > 1:
            contexts.append(context)
            continue
        line = Line(f'declared-{index}',
            **{schedule_key: {'3-3' if index == 0 else second_round: schedule_value}})
        result = simulate_lines(batch.snapshot_for(context), batch.history_for(context), data,
            'guide', (line,), seed=context.seed, rollouts=4)[0]
        evaluation = json_value(context.evaluation)
        evaluation['plan']['line'] = line.to_dict()
        evaluation['line_results']['guide'] = [result.to_dict()]
        contexts.append(replace(context, evaluation=evaluation))
        record = next(row for row in batch.records if row.log_seq == context.log_seq and row.decision == 'econ')
        option = ScoredOption(line.id, 'line', line.to_dict(), result.expected_placement,
            result.standard_error).to_dict()
        advice = json_value(record.advice) | {'option_id': line.id, 'payload': {'line': line.to_dict()}}
        records.append(replace(record, advice=advice, options=(option,)))
    # Public typed replay input with concrete forecasts from the real simulator.
    report = ReviewPolicy(min_cost=.05).build(
        replace(batch, contexts=tuple(contexts), records=tuple(records)), data=data)
    assert len(report.timeline) == 2
    assert [len(moment['members']) for moment in report.moments] == members


def test_saved_tags_return_in_summary_and_survive_regeneration_and_cross_game_costs(tmp_path):
    from tft_engine import DomainHook
    from tft_review import ReviewService
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='baseline')
    log_pick(sessions, 'B', 1)
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    service = ReviewService(sessions, store, repository=ROOT, hooks=_hook())
    summary = service.produce('901')
    moment_id = summary['top5'][0]['moment_id']
    service.tag('901', moment_id, 'disagree')
    assert service.summary('901')['top5'][0]['tag'] == 'disagree'
    assert service.produce('901')['top5'][0]['tag'] == 'disagree'
    view = service.games()
    row = view['games'][0]
    assert abs(row['total_estimated_cost'] + 1.1) < 1e-10
    assert row['worst_category'] == 'augment'
    assert view['aggregates']['last10']['categories']['augment']['games'] == 1
    assert abs(view['aggregates']['last10']['categories']['augment']['value'] + 1.1) < 1e-10
    assert view['aggregates']['live_run']['games'] == 0


def aggregate_shop(context):
    from tft_engine import Advice, ScoredOption
    return (Advice('shop', 'Buy highlighted', 'act_this_phase', .9, 'fixture', option_id='shop',
        payload={'buys': [{'slot': 0, 'unit_id': 'unit'}]},
        options=(ScoredOption('shop:0:unit', 'buy', {'slot': 0, 'unit_id': 'unit'}),)),)


def two_purchase_shop(context):
    from tft_engine import Advice, ScoredOption
    buys = [{'slot': 0, 'unit_id': 'unit'}, {'slot': 1, 'unit_id': 'unit'}]
    return (Advice('shop', 'Buy both', 'act_this_phase', .9, 'fixture', option_id='shop',
        payload={'buys': buys}, options=tuple(
            ScoredOption(f'shop:{row["slot"]}:unit', 'buy', row) for row in buys)),)


@pytest.mark.parametrize(('shown_seconds', 'show_first', 'followed'), [
    (.25, True, True),
    (.3, True, True),
    (.3, False, None),
    (.4, False, None),
    (1, False, None),
    (1.5, False, None),
])
@pytest.mark.parametrize('purchase_count', [1, 2])
def test_shop_bundle_display_must_precede_first_purchase_to_attribute_following(
    tmp_path, shown_seconds, show_first, followed, purchase_count
):
    from tft_engine import DomainHook
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    hooks = (DomainHook('shop', (), advice=two_purchase_shop if purchase_count == 2 else aggregate_shop),)
    decision = _decision_id(sessions, store, decision='shop', hooks=hooks)
    log_delivery(sessions, decision_id=decision, option_id='shop', domain='shop',
        payload={'buys': [{'slot': slot, 'unit_id': 'unit'} for slot in range(purchase_count)]})
    if show_first:
        log_shown(sessions, decision_id=decision, option_id='shop', at=NOW+timedelta(seconds=shown_seconds))
    sessions.append_event('purchase', {'slot': 0, 'unit_id': 'unit', 'cost': 1, 'copies': 1},
        timestamp=(NOW+timedelta(seconds=.3)).isoformat())
    if not show_first:
        log_shown(sessions, decision_id=decision, option_id='shop', at=NOW+timedelta(seconds=shown_seconds))
    if purchase_count == 2:
        sessions.append_event('purchase', {'slot': 1, 'unit_id': 'unit', 'cost': 1, 'copies': 1},
            timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store, hooks)
    point = next(row for row in report.timeline if row['category'] == 'shop')
    assert point['shown']['status'] == ('followed' if followed else 'shown')
    assert point['shown']['followed'] is followed
    assert point['shown']['shown_at'] == (NOW+timedelta(seconds=shown_seconds)).isoformat()
    if followed is None:
        assert point['shown']['reason'] == 'display_not_confirmed_before_policy_onset'
    assert point['player_choice']['observed_at'] == (NOW+timedelta(seconds=1 if purchase_count == 2 else .3)).isoformat()
    assert report.summary['follow_rate']['eligible'] == (1 if followed else 0)


@pytest.mark.parametrize('purchase_count', [1, 2])
@pytest.mark.parametrize('late_seconds', [.3, 1.5])
def test_late_different_shop_bundle_cannot_replace_a_causal_display(tmp_path, purchase_count, late_seconds):
    from tft_engine import DomainHook
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    hooks = (DomainHook('shop', (), advice=two_purchase_shop if purchase_count == 2 else aggregate_shop),)
    decision = _decision_id(sessions, store, decision='shop', hooks=hooks)
    log_delivery(sessions, decision_id=decision, option_id='shop', domain='shop',
        payload={'buys': [{'slot': slot, 'unit_id': 'unit'} for slot in range(purchase_count)]})
    log_shown(sessions, decision_id=decision, option_id='shop', at=NOW+timedelta(seconds=.25))
    revision = 'sha256:'+'3'*64
    log_delivery(sessions, decision_id=decision, option_id='late-buy', domain='shop',
        payload={'buys': [{'slot': 4, 'unit_id': 'unit'}]}, at=NOW+timedelta(seconds=.27), revision=revision)
    for slot in range(purchase_count):
        sessions.append_event('purchase', {'slot': slot, 'unit_id': 'unit', 'cost': 1, 'copies': 1},
            timestamp=(NOW+timedelta(seconds=.3 if slot == 0 else 1)).isoformat())
    log_shown(sessions, decision_id=decision, option_id='late-buy', revision=revision,
        at=NOW+timedelta(seconds=late_seconds))
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = review(sessions, store, hooks)
    shown = next(row['shown'] for row in report.timeline if row['category'] == 'shop')
    assert shown['shown_option_id'] == 'shop'
    assert shown['followed'] is True
    assert report.summary['follow_rate']['value'] == 1.0


@pytest.mark.parametrize(('shown_seconds', 'followed', 'earlier_valid'), [
    (.2, True, False), (.25, True, False), (.4, None, False),
    (1.5, None, False), (20, None, False), (20, True, True),
])
def test_observed_line_display_must_precede_confirmed_level_action_bounds(
    tmp_path, shown_seconds, followed, earlier_valid
):
    from dataclasses import replace
    from tft_engine import Line, ScoredOption, simulate_lines
    from tft_review import ReplayProducer, ReviewPolicy
    from tft_review.contracts import json_value
    from tests.test_replay_contracts import log_snapshot

    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    original = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    context = original.contexts[0]
    record = next(row for row in original.records if row.decision == 'econ')
    line = Line('two-levels', levels={'3-3': 2, '3-4': 3})
    result = simulate_lines(original.snapshot_for(context), original.history_for(context), data,
        'guide', (line,), seed=context.seed, rollouts=4)[0]
    log_delivery(sessions, decision_id=record.decision_id, option_id=line.id, domain='econ',
        payload={'line': line.to_dict()}, at=NOW+timedelta(seconds=.1))
    if earlier_valid:
        log_shown(sessions, decision_id=record.decision_id, option_id=line.id, at=NOW+timedelta(seconds=.2))
        log_delivery(sessions, decision_id=record.decision_id, option_id='late-hold', domain='econ',
            payload={'line': Line('late-hold').to_dict()}, at=NOW+timedelta(seconds=.3),
            revision='sha256:'+'3'*64)
    log_shown(sessions, decision_id=record.decision_id, option_id='late-hold' if earlier_valid else line.id,
        at=NOW+timedelta(seconds=shown_seconds), revision='sha256:'+('3' if earlier_valid else '1')*64)
    rounds = list(data.value('round_order'))
    for index, round_id in enumerate(rounds[rounds.index('3-3'):rounds.index('4-7')+1]):
        at = NOW+timedelta(seconds=index+1)
        if index < 2:
            before_at = NOW+timedelta(seconds=.25 if index == 0 else 1.25)
            sessions.append_event('level_up', {'before': {'level': index+1, 'xp': 0, 'xp_to_level': 2},
                'after': {'level': index+2, 'xp': 0, 'xp_to_level': 6},
                'before_read_at': before_at.isoformat(), 'after_read_at': at.isoformat(),
                'confidence': .95, 'sources': {'level': 'external-fixture'}}, timestamp=at.isoformat())
        sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id=round_id, level=min(index+2, 3))
            | {'round_id': round_id}, timestamp=at.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=21)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    record = next(row for row in batch.records if row.decision == 'econ' and row.log_seq == 1)
    evaluation = json_value(batch.contexts[0].evaluation)
    evaluation['plan']['line'] = line.to_dict()
    evaluation['line_results']['guide'] = [result.to_dict()]
    contexts = (replace(batch.contexts[0], evaluation=evaluation),) + batch.contexts[1:]
    option = ScoredOption(line.id, 'line', line.to_dict(), result.expected_placement,
        result.standard_error).to_dict()
    record = replace(record, advice=json_value(record.advice) | {'option_id': line.id,
        'payload': {'line': line.to_dict()}}, options=(option,))
    report = ReviewPolicy(min_cost=.05).build(replace(batch, contexts=contexts, records=(record,)), data=data)
    point = report.timeline[0]
    assert point['player_choice'] is not None, dict(point['unavailable'])
    assert point['shown']['followed'] is followed
    assert point['shown']['status'] in (('followed', 'engine_error') if followed else ('shown',))
    if followed is None:
        assert point['shown']['reason'] == 'display_not_confirmed_before_policy_onset'
        assert report.summary['follow_rate']['eligible'] == 0
    assert point['cost'] is not None
    assert point['shown']['shown_option_id'] == line.id
    assert point['player_choice']['observed_at'] == batch.contexts[-1].timestamp


def test_shop_buy_bundle_is_followed_when_confirmed_purchases_match_shown_bundle(tmp_path):
    from tft_engine import DomainHook
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    hooks = (DomainHook('shop', (), advice=aggregate_shop),)
    decision = _decision_id(sessions, store, decision='shop', hooks=hooks)
    log_delivery(sessions, decision_id=decision, option_id='shop', domain='shop',
        payload={'buys': [{'slot': 0, 'unit_id': 'unit'}]})
    log_shown(sessions, decision_id=decision, option_id='shop')
    sessions.append_event('purchase', {'slot': 0, 'unit_id': 'unit', 'cost': 1, 'copies': 1},
        timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    point = next(row for row in review(sessions, store, hooks).timeline if row['category'] == 'shop')
    assert point['differed'] is False
    assert point['shown']['followed'] is True, dict(point['unavailable'])


def test_shop_bundle_does_not_hide_an_additional_unscored_purchase(tmp_path):
    from tft_engine import DomainHook
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    hooks = (DomainHook('shop', (), advice=aggregate_shop),)
    decision = _decision_id(sessions, store, decision='shop', hooks=hooks)
    log_delivery(sessions, decision_id=decision, option_id='shop', domain='shop',
        payload={'buys': [{'slot': 0, 'unit_id': 'unit'}]})
    log_shown(sessions, decision_id=decision, option_id='shop')
    for slot in (0, 1):
        sessions.append_event('purchase', {'slot': slot, 'unit_id': 'unit', 'cost': 1, 'copies': 1},
            timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    point = next(row for row in review(sessions, store, hooks).timeline if row['category'] == 'shop')
    assert point['shown']['followed'] is False
    assert point['shown']['status'] == 'ignored'
    assert len(point['player_choice']['payload']['buys']) == 2


@pytest.mark.parametrize(('display_when', 'earlier_valid', 'followed'), [
    ('before', False, True), ('equal', False, None), ('after', False, None), ('after', True, True),
])
def test_unchanged_line_display_uses_completion_when_no_action_onset_or_sequence_is_available(
    tmp_path, display_when, earlier_valid, followed
):
    from dataclasses import replace
    from tft_engine import Line
    from tests.test_replay_contracts import log_snapshot
    from tft_review import ReplayProducer, ReviewPolicy
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    econ = next(row for row in batch.records if row.decision == 'econ')
    log_delivery(sessions, decision_id=econ.decision_id, option_id=econ.advice['option_id'], domain='econ', payload=econ.to_dict()['advice']['payload'])
    if earlier_valid:
        log_shown(sessions, decision_id=econ.decision_id, option_id=econ.advice['option_id'])
        log_delivery(sessions, decision_id=econ.decision_id, option_id='late-level', domain='econ',
            payload={'line': Line('late-level', levels={'3-3': 2}).to_dict()}, revision='sha256:'+'3'*64)
    at = NOW+timedelta(seconds=1)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='confirmed-hold'), timestamp=at.isoformat())
    rounds = list(data.value('round_order'))
    for index, round_id in enumerate(rounds[rounds.index('3-2')+1:rounds.index('4-7')+1]):
        at = NOW+timedelta(seconds=index+2)
        sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id=round_id)|{'round_id': round_id}, timestamp=at.isoformat())
    shown_at = NOW+timedelta(seconds=.4) if display_when == 'before' else at+timedelta(seconds=display_when == 'after')
    log_shown(sessions, decision_id=econ.decision_id, option_id='late-level' if earlier_valid else econ.advice['option_id'],
        at=shown_at, revision='sha256:'+('3' if earlier_valid else '1')*64)
    sessions.end_game(timestamp=(at+timedelta(seconds=2)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    record = next(row for row in batch.records if row.decision == 'econ' and row.log_seq == 1)
    report = ReviewPolicy(min_cost=.05).build(replace(batch, records=(record,)), data=data)
    point = next(row for row in report.timeline if row['category'] == 'econ')
    assert point['player_choice']['payload']['action_log_seqs'] == ()
    assert point['shown']['followed'] is followed, dict(point['unavailable'])
    assert point['player_choice']['observed_at'] == batch.contexts[-1].timestamp
    if followed:
        assert point['shown']['shown_option_id'] == econ.advice['option_id']
    else:
        assert point['shown']['status'] == 'shown'
        assert point['shown']['reason'] == 'display_not_confirmed_before_policy_onset'
        assert report.summary['follow_rate']['eligible'] == 0


def _board_game(tmp_path, *, unchanged_read_at=None, show_at=.5):
    """Positioning and pivot calls whose board change is first read at NOW+1s."""
    from tft_engine import Board, Unit, DomainHook
    from tests.test_replay_contracts import log_snapshot
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    hooks = (DomainHook('board-calls', (), advice=board_calls),)
    ids = {kind: _decision_id(sessions, store, kind, hooks) for kind in ('positioning', 'pivot')}
    for kind, option in (('positioning', 'layout'), ('pivot', 'new-comp')):
        revision = 'sha256:'+('4' if kind == 'pivot' else '5')*64
        log_delivery(sessions, decision_id=ids[kind], option_id=option, domain=kind, revision=revision)
        log_shown(sessions, decision_id=ids[kind], option_id=option, revision=revision,
            at=NOW+timedelta(seconds=show_at))
    if unchanged_read_at is not None:
        at = NOW+timedelta(seconds=unchanged_read_at)
        sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='unchanged'),
            timestamp=at.isoformat())
    at = NOW+timedelta(seconds=1)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='moved',
        board=Board((Unit('unit', position=1),)), comp_lock='new-comp'), timestamp=at.isoformat())
    sessions.append_event('fight_start', {'round_id': '3-2', 'opponent_id': 'rival'},
        timestamp=(NOW+timedelta(seconds=1.1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=3)).isoformat())
    report = review(sessions, store, hooks)
    return report, {row['category']: row for row in report.timeline if row['log_seq'] == 1}


def test_board_call_shown_between_reads_cannot_prove_the_change_followed_the_display(tmp_path):
    report, points = _board_game(tmp_path)
    for kind in ('positioning', 'pivot'):
        assert points[kind]['player_choice'] is not None
        shown = points[kind]['shown']
        assert shown['status'] == 'shown', kind
        assert shown['followed'] is None
        assert shown['reason'] == 'display_not_confirmed_before_policy_onset'
    assert report.summary['follow_rate']['eligible'] == 0
    assert report.plan_timeline[0]['called_status'] == 'called_action_unknown'


def test_board_call_shown_before_a_later_unchanged_read_attributes_following(tmp_path):
    report, points = _board_game(tmp_path, unchanged_read_at=.7)
    shown = points['positioning']['shown']
    assert shown['status'] == 'followed'
    assert shown['followed'] is True
    assert points['positioning']['player_choice']['observed_started_at'] == (NOW+timedelta(seconds=.7)).isoformat()


def _outcome_review(tmp_path, *, outcome=True):
    """A finished, unlocked Baseline game whose Riot outcome uses distinctive PUUIDs."""
    from tft_core.storage import SessionStore
    from tft_review import ReviewService
    from tests.test_outcomes import match_fixture
    from tests.test_replay_contracts import historical_data, log_snapshot
    store, data = historical_data(tmp_path)
    sessions = SessionStore(tmp_path / 'logs', tmp_path / 'config', live_installed=True)
    sessions.set_mode('baseline')
    sessions.start_game('901', patch=data.patch, data_snapshot_id=data.snapshot_id, set_id='18', queue_id=1100,
        model_version='reader-fixture-v1', engine_version='historical-engine', timestamp=NOW.isoformat())
    sessions.append_event('snapshot', log_snapshot(data), timestamp=NOW.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    if outcome:
        match = match_fixture()
        for row in match['info']['participants']:
            row['puuid'] = f'PUUID-SECRET-{row["placement"]}'
        sessions.record_outcome('901', match, owner_puuid='PUUID-SECRET-4')
    service = ReviewService(sessions, store, repository=ROOT)
    service.produce('901')
    return sessions, service


def _served_pages(service, path=(), seen=None):
    """Every value reachable through the protected paged evidence route."""
    seen = [] if seen is None else seen
    cursor = 0
    while cursor is not None:
        page = service.detail('901', path=path, cursor=cursor, limit=128)
        seen.append(page)
        for item in page['items']:
            if 'value' not in item and page['kind'] != 'string':
                _served_pages(service, tuple(item['path']), seen)
        cursor = page['next_cursor']
    return seen


def test_served_review_uses_validated_outcome_placement_and_never_exposes_puuids(tmp_path):
    import json
    sessions, service = _outcome_review(tmp_path)
    summary = service.summary('901')
    assert summary['placement']['value'] == 4
    assert summary['placement']['source'] == 'riot_match'
    served = [summary, service.games(), *_served_pages(service)]
    stored = (sessions.root / 'reviews' / '901.json').read_text()
    for text in (stored, *(json.dumps(value) for value in served)):
        assert 'PUUID-SECRET' not in text
    outcome = service.detail('901', path=('evidence', 'final_outcome', 'participants', 3, 'participant_id'))
    assert outcome['items'][0]['value'] == 'owner'


def test_missing_or_invalid_outcome_keeps_review_placement_unavailable_with_reason(tmp_path):
    _, service = _outcome_review(tmp_path, outcome=False)
    assert service.summary('901')['placement'] == {'value': None, 'reason': 'final_placement_unavailable', 'source': None}
    invalid = tmp_path / 'invalid'
    invalid.mkdir()
    sessions, service = _outcome_review(invalid)
    path = sessions.root / 'outcomes' / '901.json'
    path.write_text(path.read_text().replace('"placement": 4', '"placement": 9', 1))
    service.produce('901')
    assert service.summary('901')['placement'] == {'value': None, 'reason': 'outcome_artifact_invalid', 'source': None}


def test_locked_game_with_confirmed_outcome_exposes_no_placement_or_detail(tmp_path):
    import json
    import pytest
    from tft_core.storage import SessionStore
    from tft_core.review_transport import ReviewTransport
    from tft_review import ReviewService
    from tests.test_outcomes import match_fixture
    from tests.test_replay_contracts import historical_data, log_snapshot
    store, data = historical_data(tmp_path)
    sessions = SessionStore(tmp_path / 'logs', tmp_path / 'config', live_installed=True)
    sessions.set_mode('silent')
    sessions.start_game('901', patch=data.patch, data_snapshot_id=data.snapshot_id, set_id='18', queue_id=1100,
        model_version='reader-fixture-v1', engine_version='historical-engine', timestamp=NOW.isoformat())
    sessions.append_event('snapshot', log_snapshot(data), timestamp=NOW.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    sessions.record_outcome('901', match_fixture(), owner_puuid='owner')
    service = ReviewService(sessions, store, repository=ROOT)
    service.produce('901')
    assert sessions.list_games()[0]['review_locked'] is True
    summary = service.summary('901')
    assert summary['locked'] is True and summary['placement']['value'] is None
    row, = service.games()['games']
    assert row['placement'] is None and row['category_costs'] == {} and row['total_estimated_cost'] is None
    assert service.games()['aggregates']['last10']['categories'] == {}
    transport = ReviewTransport(sessions, service)
    with pytest.raises(ValueError, match='locked'):
        transport.call('regenerate', '901')
    with pytest.raises((ValueError, PermissionError)):
        transport.call('page', '901', report_id=None, evidence_id=None, path=('evidence',), cursor=0, limit=8)
    with pytest.raises(PermissionError):
        service.detail('901', path=('evidence', 'final_outcome'))
    assert '"placement": 4' not in json.dumps([summary, service.games()])
