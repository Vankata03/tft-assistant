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
