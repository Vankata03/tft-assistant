"""Review attribution over real logs: shown advice, follow status and choices."""
from datetime import timedelta

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
        at=NOW+timedelta(seconds=.2), revision='sha256:'+'1'*64):
    """The advice_delivery event format written by LiveDeliveryController.activate."""
    return sessions.append_event('advice_delivery', {'schema_version': 1, 'delivery_revision': revision,
        'game_id': '901', 'snapshot_id': snapshot_id, 'data_snapshot_id': None, 'model_hash': None,
        'captured_at': NOW.isoformat(), 'evaluated_at': at.isoformat(), 'evidence_id': 'sha256:'+'2'*64,
        'summary': {'game_id': '901', 'snapshot_id': snapshot_id, 'advice': [{'decision_id': decision_id,
            'option_id': option_id, 'domain': domain, 'action': 'Pick', 'payload': {}}]}},
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


def test_live_advice_never_delivered_or_shown_after_the_choice_is_a_capture_gap(tmp_path):
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
    assert shown['status'] == 'capture_gap'
    assert shown['cause'] == 'shown_after_choice'


def test_silent_and_baseline_decisions_keep_their_mode_status(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='silent')
    log_pick(sessions, 'B', 1)
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    assert augment_moment(review(sessions, store))['shown'] == {'status': 'no_advice_in_silent_mode'}
