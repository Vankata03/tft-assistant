"""Committed tunables come from Git HEAD; fits only ever write separate candidates."""
import os
import subprocess
import tomllib

import pytest
import tomli_w

from tft_data import DataError, TaggedValue
from tests.test_replay_contracts import historical_data


def git(repository, *args):
    return subprocess.run(['git', '-C', str(repository), *args], check=True,
        capture_output=True, text=True).stdout.strip()


def committed_repository(tmp_path, *, patches=(('18.1', '2026-09-01T10:00:00+03:00'),
                                                 ('18.2', '2026-09-15T10:00:00+03:00'))):
    """A private Git checkout whose HEAD holds reviewed patch files."""
    (tmp_path/'source').mkdir()
    historical_data(tmp_path/'source')
    source = tmp_path/'source'/'patch'
    repository = tmp_path/'repository'
    (repository/'data').mkdir(parents=True)
    git(repository, 'init', '-q')
    git(repository, 'config', 'user.email', 'fixture@example.invalid')
    git(repository, 'config', 'user.name', 'Fixture')
    (repository/'data'/'patches.toml').write_text(tomli_w.dumps({'patches': dict(patches)}))
    for patch, _ in patches:
        target = repository/'data'/patch
        target.mkdir()
        for name in ('static.toml', 'tunables.toml'):
            document = tomllib.loads((source/name).read_text())
            document['patch'] = patch
            if name == 'tunables.toml':
                document['fields']['fight_scale']['value'] = float(patch.split('.')[1])
            (target/name).write_text(tomli_w.dumps(document))
        (target/'entities.json').write_text((source/'entities.json').read_text())
    git(repository, 'add', '.')
    git(repository, 'commit', '-q', '-m', 'fixture patches')
    return repository


def test_latest_committed_tunables_follow_the_patch_calendar_at_head_not_the_worktree(tmp_path):
    from tft_harness.tunables_io import latest_committed_tunables

    repository = committed_repository(tmp_path)
    tunables = repository/'data'/'18.2'/'tunables.toml'
    edited = tomllib.loads(tunables.read_text())
    edited['fields']['fight_scale']['value'] = 99.0
    tunables.write_text(tomli_w.dumps(edited))
    committed = latest_committed_tunables(repository)
    assert committed.patch == '18.2'
    assert committed.set_number == 18
    assert committed.commit == git(repository, 'rev-parse', 'HEAD')
    assert committed.fields['fight_scale'] == TaggedValue(2.0, 'owner', '', '1')
    assert committed.values()['fight_scale'] == 2.0
    assert 'wisp_buy_margin' in committed.fields


def test_missing_committed_tunables_fail_visibly(tmp_path):
    from tft_harness.tunables_io import latest_committed_tunables

    repository = committed_repository(tmp_path, patches=())
    with pytest.raises(DataError, match='No committed patch'):
        latest_committed_tunables(repository)
    with pytest.raises(DataError, match='Git'):
        latest_committed_tunables(tmp_path/'not-a-checkout')


def test_candidate_is_a_whole_loadable_copy_with_fitted_values_and_never_replaces_committed(tmp_path):
    from tft_data.config import load_patch
    from tft_harness.tunables_io import latest_committed_tunables, write_candidate

    repository = committed_repository(tmp_path)
    committed = latest_committed_tunables(repository)
    before = (repository/'data'/'18.2'/'tunables.toml').read_bytes()
    path = write_candidate(committed, {'fight_scale': 1.75, 'win_scale_by_stage': {'3': 1.5}},
        tmp_path/'candidates', citation='Family-1 fit on 8 training games; holdout gates passed')
    assert path.parent == tmp_path/'candidates'
    if os.name == 'posix':
        assert path.stat().st_mode & 0o077 == 0
    assert (repository/'data'/'18.2'/'tunables.toml').read_bytes() == before
    text = path.read_text()
    assert text.startswith('# Candidate tunables for patch 18.2')
    assert committed.commit in text and 'data/18.2/tunables.toml' in text
    document = tomllib.loads(text)
    assert document['patch'] == '18.2'
    assert document['fields']['fight_scale'] == {'value': 1.75, 'source': 'owner',
        'citation': 'Family-1 fit on 8 training games; holdout gates passed', 'family': '1'}
    assert document['fields']['unit_weight'] == tomllib.loads(before.decode())['fields']['unit_weight']
    # The owner accepts by committing the file unchanged; it must load as a patch.
    accepted = tmp_path/'accepted'
    accepted.mkdir()
    for name in ('static.toml', 'entities.json'):
        (accepted/name).write_bytes((repository/'data'/'18.2'/name).read_bytes())
    (accepted/'tunables.toml').write_text(text)
    assert load_patch(accepted)[3]['fight_scale'].value == 1.75
    second = write_candidate(committed, {'fight_scale': 1.5}, tmp_path/'candidates', citation='second')
    assert second != path and path.read_text() == text


@pytest.mark.parametrize('updates', [{'opponent_growth_curve': {}}, {'unknown': 1},
    {'fight_scale': float('nan')}, {}])
def test_candidate_rejects_unknown_computed_nonfinite_or_empty_updates(tmp_path, updates):
    from tft_harness.tunables_io import latest_committed_tunables, write_candidate

    committed = latest_committed_tunables(committed_repository(tmp_path))
    with pytest.raises(DataError):
        write_candidate(committed, updates, tmp_path/'candidates', citation='fit')
    assert not (tmp_path/'candidates').exists() or not any((tmp_path/'candidates').iterdir())


def test_candidate_destination_cannot_be_the_committed_data_directory(tmp_path):
    from tft_harness.tunables_io import latest_committed_tunables, write_candidate

    repository = committed_repository(tmp_path)
    committed = latest_committed_tunables(repository)
    with pytest.raises(DataError, match='committed'):
        write_candidate(committed, {'fight_scale': 1.5}, repository/'data'/'18.2', citation='fit')


def test_reference_separates_file_commit_blob_and_code_and_preserves_public_tags(tmp_path):
    from tft_harness.tunables_io import latest_committed_tunables, write_candidate

    repository = committed_repository(tmp_path)
    accepted_commit = git(repository, 'rev-parse', 'HEAD')
    (repository/'unrelated').write_text('code identity')
    git(repository, 'add', 'unrelated')
    git(repository, 'commit', '-q', '-m', 'unrelated code change')
    reference = latest_committed_tunables(repository, path='data/18.2/tunables.toml')
    assert reference.commit == accepted_commit
    assert reference.code_commit == git(repository, 'rev-parse', 'HEAD')
    assert reference.blob == git(repository, 'rev-parse', 'HEAD:data/18.2/tunables.toml')
    path = write_candidate(reference, {'unit_prior_strength': 4.0}, tmp_path/'out',
        citation='Qualified public empirical Bayes fixture', sources={'unit_prior_strength': 'public-statistics'})
    assert tomllib.loads(path.read_text())['fields']['unit_prior_strength']['source'] == 'public-statistics'


def test_committed_overlay_retains_public_provenance_and_historical_static(tmp_path):
    from tft_harness.overlay import TunableOverlay
    store, data = historical_data(tmp_path)
    field = TaggedValue(4.0, 'public-statistics', 'https://public.example/cohort', '3')
    overlay = TunableOverlay(store, {}, tagged_fields={'unit_prior_strength': field})
    replayed = overlay.get(data.snapshot_id)
    assert replayed.tunables['unit_prior_strength'] == field
    assert replayed.static == data.static
    assert replayed.entities == data.entities
    assert replayed.statistics == data.statistics


def test_nested_repository_reference_cannot_write_candidate_into_accepted_data(tmp_path):
    from tft_harness.tunables_io import latest_committed_tunables, write_candidate
    from tft_data import DataError
    repository = committed_repository(tmp_path)
    reference = latest_committed_tunables(repository/'data')
    with pytest.raises(DataError, match='committed'):
        write_candidate(reference, {'fight_scale':1.5}, repository/'data', citation='fixture')


@pytest.mark.parametrize('dirty_path', [
    'core/packages/engine/src/tft_engine/planning.py',
    'core/packages/engine/src/tft_engine/untracked_fixture.py',
    'core/uv.lock', 'core/pyproject.toml'])
def test_producer_identity_detects_dirty_running_checkout_from_package_cwd(tmp_path, dirty_path):
    import json
    import sys

    runtime = runtime_repository(tmp_path)
    clean_commit = git(runtime, 'rev-parse', 'HEAD')
    path = runtime/dirty_path
    with path.open('a') as output:
        output.write('\n# public dirty-runtime fixture\n')
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str,
        [runtime/'core/src', *sorted((runtime/'core/packages').glob('*/src'))])))
    result = subprocess.run([sys.executable, '-c',
        'import json; from tft_harness.tunables_io import producer_identity; print(json.dumps(producer_identity()))'],
        cwd=runtime/'core/packages/harness/src/tft_harness', env=env, capture_output=True, text=True, check=True)
    identity = json.loads(result.stdout)
    assert identity['commit'] == clean_commit
    assert identity['source_matches_checkout'] is True
    assert identity['runtime_mismatch_count'] == 0
    assert identity['dirty'] is True
    assert identity['dirty_hash']


def test_accepted_overlay_keeps_refresh_computed_pins_and_replays_guide_without_own_line(tmp_path):
    from datetime import timedelta
    from tft_harness.overlay import TunableOverlay
    from tft_harness.tunables_io import latest_committed_tunables
    from tft_engine.growth import growth_curve
    from tft_review import ReplayProducer
    from tft_core.storage import SessionStore
    from tests.test_replay_contracts import GuideFeed, NOW, ROOT, log_snapshot

    class WithUnguidedComp(GuideFeed):
        name = 'unguided-fixture'

        def fetch(self):
            feed = super().fetch()
            feed['guides'].append(dict(feed['guides'][0], id='no-line', line=[]))
            return feed

    store, _ = historical_data(tmp_path)
    path = tmp_path/'patch/tunables.toml'
    document = tomllib.loads(path.read_text())
    for name in ('default_lines_by_carry_cost', 'opponent_growth_curve'):
        document['fields'][name]['source'] = 'default'
    path.write_text(tomli_w.dumps(document))
    refreshed = store.refresh(tmp_path/'patch', now=NOW+timedelta(seconds=5),
        sources=(WithUnguidedComp(),), computations={'opponent_growth_curve': growth_curve}).snapshot
    (tmp_path/'accepted').mkdir()
    reference = latest_committed_tunables(committed_repository(tmp_path/'accepted'))
    accepted = TunableOverlay(store, {}, tagged_fields=reference.fields)
    overlaid = accepted.get(refreshed.snapshot_id)
    assert not refreshed.guides['no-line'].line
    for name in ('default_lines_by_carry_cost', 'opponent_growth_curve'):
        assert overlaid.tunables[name] == refreshed.tunables[name]
    for name in ('static', 'entities', 'guides', 'sources', 'statistics', 'snapshot_id', 'patch'):
        assert getattr(overlaid, name) == getattr(refreshed, name)
    assert overlaid.tunables['fight_scale'] == reference.fields['fight_scale']
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.start_game('901', patch=refreshed.patch, data_snapshot_id=refreshed.snapshot_id,
        timestamp=NOW.isoformat())
    sessions.append_event('snapshot', log_snapshot(refreshed), timestamp=NOW.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=10)).isoformat())
    original = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    replay = ReplayProducer(sessions, accepted, repository=ROOT).produce('901')
    econ = next(record for record in replay.records if record.decision == 'econ')
    assert econ.options and econ.expected_placement is not None
    assert [context.seed for context in replay.contexts] == [context.seed for context in original.contexts]
    assert store.get(refreshed.snapshot_id) == refreshed


def runtime_repository(tmp_path):
    import shutil
    from tests.test_replay_contracts import ROOT
    runtime = tmp_path/'runtime'
    runtime.mkdir()
    for source in [ROOT/'core/src', *sorted((ROOT/'core/packages').glob('*/src'))]:
        shutil.copytree(source, runtime/source.relative_to(ROOT), ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('uv.lock', 'pyproject.toml'):
        shutil.copyfile(ROOT/'core'/name, runtime/'core'/name)
    (runtime/'.gitignore').write_text('__pycache__/\n')
    git(runtime, 'init', '-q')
    git(runtime, 'config', 'user.email', 'fixture@example.invalid')
    git(runtime, 'config', 'user.name', 'Fixture')
    git(runtime, 'add', '.')
    git(runtime, 'commit', '-qm', 'runtime source fixture')
    return runtime


def test_candidate_destination_rejects_case_alias_of_committed_data(tmp_path):
    from tft_harness.tunables_io import latest_committed_tunables, write_candidate
    repository = committed_repository(tmp_path)
    alias = repository/'DATA'
    if not alias.exists():
        alias.symlink_to(repository/'data', target_is_directory=True)
    reference = latest_committed_tunables(repository)
    with pytest.raises(DataError, match='committed'):
        write_candidate(reference, {'fight_scale': 1.5}, alias/'new-patch', citation='fixture')
