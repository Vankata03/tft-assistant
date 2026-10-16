"""Owner start-run workflow through the public CLI and real durable store."""
import os
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


def test_eval_cli_reads_committed_tunables_and_writes_private_aggregate_report(tmp_path, monkeypatch, capsys):
    from tests.test_harness import combat_logs
    from tests.test_harness_tunables_io import committed_repository
    from tft_core.harness_cli import main
    (tmp_path/'games').mkdir()
    (tmp_path/'accepted').mkdir()
    sessions, store = combat_logs(tmp_path/'games', results=('win','loss'))
    repository = committed_repository(tmp_path/'accepted')
    monkeypatch.setenv('TFT_ASSISTANT_DATA_ROOT', str(sessions.root))
    monkeypatch.setenv('TFT_ASSISTANT_CONFIG_ROOT', str(tmp_path/'games'/'config'))
    output = tmp_path/'reports'
    assert main(['eval', '--repository', str(repository), '--snapshots', str(store.root),
        '--output', str(output), '--bootstrap-draws', '20']) == 0
    report = next(output.glob('*.md')).read_text()
    if os.name == 'posix':
        assert next(output.glob('*.md')).stat().st_mode & 0o077 == 0
    assert 'Git blob' in report and 'Calibration' in report and 'Exclusions' in report
    assert '"901"' not in report and '"902"' not in report
    assert str(sessions.root) not in report
    assert 'historical effective tunables' not in report


def test_fit_cli_writes_unaccepted_toml_with_holdout_diagnostics(tmp_path, monkeypatch):
    import tomllib
    from tests.test_harness import combat_logs
    from tests.test_harness_tunables_io import committed_repository
    from tft_core.harness_cli import main
    (tmp_path/'games').mkdir()
    (tmp_path/'accepted').mkdir()
    sessions, store = combat_logs(tmp_path/'games', results=('win','win','loss','win','loss'))
    repository = committed_repository(tmp_path/'accepted')
    monkeypatch.setenv('TFT_ASSISTANT_DATA_ROOT', str(sessions.root))
    monkeypatch.setenv('TFT_ASSISTANT_CONFIG_ROOT', str(sessions.config_root))
    search = tmp_path/'search.json'
    search.write_text('{"fight_scale":[0.5,1,2]}')
    output = tmp_path/'reports'
    before = (repository/'data/18.2/tunables.toml').read_bytes()
    assert main(['fit', '--repository', str(repository), '--snapshots', str(store.root),
        '--output', str(output), '--search', str(search), '--bootstrap-draws', '20']) == 0
    candidate = tomllib.loads(next(output.glob('*.toml')).read_text())
    assert candidate['fields']['fight_scale']['family'] == '1'
    report = next(output.glob('*.md')).read_text()
    def section(title):
        return json.loads(report.split('## '+title+'\n\n```json\n')[1].split('\n```')[0])
    diagnostics = section('Fit diagnostics')
    assert 'gates' not in diagnostics
    partial = diagnostics['family1_only_gates']
    assert partial['scope'].startswith('family-1 search candidate before margins')
    assert partial['gates'] and set(partial['gates']) <= set(section('Gates'))
    assert (repository/'data/18.2/tunables.toml').read_bytes() == before


def test_priors_cli_uses_qualified_public_counts_and_preserves_source(tmp_path, monkeypatch):
    import tomllib
    import tomli_w
    from tests.test_harness import combat_logs
    from tests.test_harness_priors import evidence, cohort, binomial
    from tests.test_harness_tunables_io import committed_repository
    from tests.test_replay_contracts import NOW
    from tft_core.harness_cli import main
    (tmp_path/'games').mkdir()
    (tmp_path/'accepted').mkdir()
    sessions, store = combat_logs(tmp_path/'games', results=('win','loss'))
    for name in ('static.toml', 'tunables.toml'):
        path = tmp_path/'games/patch'/name
        document = tomllib.loads(path.read_text())
        document['patch'] = '18.2'
        path.write_text(tomli_w.dumps(document))
    assert store.refresh(tmp_path/'games/patch', now=NOW).snapshot.patch == '18.2'
    repository = committed_repository(tmp_path/'accepted')
    monkeypatch.setenv('TFT_ASSISTANT_DATA_ROOT', str(sessions.root))
    monkeypatch.setenv('TFT_ASSISTANT_CONFIG_ROOT', str(sessions.config_root))
    source = tmp_path/'public.json'
    source.write_text(json.dumps(evidence(cohort([binomial('unit','unit',600)], patch='18.2'))))
    output = tmp_path/'reports'
    assert main(['fit', '--priors', '--repository', str(repository), '--snapshots', str(store.root),
        '--output', str(output), '--prior-evidence', str(source), '--bootstrap-draws', '20']) == 0
    candidate = tomllib.loads(next(output.glob('*.toml')).read_text())
    fitted = candidate['fields']['cost_star_baseline']
    assert fitted['source'] == 'owner' and fitted['family'] == '3'
    assert 'Mixed-origin table' in fitted['citation']
    cells = candidate['harness_candidate']['provenance']['table_cells']['cost_star_baseline']
    assert cells['fitted_cells'] == [['1', '1']]
    assert ['3', '2'] in cells['carried_cells']
    assert cells['carried_source'] == 'owner'
    report = next(output.glob('*.md')).read_text()
    assert '"fitted_cells"' in report and '"carried_cells"' in report
    assert candidate['harness_candidate']['provenance']['cohorts'][0]['citation'].startswith('https://tactics.tools/')
    assert str(source) not in next(output.glob('*.toml')).read_text()


def test_cli_eval_actually_reports_widened_candidates(tmp_path, monkeypatch):
    from tests.test_harness import combat_logs
    from tests.test_harness_tunables_io import committed_repository
    from tft_core.harness_cli import main
    (tmp_path/'games').mkdir()
    (tmp_path/'accepted').mkdir()
    sessions,store = combat_logs(tmp_path/'games',results=('win','loss'))
    repository = committed_repository(tmp_path/'accepted')
    monkeypatch.setenv('TFT_ASSISTANT_DATA_ROOT',str(sessions.root))
    monkeypatch.setenv('TFT_ASSISTANT_CONFIG_ROOT',str(sessions.config_root))
    output=tmp_path/'reports'
    assert main(['eval','--repository',str(repository),'--snapshots',str(store.root),
        '--output',str(output),'--bootstrap-draws','20']) == 0
    assert 'widened_candidates' in next(output.glob('*.md')).read_text()


def test_report_code_identity_is_running_source_separate_from_accepted_checkout(tmp_path, monkeypatch):
    from tests.test_harness import combat_logs
    from tests.test_harness_tunables_io import committed_repository, git
    from tests.test_replay_contracts import ROOT
    from tft_core.harness_cli import main
    (tmp_path/'games').mkdir()
    (tmp_path/'accepted').mkdir()
    sessions,store = combat_logs(tmp_path/'games',results=('win','loss'))
    repository = committed_repository(tmp_path/'accepted')
    monkeypatch.setenv('TFT_ASSISTANT_DATA_ROOT',str(sessions.root))
    monkeypatch.setenv('TFT_ASSISTANT_CONFIG_ROOT',str(sessions.config_root))
    output=tmp_path/'reports'
    assert main(['eval','--repository',str(repository),'--snapshots',str(store.root),
        '--output',str(output),'--bootstrap-draws','20']) == 0
    assert git(ROOT,'rev-parse','HEAD') in next(output.glob('*.md')).read_text()


def test_dirty_runtime_cli_publishes_code_identity_separate_from_accepted_data(tmp_path):
    import subprocess
    import sys
    import tomllib
    from tests.test_harness import combat_logs
    from tests.test_harness_tunables_io import committed_repository, runtime_repository, git

    (tmp_path/'games').mkdir()
    (tmp_path/'accepted').mkdir()
    sessions, store = combat_logs(tmp_path/'games', results=('win', 'loss'))
    accepted = committed_repository(tmp_path/'accepted')
    runtime = runtime_repository(tmp_path)
    commit = git(runtime, 'rev-parse', 'HEAD')
    with (runtime/'core/packages/engine/src/tft_engine/planning.py').open('a') as output:
        output.write('\n# dirty runtime CLI fixture\n')
    (runtime/'core/packages/engine/src/tft_engine/untracked_fixture.py').write_text('# untracked runtime\n')
    search = tmp_path/'search.json'
    search.write_text('{"fight_scale":[0.5,1,2]}')
    output = tmp_path/'reports'
    env = dict(os.environ, TFT_ASSISTANT_DATA_ROOT=str(sessions.root),
        TFT_ASSISTANT_CONFIG_ROOT=str(sessions.config_root), PYTHONPATH=os.pathsep.join(map(str,
        [runtime/'core/src', *sorted((runtime/'core/packages').glob('*/src'))])))
    result = subprocess.run([sys.executable, '-m', 'tft_core.harness_cli', 'fit',
        '--repository', str(accepted), '--snapshots', str(store.root), '--output', str(output),
        '--search', str(search), '--bootstrap-draws', '20', '--max-evaluations', '3', '--model-draws', '2'],
        cwd=runtime/'core/packages/harness', env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout+result.stderr
    candidate = tomllib.loads(next(output.glob('*.toml')).read_text())['harness_candidate']
    producer = candidate['producer']
    assert producer['commit'] == candidate['code_commit'] == commit
    assert producer['dirty'] is True and producer['dirty_hash']
    assert producer['source_matches_checkout'] is True
    assert candidate['accepted_checkout_head'] == git(accepted, 'rev-parse', 'HEAD') != commit
    report = next(output.glob('*.md')).read_text()
    def section(title):
        return json.loads(report.split('## '+title+'\n\n```json\n')[1].split('\n```')[0])
    assert section('Producer code identity') == producer
    identities = section('Replay cache identities')
    assert identities and all(identity['commit'] == commit and identity['dirty'] for identity in identities)
    assert 'static and source pins' in section('Advice diff')['reference']


def test_aggregate_report_scrubs_every_path_form_but_keeps_its_own_reference_statements(tmp_path, monkeypatch):
    from tests.test_harness import combat_logs
    from tests.test_harness_tunables_io import committed_repository
    from tft_core.harness_cli import main
    from tft_harness.markdown import aggregate_only
    assert aggregate_only({'carried_citation': '/private/owner/notes'}) == {}
    omitted = 'details omitted from aggregate artifact'
    for leaked in ('games/NA1_901/events.jsonl', 'see logs\\games\\901', 'C:\\Users\\owner\\x',
            '/private/var/x', '~/logs/x', 'error at "/tmp/x"'):
        assert aggregate_only({'reason': leaked}) == {'reason': omitted}
    (tmp_path/'games').mkdir()
    (tmp_path/'accepted').mkdir()
    sessions, store = combat_logs(tmp_path/'games', results=('win', 'loss'))
    repository = committed_repository(tmp_path/'accepted')
    monkeypatch.setenv('TFT_ASSISTANT_DATA_ROOT', str(sessions.root))
    monkeypatch.setenv('TFT_ASSISTANT_CONFIG_ROOT', str(sessions.config_root))
    output = tmp_path/'reports'
    assert main(['eval', '--repository', str(repository), '--snapshots', str(store.root),
        '--output', str(output), '--bootstrap-draws', '20']) == 0
    report = next(output.glob('*.md')).read_text()
    def section(title):
        return json.loads(report.split('## '+title+'\n\n```json\n')[1].split('\n```')[0])
    assert section('Advice diff')['reference'] == (
        'latest committed accepted tunables; immutable static and source pins; original log points and seeds')
    widened = section('Widened candidate and hand-set checks')['widened_candidates']
    assert widened['reference'] == ('effective replay tunables; immutable static and source pins; '
        'original log points and seeds')
    assert omitted not in report and 'historical immutable tunables' not in report
