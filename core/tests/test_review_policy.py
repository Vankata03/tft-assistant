"""Review policies exercised through real append-only logs and historical replay."""
from datetime import timedelta

from tests.test_replay_contracts import NOW, ROOT, logged_game, log_snapshot


def test_semantic_replay_keeps_every_raw_poll_but_values_only_changed_information(tmp_path):
    from tft_review import ReplayProducer

    sessions, store, data, first = logged_game(tmp_path, finish=False, mode='baseline')
    for index in range(1, 5):
        at = NOW + timedelta(seconds=index / 4)
        sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id=f'poll-{index}'),
            timestamp=at.isoformat())
    at = NOW + timedelta(seconds=1.25)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='gold-change', gold=8),
        timestamp=at.isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=1)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT, decision_segmentation='semantic').produce('901')
    assert len(batch.contexts) == 6
    assert len([context for context in batch.contexts if context.evaluation is not None]) == 2
    assert batch.contexts[1].unavailable == ('semantic_duplicate',)
    assert batch.contexts[1].validity_annotations[0]['evaluation_log_seq'] == first['seq']
    assert [context.snapshot['snapshot_id'] for context in batch.contexts] == [
        'original', 'poll-1', 'poll-2', 'poll-3', 'poll-4', 'gold-change']
    assert batch.contexts[-1].snapshot['fields']['gold']['value'] == 8
    assert batch.contexts[-1].prefix_through_seq == 5
    assert {record.log_seq for record in batch.records} == {1, 6}


def augment_choices(context):
    from tft_engine import Advice, ScoredOption
    return (Advice('augment', 'Pick A', 'act_this_phase', .9, 'fixture-model',
        decision_id=context.snapshot.snapshot_id+':augment', option_id='a',
        options=(ScoredOption('a', 'pick', {'augment_id': 'A', 'slot': 0}, 3.1),
                 ScoredOption('b', 'pick', {'augment_id': 'B', 'slot': 1}, 4.2))),)


def timer_advice(context):
    from tft_engine import Advice
    return (Advice('clock', 'Declared timer dependency', 'information', .9, 'fixture-model',
        payload={'timer':context.snapshot.field('timer')}),)


def test_semantic_replay_ignores_timer_polls_but_keeps_expiry_and_declared_hook_dependencies(tmp_path):
    from tft_engine import DomainHook
    from tft_review import ReplayProducer

    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='baseline')
    for index in range(1, 5):
        at = NOW+timedelta(seconds=index/4)
        sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id=f'timer-{index}',
            timer=30-index), timestamp=at.isoformat())
    at = NOW+timedelta(seconds=3)
    stale = log_snapshot(data, at=at, snapshot_id='ownership-expired', timer=20)
    stale['fields']['board']['read_at'] = NOW.isoformat()
    sessions.append_event('snapshot', stale, timestamp=at.isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=1)).isoformat())
    default = ReplayProducer(sessions, store, repository=ROOT, decision_segmentation='semantic').produce('901')
    assert len(default.contexts) == 6
    assert sum(context.evaluation is not None for context in default.contexts) == 2
    assert default.contexts[4].snapshot['fields']['timer']['value'] == 26
    assert default.contexts[4].unavailable == ('semantic_duplicate',)
    assert default.contexts[-1].snapshot['fields']['board']['read_at'] == NOW.isoformat()
    assert not default.contexts[-1].evaluation['line_results']
    declared = ReplayProducer(sessions, store, repository=ROOT,
        hooks=(DomainHook('clock', (), advice=timer_advice, dependency_fields=('timer',)),),
        decision_segmentation='semantic').produce('901')
    assert sum(context.evaluation is not None for context in declared.contexts) == 6
    assert default.identity['hook_hash'] != declared.identity['hook_hash']


def test_review_attributes_confirmed_pick_and_preserves_signed_cost_without_fabricating_shown(tmp_path):
    from tft_engine import DomainHook
    from tft_review import ReplayProducer, ReviewPolicy

    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='baseline')
    sessions.append_event('augment_pick', {'slot': 1, 'augment_id': 'B',
        'choice_token': 'confirmed-fixture-offer', 'evidence': 'positive_pick_confirmation'},
        timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT,
        hooks=(DomainHook('augment', (), advice=augment_choices),)).produce('901')
    report = ReviewPolicy(min_cost=.05).build(batch)
    moment = next(row for row in report.moments if row['category'] == 'augment')
    assert abs(moment['cost'] - (-1.1)) < 1e-10
    assert moment['player_choice']['option_id'] == 'b'
    assert moment['shown']['status'] == 'no_advice_in_baseline_mode'
    assert report.summary['category_costs']['augment']['value'] == moment['cost']
    assert report.summary['follow_rate'] == {'value': None, 'reason': 'no_acknowledged_eligible_advice', 'eligible': 0}
    assert report.summary['top5'][0]['moment_id'] == moment['moment_id']
    assert moment['engine_decision_id'] != moment['moment_id']
    assert moment['paired_uncertainty'] is None
    assert moment['unavailable']['paired_uncertainty'] == 'paired_rollouts_unavailable'
    assert len(report.evidence['replay']['observations']) == len(batch.observations)


def test_review_service_guards_each_route_and_serves_only_scored_option_paths(tmp_path):
    import pytest
    from tft_review import ReviewService

    sessions, store, _, _ = logged_game(tmp_path)
    service = ReviewService(sessions, store, repository=ROOT)
    summary = service.produce('901')
    assert summary['locked'] is True
    assert summary['top5'] == []
    assert summary['category_costs']['reason'] == 'review_locked'
    assert 'evidence_graph' not in summary
    for operation in (lambda: service.detail('901', path=('timeline',)),
        lambda: service.what_if('901', 'unknown', 'unknown'),
        lambda: service.tag('901', 'unknown', 'agree')):
        with pytest.raises(PermissionError, match='locked'):
            operation()

    # A Baseline log is unlocked; no artificial start-run manifest is needed.
    second = tmp_path / 'unlocked'
    second.mkdir()
    sessions, store, _, _ = logged_game(second, mode='baseline')
    service = ReviewService(sessions, store, repository=ROOT)
    summary = service.produce('901')
    assert summary['schema_version'] == 1 and summary['locked'] is False
    assert summary['report_id'] and summary['evidence_id']
    page = service.detail('901', path=('timeline',), limit=2, max_bytes=2048)
    assert page['evidence_id'] == summary['evidence_id']
    assert page['total'] > 0
    moment = service.detail('901', path=('moments', 0))
    fields = {row['path'][-1]: row.get('value') for row in moment['items']}
    moment_id = fields['moment_id']
    service.tag('901', moment_id, 'disagree')
    assert sessions.read_review('901')['tags'][moment_id] == 'disagree'
    with pytest.raises(ValueError, match='scored'):
        service.what_if('901', moment_id, 'invented-replacement')
    with pytest.raises(ValueError, match='member'):
        service.detail('901', path=('../other-game',))


def paired_augment_choices(context):
    from tft_engine import Advice, ScoredOption
    common = {'seed': context.seed}
    return (Advice('augment', 'Pick A', 'act_this_phase', .9, 'fixture-model',
        decision_id=context.snapshot.snapshot_id+':augment', option_id='a',
        options=(ScoredOption('a', 'pick', {'augment_id': 'A', 'slot': 0,
                     'after': dict(common, rollout_placements=[2, 4])}, 3.1, 99),
                 ScoredOption('b', 'pick', {'augment_id': 'B', 'slot': 1,
                     'after': dict(common, rollout_placements=[4, 4])}, 4.2, 99))),)


def test_protected_top5_expands_by_authenticated_moment_path_not_the_hashed_id(tmp_path):
    from tft_engine import DomainHook
    from tft_review import ReviewService

    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='baseline')
    sessions.append_event('augment_pick', {'slot': 1, 'augment_id': 'B', 'choice_token': 'offer',
        'evidence': 'positive_pick_confirmation'}, timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    service = ReviewService(sessions, store, repository=ROOT,
        hooks=(DomainHook('augment', (), advice=paired_augment_choices),))
    summary = service.produce('901')
    top = summary['top5'][0]
    assert top['moment_path'][0] == 'moments'
    assert isinstance(top['moment_path'][1], int)
    assert top['engine_choice']['option_id'] == 'a'
    assert top['player_choice']['option_id'] == 'b'
    assert 'payload' not in top['engine_choice']
    assert top['keyframe'] == {'media_name': None, 'reason': 'logged_keyframe_unavailable'}
    page = service.detail('901', path=top['moment_path'], max_bytes=2048)
    fields = {row['path'][-1]: row.get('value') for row in page['items']}
    assert fields['moment_id'] == top['moment_id']
    option = service.what_if('901', top['moment_id'], 'b')
    assert option['simulation'] == 'already_scored'
    assert option['evidence_id'] == summary['evidence_id']


def test_top5_keyframe_is_a_logged_causal_media_reference_not_a_filesystem_path(tmp_path):
    from PIL import Image
    from tft_engine import DomainHook
    from tft_review import ReviewService

    sessions,store,data,_ = logged_game(tmp_path,finish=False,mode='baseline')
    image = Image.new('RGB',(3,3),'blue') # External capture fixture; no production image.
    name = sessions.write_keyframe(image,reason='augment_offer',timestamp=(NOW+timedelta(seconds=.5)).isoformat())
    sessions.append_event('snapshot',log_snapshot(data,at=NOW+timedelta(seconds=1),snapshot_id='offer-read',gold=17),
        timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.append_event('augment_pick',{'slot':1,'augment_id':'B','choice_token':'offer',
        'evidence':'positive_pick_confirmation'},timestamp=(NOW+timedelta(seconds=2)).isoformat())
    sessions.write_keyframe(image,reason='later-outcome',timestamp=(NOW+timedelta(seconds=2.5)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=3)).isoformat())
    service = ReviewService(sessions,store,repository=ROOT,
        hooks=(DomainHook('augment',(),advice=paired_augment_choices),))
    top = service.produce('901')['top5'][0]
    assert top['keyframe']['media_name'] == name
    assert top['keyframe']['reason'] is None
    assert top['keyframe']['logged_reason'] == 'augment_offer'
    assert top['keyframe']['timestamp'] == (NOW+timedelta(seconds=.5)).isoformat()
    assert name.startswith('media/') and name.endswith('.webp')


def test_protected_section_paths_expose_typed_chart_values_without_rollout_hydration(tmp_path):
    from tft_review import ReviewService

    sessions,store,_,_ = logged_game(tmp_path,mode='baseline')
    service = ReviewService(sessions,store,repository=ROOT)
    summary = service.produce('901')
    assert summary['section_paths']['lines'] == ['surface','lines']
    assert summary['section_paths']['fights'] == ['surface','fights']
    assert summary['section_paths']['debug'] == ['debug']
    page = service.detail('901',path=summary['section_paths']['lines'],limit=1,max_bytes=2048)
    path = page['items'][0]['path']
    def scalar(field):
        result = service.detail('901',path=path+[field],max_bytes=512)
        return result['items'][0]['value']
    assert scalar('round_id') == '3-2'
    observed = service.detail('901',path=path+['observed'],max_bytes=1024)
    assert {row['path'][-1]:row['value'] for row in observed['items']} == {'gold':18,'hp':73,'level':1}
    fields = {row['path'][-1] for row in service.detail('901',path=path+['recommended'],max_bytes=2048)['items']}
    assert 'projections' in fields and 'line_id' in fields
    assert 'rollout_placements' not in fields and 'rollout_deaths' not in fields
    # Full raw evidence remains independently accessible through the Debug/evidence path.
    raw = service.detail('901',path=('evidence','replay','contexts',0,'evaluation','line_results','guide',0),max_bytes=2048)
    assert any(row['path'][-1] == 'rollout_placements' for row in raw['items'])


def test_review_job_identity_binds_finished_log_and_original_pin_before_publication(tmp_path):
    import pytest
    from tft_review import ReviewService

    sessions,store,data,_ = logged_game(tmp_path,finish=False,mode='baseline')
    service = ReviewService(sessions,store,repository=ROOT)
    with pytest.raises(ValueError,match='finished'):
        service.job_identity('901')
    sessions.end_game(timestamp=(NOW+timedelta(seconds=1)).isoformat())
    identity = service.job_identity('901')
    assert identity['data_snapshot_id'] == data.snapshot_id
    assert identity['engine_version']
    assert len(identity['job_id']) == 64
    assert identity == service.job_identity('901')
    # A later committed observation changes the job and cannot publish under the old receipt.
    import json
    events = sessions.read_events('901')
    # External committed-file change, as when a recovered log receives an annotation.
    with sessions.log_path('901').open('a',encoding='utf-8') as output:
        output.write(json.dumps({'v':1,'seq':len(events),'kind':'reader_tracker_disagreement',
            'timestamp':(NOW+timedelta(seconds=2)).isoformat(),
            'payload':{'reason':'later annotation'}})+'\n')
    assert service.job_identity('901')['job_id'] != identity['job_id']
    with pytest.raises(ValueError,match='identity changed'):
        service.produce('901',expected_job_id=identity['job_id'])
    assert sessions.read_review('901') is None


def test_paired_difference_not_marginal_error_controls_close_calls_and_grouped_signed_cost(tmp_path):
    from tft_engine import DomainHook
    from tft_review import ReplayProducer, ReviewPolicy

    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='baseline')
    for index in range(2):
        if index:
            at = NOW+timedelta(seconds=2)
            sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='second', gold=17),
                timestamp=at.isoformat())
        sessions.append_event('augment_pick', {'slot': 1, 'augment_id': 'B',
            'choice_token': f'offer-{index}', 'evidence': 'positive_pick_confirmation'},
            timestamp=(NOW+timedelta(seconds=index*2+1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT,
        hooks=(DomainHook('augment', (), advice=paired_augment_choices),)).produce('901')
    report = ReviewPolicy(min_cost=.05).build(batch)
    points = [row for row in report.timeline if row['category'] == 'augment']
    assert len(points) == 2
    assert points[0]['paired_uncertainty'] == 1
    assert points[0]['close_call'] is False  # Marginal99 would incorrectly hide this.
    moments = [row for row in report.moments if row['category'] == 'augment']
    assert len(moments) == 1
    assert len(moments[0]['members']) == 2
    assert abs(moments[0]['cost'] + 2.2) < 1e-10
    assert report.summary['top5'][0]['cost'] == moments[0]['cost']
    assert report.summary['category_costs']['augment']['value'] == moments[0]['cost']


def test_review_replay_records_carry_the_same_attribution_as_surface_moments(tmp_path):
    from tft_engine import DomainHook
    from tft_review import ReplayProducer, ReviewPolicy

    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='baseline')
    sessions.append_event('augment_pick', {'slot': 1, 'augment_id': 'B', 'choice_token': 'offer',
        'evidence': 'positive_pick_confirmation'}, timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT,
        hooks=(DomainHook('augment', (), advice=paired_augment_choices),)).produce('901')
    report = ReviewPolicy(min_cost=.05).build(batch)
    record = next(row for row in report.evidence['replay']['records'] if row['decision'] == 'augment')
    assert abs(record['cost']+1.1) < 1e-10
    assert record['paired_uncertainty'] == 1
    assert record['observed_choice']['option_id'] == 'b'
    assert 'cost' not in record['unavailable']
    assert record['seed'] == batch.contexts[0].seed
    assert batch.records[-1].observed_choice is None  # Original frozen replay remains intact.


def test_report_keeps_plan_lines_fights_debug_and_positioning_as_separate_authenticated_sections(tmp_path):
    from tests.test_harness import combat_logs
    from tft_review import ReviewPolicy, ReplayProducer

    sessions, store = combat_logs(tmp_path, results=('loss',))
    batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    report = ReviewPolicy(min_cost=.05).build(batch, data=store.get(batch.identity['data_snapshot_id']))
    assert report.fights[0]['round_id'] == '3-2'
    assert report.fights[0]['win_probability'] == .5
    assert report.fights[0]['result'] == 'loss'
    assert report.fights[0]['predicted_hp_loss'] == 4.5
    assert report.fights[0]['actual_hp_loss'] == 5
    assert report.lines[0]['observed']['gold'] == 18
    assert report.lines[0]['observed']['level'] == 1
    assert report.plan_timeline[0]['candidates']
    assert report.plan_timeline[0]['called_status'] == 'display_attribution_unavailable'
    assert report.debug['raw_snapshot_count'] == 1
    assert report.debug['gap_events'] == ()
    assert not any(row['category'] == 'positioning' for row in report.moments)
    assert report.to_dict()['evidence']['replay']['observations'] == batch.to_dict()['observations']
