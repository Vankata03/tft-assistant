"""Owner start-run workflow through the public CLI and real durable store."""
import json

from tests.test_harness_baseline import external_matches
from tft_core.storage import SessionStore


class OwnerAPI:
    """Synthetic external Riot boundary; never reads credentials or the network."""
    def account(self, game_name, tag_line):
        return {'puuid': 'fixture-owner'}

    def rank(self):
        return [{'queueType': 'RANKED_TFT', 'tier': 'PLATINUM', 'rank': 'III', 'leaguePoints': 59}]

    def own_matches(self, *, set_number, max_matches):
        return external_matches()


def arguments():
    return ['start-run', '--game-name', 'Fixture Owner', '--tag-line', 'EU', '--set', '18']


def test_cli_refreshes_and_freezes_latest_fifty_and_unlocks_silent_reviews(tmp_path, monkeypatch, capsys):
    from tft_core.harness_cli import main

    root, config = tmp_path/'logs', tmp_path/'config'
    monkeypatch.setenv('TFT_ASSISTANT_DATA_ROOT', str(root))
    monkeypatch.setenv('TFT_ASSISTANT_CONFIG_ROOT', str(config))
    sessions = SessionStore(root, config)
    sessions.start_game('10000', set_id='18')
    sessions.end_game(placement=1)
    original = sessions.read_events('10000')
    assert sessions.list_games()[0]['review_locked']
    assert main(arguments(), riot_client=OwnerAPI()) == 0
    reopened = SessionStore(root, config)
    assert reopened.run['set_id'] == '18'
    assert reopened.run['baseline']['game_count'] == 50
    assert reopened.run['baseline']['average_placement'] == 1
    assert reopened.run['baseline']['matches'][-1]['metadata']['match_id'] == 'EUN1_10049'
    assert reopened.default_mode.value == 'live'
    assert reopened.list_games()[0]['review_locked'] is False
    assert reopened.read_events('10000') == original
    cached = json.loads((config/'baseline-matches.json').read_text())
    assert cached['owner_puuid'] == 'fixture-owner'
    assert len(cached['matches']) == 55
    output = capsys.readouterr().out
    assert '50' in output and 'PLATINUM III' in output
    assert 'fixture-owner' not in output and '10000' not in output


def test_failed_refresh_leaves_frozen_state_and_last_good_cache_unchanged(tmp_path, monkeypatch, capsys):
    from tft_core.harness_cli import main

    class TooFew(OwnerAPI):
        def own_matches(self, *, set_number, max_matches):
            return external_matches(49)

    root, config = tmp_path/'logs', tmp_path/'config'
    monkeypatch.setenv('TFT_ASSISTANT_DATA_ROOT', str(root))
    monkeypatch.setenv('TFT_ASSISTANT_CONFIG_ROOT', str(config))
    sessions = SessionStore(root, config)
    sessions.start_game('900', set_id='18')
    sessions.end_game(placement=3)
    original = sessions.read_events('900')
    cache = config/'baseline-matches.json'
    cache.write_text('{"previous": "last-good"}')
    assert main(arguments(), riot_client=TooFew()) == 2
    assert sessions.run is None and sessions.default_mode.value == 'silent'
    assert sessions.read_events('900') == original
    assert cache.read_text() == '{"previous": "last-good"}'
    assert 'at least 50' in capsys.readouterr().out


def test_repeated_start_does_not_fetch_or_change_an_existing_run(tmp_path, monkeypatch, capsys):
    from tft_core.harness_cli import main

    class Offline(OwnerAPI):
        def account(self, game_name, tag_line):
            raise AssertionError('An existing run must be rejected before API access')

    root, config = tmp_path/'logs', tmp_path/'config'
    monkeypatch.setenv('TFT_ASSISTANT_DATA_ROOT', str(root))
    monkeypatch.setenv('TFT_ASSISTANT_CONFIG_ROOT', str(config))
    assert main(arguments(), riot_client=OwnerAPI()) == 0
    frozen = (config/'run.json').read_bytes()
    cached = (config/'baseline-matches.json').read_bytes()
    assert main(arguments(), riot_client=Offline()) == 2
    assert (config/'run.json').read_bytes() == frozen
    assert (config/'baseline-matches.json').read_bytes() == cached
    assert 'already started' in capsys.readouterr().out


def test_owner_api_failure_is_actionable_without_exposing_private_response(tmp_path, monkeypatch, capsys):
    from tft_core.harness_cli import main
    from tft_data.models import DataError

    class ExpiredKey(OwnerAPI):
        def account(self, game_name, tag_line):
            raise DataError('Riot authentication failed; refresh the local API key or check approval')

    monkeypatch.setenv('TFT_ASSISTANT_DATA_ROOT', str(tmp_path/'logs'))
    monkeypatch.setenv('TFT_ASSISTANT_CONFIG_ROOT', str(tmp_path/'config'))
    assert main(arguments(), riot_client=ExpiredKey()) == 2
    assert not (tmp_path/'config/run.json').exists()
    assert not (tmp_path/'config/baseline-matches.json').exists()
    assert 'refresh the local API key' in capsys.readouterr().out


def test_git_private_roots_are_rejected_before_external_api_access(tmp_path, monkeypatch, capsys):
    from tft_core.harness_cli import main

    class NoAccess(OwnerAPI):
        def account(self, game_name, tag_line):
            raise AssertionError('Private roots must be checked before API access')

    repository = tmp_path/'repository'
    repository.mkdir()
    (repository/'.git').write_text('gitdir: external-worktree-metadata')
    monkeypatch.setenv('TFT_ASSISTANT_DATA_ROOT', str(tmp_path/'logs'))
    monkeypatch.setenv('TFT_ASSISTANT_CONFIG_ROOT', str(repository/'config'))
    assert main(arguments(), riot_client=NoAccess()) == 2
    assert not (repository/'config').exists()
    assert 'outside Git repositories' in capsys.readouterr().out
