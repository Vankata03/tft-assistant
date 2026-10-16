"""Post-game truth through public capture, outcome and session boundaries."""
import asyncio
from copy import deepcopy

import httpx
import pytest

from tests.test_harness_baseline import baseline_fixture
from tft_capture.lcu import LcuConnection, LcuCredentials
from tft_core.storage import SessionStore


def test_real_queue_metadata_stays_explicit_and_only_ranked_games_number_the_run(tmp_path):
    async def capture_queue():
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
            'gameData': {'gameId': 901, 'gameMode': 'TFT', 'queue': {'id': 1100}}}))
        async with LcuConnection(LcuCredentials(1, 'fixture-secret'), transport=transport) as client:
            return await client.get_game_metadata()

    assert asyncio.run(capture_queue()) == ('901', 'TFT', 1100)
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.start_run(baseline_fixture(at='2026-10-06T12:00:00+00:00'), set_id='18',
        timestamp='2026-10-06T12:00:00+00:00')
    for game_id, queue in [('901', None), ('902', 1090), ('903', 1100)]:
        sessions.start_game(game_id, set_id='18', queue_id=queue, timestamp='2026-10-07T12:00:00+00:00')
        sessions.end_game()
    games = {row['game_id']: row for row in sessions.list_games()}
    assert [(games[key]['run_number'], games[key]['queue_id']) for key in ('901', '902', '903')] == [
        (None, None), (None, 1090), (1, 1100)]
    assert sessions.read_events('903')[0]['payload']['queue_id'] == 1100


def match_fixture(game_id='901'):
    return {'metadata': {'match_id': f'EUN1_{game_id}'}, 'info': {
        'queue_id': 1100, 'tft_set_number': 18, 'game_datetime': 1791500000000,
        'participants': [{'puuid': 'owner' if place == 4 else f'player-{place}',
            'placement': place, 'last_round': 20 + 8 - place, 'time_eliminated': 900 + 10*(8-place),
            'units': [{'character_id': 'TFT18_Test', 'tier': 2, 'items': [11, 22]}],
            'traits': [{'name': 'TFT18_TestTrait', 'num_units': 2, 'style': 1,
                'tier_current': 1, 'tier_total': 3}]} for place in range(1, 9)]}}


def finished_session(tmp_path):
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.start_game('901', set_id='18', queue_id=1100)
    sessions.end_game()
    return sessions


def test_late_match_outcome_survives_index_rebuild_without_editing_log_or_unlocking_review(tmp_path):
    sessions = finished_session(tmp_path)
    original = sessions.log_path('901').read_bytes()
    result = sessions.record_outcome('901', match_fixture(), owner_puuid='owner')
    assert result['placement'] == 4
    assert result['participants'][0]['units'] == [{'character_id': 'TFT18_Test', 'tier': 2, 'items': [11, 22]}]
    assert result['elimination_order'] == ['player-8', 'player-7', 'player-6', 'player-5', 'owner', 'player-3', 'player-2', 'player-1']
    assert result['elimination_order_source'] == 'final_placement'
    assert sessions.log_path('901').read_bytes() == original
    recovered = SessionStore(sessions.root, sessions.config_root, live_installed=True)
    assert recovered.read_outcome('901') == result
    game = recovered.list_games()[0]
    assert (game['placement'], game['review_locked']) == (4, True)
    with pytest.raises(PermissionError):
        recovered.read_review('901')


@pytest.mark.parametrize('mutation', ['match', 'owner', 'set', 'queue', 'placement', 'unit', 'traits', 'nan'])
def test_bad_external_truth_is_rejected_without_replacing_last_good_outcome(tmp_path, mutation):
    sessions = finished_session(tmp_path)
    good = sessions.record_outcome('901', match_fixture(), owner_puuid='owner')
    bad = deepcopy(match_fixture())
    if mutation == 'match': bad['metadata']['match_id'] = 'EUN1_999'
    if mutation == 'owner': bad['info']['participants'][3]['puuid'] = 'absent-owner'
    if mutation == 'set': bad['info']['tft_set_number'] = 19
    if mutation == 'queue': bad['info']['queue_id'] = 1090
    if mutation == 'placement': bad['info']['participants'][0]['placement'] = 4
    if mutation == 'unit': bad['info']['participants'][0]['units'][0]['tier'] = True
    if mutation == 'traits': del bad['info']['participants'][0]['traits']
    if mutation == 'nan': bad['info']['participants'][0]['time_eliminated'] = float('nan')
    with pytest.raises(ValueError):
        sessions.record_outcome('901', bad, owner_puuid='owner')
    assert sessions.read_outcome('901') == good


def test_collector_paces_owner_scoped_http_and_recovers_a_delayed_match(tmp_path):
    import json
    from tft_core.outcomes import OutcomeCollector
    from tft_data.riot import HTTPResponse, RiotClient

    sessions = finished_session(tmp_path)
    (sessions.config_root/'outcome-source.json').write_text(json.dumps({
        'owner_puuid': 'owner', 'platform': 'eun1', 'region': 'europe'}))
    key = sessions.config_root/'riot-api-key'
    key.write_text('fixture-key')
    urls, sleeps = [], []

    def external_http(url, headers):
        assert headers['X-Riot-Token'] == 'fixture-key'
        urls.append(url)
        if '/ids?' in url:
            return HTTPResponse(200, {}, [] if len(urls) == 1 else ['EUN1_901'])
        return HTTPResponse(200, {}, match_fixture())

    client = RiotClient(key_path=key, transport=external_http, sleep=sleeps.append)
    collector = OutcomeCollector(sessions, client=client)
    assert collector.collect('901')['state'] == 'pending'
    assert sessions.list_games()[0]['placement'] is None
    assert collector.collect('901')['state'] == 'confirmed'
    assert sessions.list_games()[0]['placement'] == 4
    assert sleeps == [1.25]
    assert urls[-1].endswith('/tft/match/v1/matches/EUN1_901')
    assert 'fixture-key' not in collector.status('901').__str__()
    assert collector.collect('901')['state'] == 'confirmed'
    assert len(urls) == 3


@pytest.mark.parametrize('delayed', [False, True, 'never_available'])
def test_actual_review_job_collects_outcome_before_historical_evaluation(tmp_path, delayed):
    import json
    from tests.test_replay_contracts import ROOT, NOW, historical_data, log_snapshot
    from tft_core.outcomes import OutcomeCollector
    from tft_core.review_jobs import ReviewJobs
    from tft_data.riot import HTTPResponse, RiotClient
    from tft_review import ReviewService

    async def scenario():
        store, data = historical_data(tmp_path)
        sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
        sessions.set_mode('baseline')
        sessions.start_game('901', set_id='18', queue_id=1100, patch=data.patch,
            data_snapshot_id=data.snapshot_id, timestamp=NOW.isoformat())
        sessions.append_event('snapshot', log_snapshot(data), timestamp=NOW.isoformat())
        sessions.end_game()
        (sessions.config_root/'outcome-source.json').write_text(json.dumps({
            'owner_puuid': 'owner', 'platform': 'eun1', 'region': 'europe'}))
        key = sessions.config_root/'riot-api-key'
        key.write_text('fixture-key')
        requests = []
        def external_http(url, headers):
            requests.append(url)
            absent = delayed == 'never_available' or (delayed and len(requests) == 1)
            return HTTPResponse(200, {}, ([] if absent else ['EUN1_901']) if '/ids?' in url else match_fixture())
        client = RiotClient(key_path=key, sleep=lambda seconds: None, transport=external_http)
        jobs = ReviewJobs(sessions, store, ReviewService(sessions, store, repository=ROOT), ROOT,
            outcome_collector=OutcomeCollector(sessions, client=client), outcome_retry_seconds=.01)
        jobs.start()
        try:
            jobs.enqueue('901')
            for _ in range(600):
                records = jobs.jobs()
                collected = jobs.outcomes.status('901')
                available = sessions.read_outcome('901') is not None
                exhausted = collected and collected['attempts'] == 10
                if records and records[-1]['state'] in {'completed', 'failed', 'unavailable'} and (available or exhausted):
                    break
                await asyncio.sleep(.01)
            assert records[-1]['state'] == 'completed', records
            if delayed == 'never_available':
                assert sessions.read_outcome('901') is None
                assert jobs.outcomes.status('901')['state'] == 'pending'
                assert len(requests) == 10
                await asyncio.sleep(.05)
                assert len(requests) == 10
                assert sessions.read_review('901') is not None
            else:
                assert sessions.read_outcome('901')['placement'] == 4
        finally:
            assert await jobs.shutdown()
    asyncio.run(scenario())


def test_actual_app_persists_ranked_queue_from_the_gameflow_watcher(tmp_path):
    from tests.test_runtime_app import ScriptedClient, core

    class QueueClient(ScriptedClient):
        async def get_game_metadata(self):
            return self.game_id, self.mode, 1100

    async def scenario():
        client = QueueClient()
        async with core(tmp_path, client, live_installed=False) as (_, sessions, _, _):
            client.phase, client.game_id, client.mode = 'InProgress', '901', 'TFT'
            for _ in range(300):
                if sessions.read_events('901'):
                    break
                await asyncio.sleep(.01)
            assert sessions.read_events('901')[0]['payload']['queue_id'] == 1100
            client.phase = 'EndOfGame'
            for _ in range(300):
                games = sessions.list_games()
                if games and games[0]['finished']:
                    break
                await asyncio.sleep(.01)
            assert (games[0]['finished'], games[0]['queue_id'], games[0]['placement']) == (True, 1100, None)
    asyncio.run(scenario())


def test_capture_runtime_keeps_original_queue_through_reconnection_and_finalization(tmp_path):
    from tests.test_runtime import fixture_runtime, wait_snapshot
    from tft_capture.lcu import GameflowUpdate

    async def scenario():
        runtime, sessions, _, _ = fixture_runtime(tmp_path)
        try:
            await runtime.update(GameflowUpdate(True, 'InProgress', '123', 'TFT', queue_id=1100))
            await wait_snapshot(runtime)
            await runtime.update(GameflowUpdate(True, 'Reconnect', '123', 'TFT', queue_id=1090))
            await runtime.update(GameflowUpdate(True, 'EndOfGame', '123', 'TFT', queue_id=1090))
            assert sessions.read_events('123')[0]['payload']['queue_id'] == 1100
            assert runtime.completed_game['queue_id'] == 1100
        finally:
            await runtime.shutdown()
    asyncio.run(scenario())


def test_confirmed_outcome_conflicts_and_corrupted_artifacts_fail_visibly(tmp_path):
    import json
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.start_game('901', set_id='18', queue_id=1100)
    sessions.end_game(placement=5)
    with pytest.raises(ValueError, match='conflicts'):
        sessions.record_outcome('901', match_fixture(), owner_puuid='owner')
    assert sessions.read_outcome('901') is None
    assert sessions.list_games()[0]['placement'] == 5
    other = finished_session(tmp_path/'other')
    other.record_outcome('901', match_fixture(), owner_puuid='owner')
    path = other.root/'outcomes'/'901.json'
    altered = json.loads(path.read_text())
    altered['participants'][0]['units'][0]['tier'] = 3
    path.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match='evidence changed'):
        other.read_outcome('901')


def test_refit_cannot_cross_a_detached_unfinished_ranked_game_after_the_tenth_completion(tmp_path):
    from tests.test_replay_contracts import ROOT
    from tft_data import DataStore
    from tft_harness import EvaluationHarness

    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.start_run(baseline_fixture(at='2026-10-06T12:00:00+00:00'), set_id='18',
        timestamp='2026-10-06T12:00:00+00:00')
    for identity in range(901, 911):
        sessions.start_game(str(identity), set_id='18', queue_id=1100, timestamp='2026-10-07T12:00:00+00:00')
        sessions.end_game(placement=4)
    sessions.start_game('911', set_id='18', queue_id=1100, timestamp='2026-10-07T12:00:00+00:00')
    sessions.detach_game('911', reason='positive_different_game_identity')
    harness = EvaluationHarness(sessions, DataStore(tmp_path/'data'), repository=ROOT)
    with pytest.raises(ValueError, match='completed ten-game block'):
        harness.fit({'fight_scale': [1]})


def test_automatic_collector_retains_server_rate_limits_across_finished_games(tmp_path):
    import json
    from tft_core.outcomes import OutcomeCollector
    from tft_data.riot import HTTPResponse, RiotClient

    sessions = finished_session(tmp_path)
    sessions.start_game('902', set_id='18', queue_id=1100)
    sessions.end_game()
    (sessions.config_root/'riot-api-key').write_text('fixture-key')
    (sessions.config_root/'outcome-source.json').write_text(json.dumps({
        'owner_puuid': 'owner', 'platform': 'eun1', 'region': 'europe'}))
    elapsed, delays = [0.0], []
    def sleep(seconds):
        delays.append(seconds)
        elapsed[0] += seconds
    def external_http(url, headers):
        body = ['EUN1_901', 'EUN1_902'] if '/ids?' in url else match_fixture(url.rsplit('_', 1)[1])
        return HTTPResponse(200, {'X-App-Rate-Limit': '2:120'}, body)
    def client_factory(**options):
        return RiotClient(**options, transport=external_http, clock=lambda: elapsed[0], sleep=sleep)
    collector = OutcomeCollector(sessions, client_factory=client_factory)
    assert collector.collect('901')['state'] == 'confirmed'
    assert collector.collect('902')['state'] == 'confirmed'
    assert any(delay > 100 for delay in delays)
