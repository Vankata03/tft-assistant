"""Baseline qualification through external API responses and the public run seam."""
from datetime import datetime, timedelta, timezone

import pytest

from tft_core.storage import SessionStore

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


def external_matches(count=55, *, at=NOW):
    return [{'metadata': {'match_id': f'EUN1_{10000+i}'},
        'info': {'queue_id': 1100, 'tft_set_number': 18,
            'game_datetime': int((at-timedelta(days=i+1)).timestamp()*1000), 'game_length': 1000,
            'participants': [{'puuid': 'fixture-owner' if place == 1 else f'other-{place}',
                'placement': place, 'units': [], 'traits': []} for place in range(1, 9)]}}
        for i in range(count)]


def baseline_fixture(*, sessions=None, at=NOW):
    from tft_harness import qualify_baseline
    at = datetime.fromisoformat(at) if isinstance(at, str) else at
    return qualify_baseline(external_matches(at=at), owner_puuid='fixture-owner', set_number=18,
        rank=[{'queueType': 'RANKED_TFT', 'tier': 'PLATINUM', 'rank': 'III', 'leaguePoints': 59}],
        logged_games=sessions.list_games() if sessions else (), refreshed_at=at.isoformat())


def test_public_start_run_rejects_shallow_manifest_and_freezes_exact_latest_eligible_fifty(tmp_path):
    from tft_harness import qualify_baseline

    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    with pytest.raises(ValueError, match='qualified'):
        sessions.start_run({'game_count': 50, 'average_placement': 4.62, 'rank': 'P3'}, set_id='18')
    # Highest Baseline reached remains excluded, even after a Silent downgrade.
    sessions.set_mode('baseline')
    sessions.start_game('10000', set_id='18')
    sessions.set_mode('silent')
    sessions.end_game(placement=1)
    raw = external_matches()
    raw[1]['info']['queue_id'] = 1090
    raw[2]['info']['tft_set_number'] = 17
    baseline = qualify_baseline(raw, owner_puuid='fixture-owner', set_number=18,
        rank=[{'queueType': 'RANKED_TFT', 'tier': 'PLATINUM', 'rank': 'III', 'leaguePoints': 59}],
        logged_games=sessions.list_games(), refreshed_at=NOW.isoformat())
    assert baseline['game_count'] == 50 and baseline['average_placement'] == 1
    assert [row['metadata']['match_id'] for row in baseline['matches']][:2] == ['EUN1_10003', 'EUN1_10004']
    assert baseline['matches'][-1]['metadata']['match_id'] == 'EUN1_10052'
    assert baseline['excluded'] == {'coached': 1, 'wrong_queue': 1, 'wrong_set': 1}
    run = sessions.start_run(baseline, set_id='18', timestamp=NOW.isoformat())
    assert run['baseline'] == baseline
    assert sessions.run['baseline']['evidence_hash'] == baseline['evidence_hash']
    assert sessions.default_mode.value == 'live'


def test_run_boundary_rejects_changed_modes_tampered_sample_and_future_refresh(tmp_path):
    from copy import deepcopy

    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    baseline = baseline_fixture(sessions=sessions)
    corrupt = deepcopy(baseline)
    corrupt['average_placement'] = 4.62
    with pytest.raises(ValueError, match='evidence'):
        sessions.start_run(corrupt, set_id='18', timestamp=NOW.isoformat())
    with pytest.raises(ValueError, match='refresh'):
        sessions.start_run(baseline, set_id='18', timestamp=(NOW-timedelta(days=1)).isoformat())
    sessions.set_mode('live')
    sessions.start_game('10000', set_id='18')
    sessions.end_game(placement=1)
    with pytest.raises(ValueError, match='eligibility'):
        sessions.start_run(baseline, set_id='18', timestamp=NOW.isoformat())
    assert sessions.run is None


def test_an_independent_store_cannot_start_run_over_another_cores_unfinished_log(tmp_path):
    core = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    launcher = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    baseline = baseline_fixture(sessions=launcher)
    core.start_game('901', set_id='18')
    before = core.read_events('901')
    with pytest.raises(ValueError, match='during a game|unfinished'):
        launcher.start_run(baseline, set_id='18', timestamp=NOW.isoformat())
    assert core.run is None and launcher.run is None
    assert core.read_events('901') == before
    assert core.default_mode.value == 'silent'
    core.end_game(placement=3)
    assert launcher.start_run(baseline, set_id='18', timestamp=NOW.isoformat())['baseline'] == baseline


def test_running_core_uses_cli_started_run_default_for_its_next_game(tmp_path):
    core = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    launcher = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    launcher.start_run(baseline_fixture(sessions=launcher), set_id='18', timestamp=NOW.isoformat())
    core.start_game('901', set_id='18')
    assert core.mode.value == 'live'
    assert core.read_events('901')[0]['payload']['mode'] == 'live'
    core.end_game(placement=3)
    # An explicit Silent selection after the run starts remains authoritative.
    launcher.set_mode('silent')
    core.start_game('902', set_id='18')
    assert core.read_events('902')[0]['payload']['mode'] == 'silent'


def test_separate_cli_process_rejects_running_cores_log_without_changing_run(tmp_path):
    import subprocess
    import sys

    core = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    core.start_game('901', set_id='18')
    original = core.read_events('901')
    script = '''
import sys
from pathlib import Path
from tft_core.storage import SessionStore
from tests.test_harness_baseline import baseline_fixture, NOW
store = SessionStore(Path(sys.argv[1]), Path(sys.argv[2]), live_installed=True)
try:
    store.start_run(baseline_fixture(sessions=store), set_id='18', timestamp=NOW.isoformat())
except ValueError as error:
    print(error)
    sys.exit(2)
'''
    result = subprocess.run([sys.executable, '-c', script, str(core.root), str(core.config_root)],
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 2, result.stderr
    assert 'unfinished' in result.stdout
    assert core.run is None
    assert core.read_events('901') == original
