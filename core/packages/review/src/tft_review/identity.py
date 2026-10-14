"""Replay cache identity from checked Git, running sources and frozen inputs."""
import hashlib
import inspect
import json
from pathlib import Path
import subprocess

from tft_engine.registry import default_hooks

from .contracts import REPLAY_SCHEMA_VERSION, json_value


def digest(value):
    return hashlib.sha256(json.dumps(json_value(value), sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def replay_identity(repository, events, data, hooks, hook_version):
    import tft_data
    import tft_engine
    import tft_review

    repository = Path(repository).resolve()
    def git(*args):
        return subprocess.run(['git', '-C', str(repository), *args], check=True,
            capture_output=True).stdout
    commit = git('rev-parse', 'HEAD').decode().strip()
    relevant = ('core/packages/*/src/**', 'core/src/**', 'core/uv.lock', 'core/pyproject.toml',
        'core/packages/*/pyproject.toml', 'data/**')
    status = git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--', *relevant)
    dirty_content = [status.hex(), git('diff', 'HEAD', '--binary', '--', *relevant).hex()]
    for name in git('ls-files', '--others', '--exclude-standard', '-z', '--', *relevant).split(b'\0'):
        if name:
            path = repository / name.decode()
            dirty_content.append([name.decode(), hashlib.sha256(path.read_bytes()).hexdigest()])
    runtime, mismatches = {}, []
    for package, module in (('data', tft_data), ('engine', tft_engine), ('review', tft_review)):
        source = Path(module.__file__).parent
        for path in sorted(source.rglob('*.py')):
            relative = f'core/packages/{package}/src/{module.__name__}/{path.relative_to(source).as_posix()}'
            content = path.read_bytes()
            runtime[relative] = hashlib.sha256(content).hexdigest()
            checked = repository / relative
            if not checked.is_file() or checked.read_bytes() != content:
                mismatches.append(relative)
    registry, cacheable_hooks = [], True
    for hook in default_hooks() if hooks is None else hooks:
        row = {name: json_value(getattr(hook, name)) for name in
            ('name', 'required_fields', 'fit_required_fields', 'advice_phases',
             'activation_field', 'dependency_fields')}
        for name in ('fit', 'advice'):
            function = getattr(hook, name)
            if function is None:
                row[name] = None
                continue
            try:
                source = inspect.getsource(function)
                row[name] = {'module': function.__module__, 'name': function.__qualname__,
                    'source_hash': hashlib.sha256(source.encode()).hexdigest()}
                if not inspect.isfunction(function) or function.__closure__:
                    cacheable_hooks = False
            except (OSError, TypeError, AttributeError):
                row[name] = {'unavailable': True}
                cacheable_hooks = False
        registry.append(row)
    return {'commit': commit, 'dirty': bool(status or mismatches),
        'dirty_hash': digest(dirty_content) if status else None,
        'runtime_source_hash': digest(runtime), 'runtime_mismatches': mismatches,
        'data_snapshot_id': data.snapshot_id, 'tunables_hash': digest(data.tunables),
        'log_hash': digest(events), 'schema_version': REPLAY_SCHEMA_VERSION,
        'hook_version': hook_version, 'hook_hash': digest(registry),
        'hooks_cacheable': cacheable_hooks, 'finished': any(row['kind']=='game_end' for row in events),
        'model_version': events[0]['payload'].get('model_version')}
