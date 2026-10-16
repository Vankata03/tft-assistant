"""Historical replay through real logs, immutable data and the shared Engine."""
from tests.test_harness_baseline import baseline_fixture

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import tomli_w

from tft_core.storage import SessionStore
from tft_data import DataStore, SourceState
from tft_data.config import REQUIRED_STATIC, TUNABLE_FAMILIES
from tft_engine import Board, FieldValue, GameSnapshot, Unit

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]


class GuideFeed:
    """Synthetic external Academy response, not an internal collaborator."""
    name, kind = 'academy-fixture', 'guides'

    def metadata(self):
        return SourceState(self.name, 'fixture', NOW, NOW, self.kind)

    def fetch(self):
        return {'guides': [{'id': 'guide', 'tier': 'S', 'finalComp': [{'apiName': 'unit'}],
            'earlyComp': [{'apiName': 'unit'}], 'mainChampion': 'unit', 'tips': [],
            'augments': [], 'carousel': [], 'altBuilds': [],
            'line': [{'round': '3-2', 'level': 1}]}]}


def historical_data(tmp_path):
    path = tmp_path / 'patch'
    path.mkdir()
    rounds = [f'{stage}-{round_number}' for stage in range(1, 7) for round_number in range(1, 8)]
    rules = {
        'team_capacity': {'levels': {str(level):level for level in range(1,11)}, 'trait_bonuses': [], 'held_augment_slots': {}, 'inventory_item_slots': {},'transition_policy':{'deploy':'reserve_before','swap':'remove_then_reserve','bench':'validate_after'}},
        'xp_table': {str(i): 2*i for i in range(1, 10)}, 'gold_by_round': {'default': 5},
        'streak_gold': {'2': 1}, 'interest': {'gold_per_tick': 10, 'gold_per_interest': 1, 'cap': 5},
        'player_damage': {'stage_base': {str(i): i+1 for i in range(1, 9)}, 'per_survivor': 1},
        'shop_odds': {str(i): [1, 0, 0, 0, 0] for i in range(1, 11)},
        'pool_sizes': {str(i): 20 for i in range(1, 6)},
        'rules_flags': {'pve_preserves_streak': True, 'passive_xp': 2, 'xp_buy_cost': 4,
            'xp_buy_amount': 4, 'roll_cost': 2, 'combat_win_gold': 1, 'champion_slots_max': 5,
            'unknown_wisp_slots': 4.5, 'pve_orb_gold': {r: 0 for r in rounds}},
        'wisps': {}, 'combat_buff_power': {}, 'wisp_round_cap': {'default': 1, 'trait_overrides': {}},
        'opening_encounters': {}, 'econ_augments': {},
        'augment_pools': {'silver': [], 'gold': [], 'prismatic': []},
        'threat_keywords': {'aoe': ['nearby'], 'backline_access': ['backline']},
        'bench_size': 9, 'item_recipes': {}, 'trait_rules': {},
        'stage_items': {str(i): {'finished': 0, 'component': 0, 'high_cost_finished': 0} for i in range(1, 9)},
        'level_calendar': {'1-1': 1, '3-1': 1, '4-1': 1}, 'lobby_top4_rate': .5,
        'round_order': rounds, 'round_types': {r: 'pve' for r in rounds},
        'sell_values': {str(c): {'1': c, '2': 3*c, '3': 9*c} for c in range(1, 6)},
    }
    tunables = {name: 1 for name in TUNABLE_FAMILIES}
    tunables.update({'rollouts_full': 4, 'rollouts_reroll': 2, 'gold_floors': [10, 0],
        'commit_latest_round': '3-2', 'opponent_growth_curve': {}, 'default_lines_by_carry_cost': {},
        'confidence_show_min': .2, 'confidence_medium_min': .5, 'confidence_high_min': .8,
        'cost_star_baseline': {str(c): {str(s): c+s-1 for s in (1, 2, 3)} for c in range(1, 6)},
        'item_values': {'finished': 1, 'component': .35, 'high_cost_bonus': .25},
        'win_scale_by_stage': {}, 'survivor_scale_by_stage': {str(i): 1 for i in range(1, 9)},
        'opponent_star_mix': {'1-1': {str(c): [1, 0, 0] for c in range(1, 6)}},
        'emblem_count_prior': {'0': 1}, 'size_level_prior': {'1': {'1': 1}},
        'classifier_weights': {'carry': 3, 'key': 2, 'other': 1, 'bench': .5},
        'field_max_age_seconds': {'default': 2, 'shop_roll_down': .5},
        'pivot_margin_by_stage': {'default': .5, 'post_roll_down': .8}})
    (path / 'static.toml').write_text(tomli_w.dumps({'patch': 'fixture', 'set_number': 18,
        'fields': {name: {'value': rules[name], 'source': 'owner'} for name in REQUIRED_STATIC}}))
    (path / 'tunables.toml').write_text(tomli_w.dumps({'patch': 'fixture', 'fields': {
        name: {'value': value, 'source': 'owner', 'family': TUNABLE_FAMILIES[name]}
        for name, value in tunables.items()}}))
    (path / 'entities.json').write_text(json.dumps({'entities': [{'id': 'unit', 'kind': 'unit',
        'name': 'Fixture unit', 'cost': 1, 'traits': [],
        'values': {'team_slot_cost': {'value':1, 'source':'owner'},'play_rate': {'value': .5, 'source': 'owner'}}}]}))
    store = DataStore(tmp_path / 'data')
    result = store.refresh(path, now=NOW, sources=(GuideFeed(),))
    assert result.error is None
    assert result.snapshot.guides['guide'].units == ('unit',)
    return store, result.snapshot


def log_snapshot(data, *, at=NOW, snapshot_id='original', **changes):
    board = Board((Unit('unit', position=0),))
    fields = {'board': board, 'bench': [], 'inventory_complete': True,
        'phase': 'planning', 'planning_phase': True, 'gold': 18, 'hp': 73, 'level': 1,
        'xp': 0, 'streak': 0, 'lobby': {'rival': {'hp': 84}}, 'lobby_complete': True, 'slot_count': 5}
    fields.update(changes)
    snapshot = GameSnapshot('901', '3-2', at,
        {name: FieldValue(value, at, 'recorded-fixture', .95) for name, value in fields.items()}, snapshot_id).to_dict()
    return snapshot | {'data_snapshot_id': data.snapshot_id, 'stale_fields': [],
        'phase': 'planning', 'capture_copies': {'rgb_bytes': 120}}


def logged_game(tmp_path, *, finish=True, mode='silent', **fields):
    data_store, data = historical_data(tmp_path)
    sessions = SessionStore(tmp_path / 'logs', tmp_path / 'config', live_installed=True)
    sessions.set_mode(mode)
    sessions.start_game('901', patch=data.patch, data_snapshot_id=data.snapshot_id,
        model_version='reader-fixture-v1', engine_version='historical-engine', timestamp=NOW.isoformat())
    event = sessions.append_event('snapshot', log_snapshot(data, **fields), timestamp=NOW.isoformat())
    if finish:
        sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    return sessions, data_store, data, event


def test_frozen_replay_keeps_original_log_metadata_and_actual_engine_options_without_inferred_attribution(tmp_path):
    from tft_review import ReplayBatch, ReplayProducer

    sessions, data_store, data, event = logged_game(tmp_path)
    batch = ReplayProducer(sessions, data_store, repository=ROOT).produce('901')
    context = batch.contexts[0]
    assert context.log_seq == event['seq'] == 1
    assert context.snapshot['snapshot_id'] == 'original'
    assert context.snapshot['capture_copies'] == {'rgb_bytes': 120}
    assert context.game_start['model_version'] == 'reader-fixture-v1'
    assert context.data_snapshot_id == data.snapshot_id
    assert context.prefix_through_seq == 0
    econ = next(record for record in batch.records if record.decision == 'econ')
    assert econ.options, econ.advice
    assert any(option['expected_placement'] is not None for option in econ.options)
    assert econ.expected_placement is not None
    assert econ.observed_choice is econ.cost is econ.paired_uncertainty is econ.shown is None
    assert econ.unavailable['observed_choice'] == 'not_reconstructed'
    assert econ.seed == context.seed
    restored = ReplayBatch.from_dict(json.loads(json.dumps(batch.to_dict())))
    assert restored == batch
    with pytest.raises(TypeError):
        context.snapshot['fields']['gold']['value'] = 0
    assert context.snapshot['fields']['gold']['value'] == 18


def test_replay_history_prefix_excludes_later_sequences_and_future_dated_sightings(tmp_path):
    from tft_review import ReplayProducer

    sessions, data_store, data, _ = logged_game(tmp_path, finish=False)
    producer = ReplayProducer(sessions, data_store, repository=ROOT)
    original = producer.produce('901')
    sessions.append_event('sighting', {'opponent_id': 'future-rival', 'round_id': '3-2',
        'level': 1, 'traits': {}, 'hidden_traits': 0}, timestamp=(NOW+timedelta(seconds=5)).isoformat())
    sessions.append_event('snapshot', log_snapshot(data, at=NOW+timedelta(seconds=.25),
        snapshot_id='second'), timestamp=(NOW+timedelta(seconds=.25)).isoformat())
    sessions.append_event('sighting', {'opponent_id': 'known-rival', 'round_id': '3-2',
        'level': 1, 'traits': {}, 'hidden_traits': 0}, timestamp=(NOW+timedelta(seconds=.5)).isoformat())
    sessions.append_event('snapshot', log_snapshot(data, at=NOW+timedelta(seconds=1),
        snapshot_id='third', hp=20, gold=0), timestamp=(NOW+timedelta(seconds=1)).isoformat())
    batch = producer.produce('901')
    assert batch.contexts[0].evaluation == original.contexts[0].evaluation
    first_history = batch.history_for(batch.contexts[0])
    assert first_history.snapshots == first_history.sightings == ()
    second_history = batch.history_for(batch.contexts[1])
    assert [snapshot.snapshot_id for snapshot in second_history.snapshots] == ['original']
    assert isinstance(second_history.snapshots[0].field('board'), Board)
    assert second_history.sightings == ()
    third_history = batch.history_for(batch.contexts[2])
    assert [sighting.opponent_id for sighting in third_history.sightings] == ['known-rival']
    assert third_history.sightings[0].read_at == NOW+timedelta(seconds=.5)
    assert batch.contexts[0].snapshot['fields']['hp']['value'] == 73


def test_replay_uses_historical_data_and_preserves_stale_fields_and_gap_boundaries(tmp_path):
    from tft_review import ReplayProducer

    sessions, data_store, original, _ = logged_game(tmp_path, finish=False)
    import tomllib
    tunables_path = tmp_path / 'patch' / 'tunables.toml'
    changed = tomllib.loads(tunables_path.read_text())
    changed['fields']['gold_floors']['value'] = [20, 0]
    tunables_path.write_text(tomli_w.dumps(changed))
    refreshed = data_store.refresh(tmp_path / 'patch', now=NOW+timedelta(days=1)).snapshot
    assert refreshed.snapshot_id != original.snapshot_id
    stale = log_snapshot(original, at=NOW+timedelta(seconds=3), snapshot_id='stale')
    stale['fields']['gold']['read_at'] = NOW.isoformat()
    stale['stale_fields'] = ['gold']
    sessions.append_event('snapshot', stale, timestamp=(NOW+timedelta(seconds=3)).isoformat())
    sessions.append_event('capture_gap', {'start': (NOW+timedelta(seconds=2)).isoformat(),
        'end': (NOW+timedelta(seconds=4)).isoformat(), 'reason': 'window_unavailable'},
        timestamp=(NOW+timedelta(seconds=4)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=5)).isoformat())
    batch = ReplayProducer(sessions, data_store, repository=ROOT).produce('901')
    assert all(context.data_snapshot_id == original.snapshot_id for context in batch.contexts)
    assert batch.contexts[1].snapshot['fields']['gold']['read_at'] == NOW.isoformat()
    assert batch.contexts[1].snapshot['stale_fields'] == ('gold',)
    assert 'capture_gap' in batch.contexts[1].unavailable
    assert batch.contexts[1].evaluation is None
    assert not any(record.log_seq == 2 for record in batch.records)
    assert [row for row in batch.observations if row['kind'] == 'capture_gap'][0]['payload']['reason'] == 'window_unavailable'


@pytest.mark.parametrize('bad', ['wrong_game', 'changed_pin', 'future_field', 'naive_event', 'missing_fields', 'reversed_gap', 'bool_version'])
def test_committed_malformed_replay_records_fail_visibly(tmp_path, bad):
    from tft_review import ReplayProducer
    sessions, data_store, data, _ = logged_game(tmp_path, finish=False)
    payload = log_snapshot(data, snapshot_id='bad')
    kind, timestamp = 'snapshot', NOW.isoformat()
    if bad == 'wrong_game': payload['game_id'] = '902'
    elif bad == 'changed_pin': payload['data_snapshot_id'] = '0'*64
    elif bad == 'future_field': payload['fields']['gold']['read_at'] = (NOW+timedelta(seconds=1)).isoformat()
    elif bad == 'naive_event': timestamp = '2026-10-11T00:00:00'
    elif bad == 'missing_fields': payload = {'game_id': '901'}
    elif bad == 'reversed_gap':
        kind, payload = 'capture_gap', {'start': (NOW+timedelta(seconds=2)).isoformat(), 'end': NOW.isoformat(), 'reason': 'test'}
    sessions.append_event(kind, payload, timestamp=timestamp)
    if bad == 'bool_version':
        events = sessions.read_events('901')
        events[-1]['v'] = True
        sessions.log_path('901').write_text(''.join(json.dumps(row)+'\n' for row in events))
    with pytest.raises(ValueError, match='[Rr]eplay'):
        ReplayProducer(sessions, data_store, repository=ROOT).produce('901')


@pytest.mark.parametrize('missing', [True, False])
def test_missing_or_corrupt_historical_data_never_falls_back_to_current(tmp_path, missing):
    from tft_data.models import DataError
    from tft_review import ReplayProducer
    sessions, data_store, data, _ = logged_game(tmp_path)
    snapshot_path = data_store.root / data.snapshot_id / 'snapshot.json'
    if missing: snapshot_path.unlink()
    else: snapshot_path.write_text('{}')
    with pytest.raises(DataError):
        ReplayProducer(sessions, data_store, repository=ROOT).produce('901')


def positioning_hook(context):
    from tft_engine import Advice, ScoredOption
    return (Advice('positioning', 'Keep backline together', 'information', .8,
        'trait_sighting', decision_id='position-fixture', option_id='layout-a',
        options=(ScoredOption('layout-a', 'position', {'positions': [0]}, reason='non_costed'),),
        payload={'history_snapshots': [row.snapshot_id for row in context.history.snapshots]}),)


def test_final_hooks_and_identical_polls_retain_causal_context_without_costing_positioning(tmp_path):
    from tft_engine.registry import DomainHook
    from tft_review import ReplayProducer
    sessions, data_store, data, _ = logged_game(tmp_path, finish=False)
    sessions.append_event('snapshot', log_snapshot(data, at=NOW+timedelta(seconds=.25),
        snapshot_id='poll-2'), timestamp=(NOW+timedelta(seconds=.25)).isoformat())
    batch = ReplayProducer(sessions, data_store, repository=ROOT,
        hooks=(DomainHook('positioning', (), advice=positioning_hook),), hook_version='fixture-v1').produce('901')
    assert [row.snapshot['snapshot_id'] for row in batch.contexts] == ['original', 'poll-2']
    records = [row for row in batch.records if row.decision == 'positioning']
    assert len(records) == 2
    assert [row.log_seq for row in records] == [1, 2]
    assert records[0].options[0]['expected_placement'] is None
    assert records[0].expected_placement is None
    assert records[0].unavailable['expected_placement'] == 'domain_does_not_value_placement'
    assert records[0].cost is None
    assert records[1].advice['payload']['history_snapshots'] == ('original',)
    assert records[1].engine_identity['hook_version'] == 'fixture-v1'


@pytest.fixture
def clean_checkout(tmp_path):
    """Temporary detached worktree of this repository, with the running sources."""
    checkout = tmp_path / 'checkout'
    def git(*args):
        return subprocess.run(['git', '-C', str(ROOT), *args], check=True, capture_output=True, text=True)
    git('worktree', 'add', '--detach', str(checkout), 'HEAD')
    try:
        for package in ('data', 'engine', 'review'):
            source = ROOT / 'core' / 'packages' / package / 'src'
            shutil.copytree(source, checkout / source.relative_to(ROOT), dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        subprocess.run(['git', '-C', str(checkout), 'add', 'core/packages'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(checkout), 'commit', '--allow-empty', '-m', 'Replay fixture sources'],
            check=True, capture_output=True)
        yield checkout
    finally:
        git('worktree', 'remove', '--force', str(checkout))


def test_clean_finished_replay_reuses_exact_cache_without_recursive_provenance(tmp_path, clean_checkout):
    from tft_review import ReplayProducer
    sessions, data_store, _, _ = logged_game(tmp_path)
    producer = ReplayProducer(sessions, data_store, repository=clean_checkout)
    original = producer.produce('901')
    assert original.identity['dirty'] is False
    events = sessions.read_events('901')
    assert sum(row['kind'] == 'replay_cache' for row in events) == 1
    assert not any(row['kind'] == 'replay_cache' for row in original.observations)
    reused = producer.produce('901')
    assert reused == original
    assert sessions.read_events('901') == events
    assert original.identity['log_hash'] == reused.identity['log_hash']


@pytest.mark.parametrize('untracked', [False, True])
def test_relevant_tracked_and_untracked_changes_bypass_clean_cache(tmp_path, clean_checkout, untracked):
    from tft_review import ReplayProducer
    sessions, data_store, _, _ = logged_game(tmp_path)
    producer = ReplayProducer(sessions, data_store, repository=clean_checkout)
    original = producer.produce('901')
    path = clean_checkout / 'core/packages/engine/src/tft_engine' / ('new_rule.py' if untracked else 'registry.py')
    path.write_text(path.read_text()+'\n# changed rule\n' if path.exists() else '# unpublished rule\n')
    changed = producer.produce('901')
    assert changed.identity['dirty'] is True
    assert changed.identity != original.identity
    assert sum(row['kind'] == 'replay_cache' for row in sessions.read_events('901')) == 1


def test_active_game_and_hook_version_changes_do_not_reuse_finished_cache(tmp_path, clean_checkout):
    from tft_review import ReplayProducer
    sessions, data_store, _, _ = logged_game(tmp_path, finish=False)
    producer = ReplayProducer(sessions, data_store, repository=clean_checkout)
    active = producer.produce('901')
    assert active.identity['finished'] is False
    assert not any(row['kind'] == 'replay_cache' for row in sessions.read_events('901'))
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    finished = producer.produce('901')
    assert finished.identity['finished'] is True
    assert active.identity['log_hash'] != finished.identity['log_hash']
    changed_hook = ReplayProducer(sessions, data_store, repository=clean_checkout, hook_version='new-registry').produce('901')
    assert changed_hook.identity['hook_version'] == 'new-registry'
    assert sum(row['kind'] == 'replay_cache' for row in sessions.read_events('901')) == 2


def test_review_facade_locks_records_tags_and_media_but_keeps_raw_training_media_available(tmp_path):
    from PIL import Image
    from tft_review import ReplayProducer, ReviewAccess
    sessions, data_store, _, _ = logged_game(tmp_path, finish=False)
    media = sessions.write_keyframe(Image.new('RGB', (3, 3), 'red'), reason='offer', timestamp=NOW.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    batch = ReplayProducer(sessions, data_store, repository=ROOT).produce('901')
    access = ReviewAccess(sessions)
    access.publish(batch)
    assert batch.records  # Internal harness can consume locked evidence.
    assert sessions.read_media('901', media)  # Raw reader/training is not a review route.
    for operation in (lambda: access.read('901'), lambda: access.read_media('901', media),
        lambda: access.tag('901', batch.records[0].decision_id, 'agree'),
        lambda: sessions.set_review_tag('901', batch.records[0].decision_id, 'agree')):
        with pytest.raises(PermissionError, match='locked'):
            operation()
    sessions.start_run(baseline_fixture(sessions=sessions), set_id='18')
    assert access.read_batch('901') == batch
    assert access.read_media('901', media) == sessions.read_media('901', media)
    decision_id = batch.records[0].decision_id
    with pytest.raises(ValueError, match='decision'):
        access.tag('901', 'unknown-decision', 'agree')
    with pytest.raises(ValueError, match='tag'):
        access.tag('901', decision_id, 'invalid')
    access.tag('901', decision_id, 'disagree')
    access.publish(batch)
    assert access.read('901')['tags'] == {decision_id: 'disagree'}
    with pytest.raises(ValueError, match='logged media'):
        access.read_media('901', 'media/unlogged.webp')


@pytest.mark.parametrize('change', ['wrong_game', 'unknown_context', 'bad_version', 'nonfinite_cost'])
def test_json_replay_contracts_reject_inconsistent_or_nonfinite_records(tmp_path, change):
    from tft_review import ReplayBatch, ReplayProducer
    sessions, data_store, _, _ = logged_game(tmp_path)
    encoded = ReplayProducer(sessions, data_store, repository=ROOT).produce('901').to_dict()
    if change == 'wrong_game': encoded['records'][0]['game_id'] = '902'
    elif change == 'unknown_context': encoded['records'][0]['log_seq'] = 100
    elif change == 'bad_version': encoded['v'] = True
    elif change == 'nonfinite_cost': encoded['records'][0]['cost'] = float('nan')
    with pytest.raises(ValueError, match='[Rr]eplay|JSON'):
        ReplayBatch.from_dict(encoded)


def test_changed_log_and_engine_commit_invalidate_cache_and_corrupt_cache_fails_visibly(tmp_path, clean_checkout):
    from tft_review import ReplayProducer
    sessions, data_store, _, _ = logged_game(tmp_path)
    producer = ReplayProducer(sessions, data_store, repository=clean_checkout)
    original = producer.produce('901')
    events = sessions.read_events('901')
    events[1]['payload']['fields']['hp']['value'] = 17
    sessions.log_path('901').write_text(''.join(json.dumps(row)+'\n' for row in events))
    changed = producer.produce('901')
    assert changed.identity['log_hash'] != original.identity['log_hash']
    assert changed.contexts[0].snapshot['fields']['hp']['value'] == 17
    subprocess.run(['git', '-C', str(clean_checkout), 'commit', '--allow-empty', '-m', 'New Engine fixture revision'],
        check=True, capture_output=True)
    revised = producer.produce('901')
    assert revised.identity['commit'] != changed.identity['commit']
    caches = [row for row in sessions.read_events('901') if row['kind'] == 'replay_cache']
    assert len(caches) == 3
    path = sessions.root / caches[-1]['payload']['path']
    encoded = json.loads(path.read_text())
    encoded['records'][0]['records'][0]['advice']['action'] = 'unchecked cached advice'
    path.write_text(json.dumps(encoded))
    with pytest.raises(ValueError, match='[Cc]ache'):
        producer.produce('901')


def changing_source_hook(context):
    path = context.snapshot.field('write_source')
    if path:
        Path(path).write_text('# source changed during replay\n')
    return positioning_hook(context)


def test_source_changes_during_actual_hook_evaluation_cannot_publish_cache(tmp_path, clean_checkout):
    from tft_engine.registry import DomainHook
    from tft_review import ReplayProducer
    sessions, data_store, data, _ = logged_game(tmp_path, finish=False)
    destination = clean_checkout / 'core/packages/engine/src/tft_engine/new_during_replay.py'
    sessions.append_event('snapshot', log_snapshot(data, snapshot_id='mutating',
        write_source=str(destination)), timestamp=NOW.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    with pytest.raises(ValueError, match='inputs changed'):
        ReplayProducer(sessions, data_store, repository=clean_checkout,
            hooks=(DomainHook('positioning', (), advice=changing_source_hook),)).produce('901')
    assert not any(row['kind'] == 'replay_cache' for row in sessions.read_events('901'))


def test_recovered_opening_gap_with_unknown_start_retains_only_confirmed_post_gap_history(tmp_path):
    from tft_review import ReplayProducer
    data_store, data = historical_data(tmp_path)
    sessions = SessionStore(tmp_path / 'logs', tmp_path / 'config', live_installed=True)
    path = sessions.log_path('901')
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"v":1,"seq":0')
    sessions.start_game('901', data_snapshot_id=data.snapshot_id, timestamp=NOW.isoformat())
    sessions.append_event('snapshot', log_snapshot(data, at=NOW+timedelta(seconds=1)),
        timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    batch = ReplayProducer(sessions, data_store, repository=ROOT).produce('901')
    assert batch.observations[1]['payload']['start'] is None
    assert batch.contexts[0].evaluation is not None
    assert batch.history_for(batch.contexts[0]).snapshots == ()


def test_later_backdated_gap_cannot_change_an_earlier_engine_information_prefix(tmp_path):
    from tft_review import ReplayProducer
    sessions, data_store, data, _ = logged_game(tmp_path, finish=False)
    sessions.append_event('snapshot', log_snapshot(data, at=NOW+timedelta(seconds=1),
        snapshot_id='before-gap-annotation'), timestamp=(NOW+timedelta(seconds=1)).isoformat())
    producer = ReplayProducer(sessions, data_store, repository=ROOT)
    before = producer.produce('901')
    sessions.append_event('capture_gap', {'start': NOW.isoformat(),
        'end': (NOW+timedelta(seconds=.5)).isoformat(), 'reason': 'late_crash_annotation'},
        timestamp=(NOW+timedelta(seconds=2)).isoformat())
    after = producer.produce('901')
    assert after.contexts[1].evaluation == before.contexts[1].evaluation
    assert [row.snapshot_id for row in after.history_for(after.contexts[1]).snapshots] == ['original']
    # A retrospective validity annotation can exclude a point without becoming
    # information available to that point's Engine evaluation.
    assert after.contexts[0].unavailable == ('capture_gap',)
    assert after.contexts[0].validity_annotations[0]['log_seq'] == 3
    assert after.contexts[0].validity_annotations[0]['retrospective'] is True


def test_review_publication_rejects_a_batch_from_changed_log_evidence(tmp_path):
    from tft_review import ReplayProducer, ReviewAccess
    sessions, data_store, _, _ = logged_game(tmp_path)
    batch = ReplayProducer(sessions, data_store, repository=ROOT).produce('901')
    events = sessions.read_events('901')
    events[1]['payload']['fields']['hp']['value'] = 21
    sessions.log_path('901').write_text(''.join(json.dumps(row)+'\n' for row in events))
    with pytest.raises(ValueError, match='changed'):
        ReviewAccess(sessions).publish(batch)
