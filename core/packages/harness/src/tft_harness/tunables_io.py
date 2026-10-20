"""Read the latest tunables committed at Git HEAD and write separate candidates.

Git is the only record of accepted tunables. The harness reads the committed
file from HEAD, never the working tree, and writes each fit as a whole new
candidate file that the owner accepts by committing it to ``data/<patch>/``.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
import subprocess
import tomllib

import tomli_w

from tft_data import DataError
from tft_data.config import TUNABLE_FAMILIES, tagged
from tft_data.models import plain


@dataclass(frozen=True)
class CommittedTunables:
    repository: Path
    commit: str
    code_commit: str
    blob: str
    patch: str
    set_number: int
    path: str
    document: dict
    fields: dict

    def values(self):
        return {name: plain(value.value) for name, value in self.fields.items()}


def _show(repository, revision_path):
    try:
        result = subprocess.run(['git', '-C', str(repository), 'show', revision_path],
            capture_output=True, check=False)
    except OSError as error:
        raise DataError(f'Git is unavailable for committed tunables: {error}') from None
    return result.stdout.decode('utf-8') if result.returncode == 0 else None


def _families(set_number):
    return {name: family for name, family in TUNABLE_FAMILIES.items()
        if set_number == 18 or name != 'wisp_buy_margin'}


def latest_committed_tunables(repository, *, path=None):
    """Return the tunables of the newest calendar patch committed at HEAD."""
    repository = Path(repository).resolve()
    try:
        repository = Path(subprocess.run(['git', '-C', str(repository), 'rev-parse', '--show-toplevel'],
            capture_output=True, check=True, text=True).stdout.strip())
        commit = subprocess.run(['git', '-C', str(repository), 'rev-parse', 'HEAD'],
            capture_output=True, check=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        raise DataError(f'Committed tunables require a Git checkout with a HEAD commit: {repository}') from None
    calendar = _show(repository, f'{commit}:data/patches.toml')
    try:
        rows = tomllib.loads(calendar or '').get('patches', {})
        boundaries = sorted((datetime.fromisoformat(str(when)), patch) for patch, when in rows.items())
    except (ValueError, TypeError) as error:
        raise DataError(f'Invalid committed patch calendar: {error}') from None
    if path is not None:
        selected = Path(path)
        if selected.is_absolute() or ".." in selected.parts or len(selected.parts) != 3 or selected.parts[0] != "data" or selected.name != "tunables.toml":
            raise DataError("Accepted tunables require an unambiguous tracked data/<patch>/tunables.toml path")
        boundaries = [(when, patch) for when, patch in boundaries if selected.as_posix() == f"data/{patch}/tunables.toml"]
    for _, patch in reversed(boundaries):
        tunables_path = f'data/{patch}/tunables.toml'
        tunables_text = _show(repository, f'{commit}:{tunables_path}')
        static_text = _show(repository, f'{commit}:data/{patch}/static.toml')
        if tunables_text is None or static_text is None:
            continue
        try:
            document = tomllib.loads(tunables_text)
            static = tomllib.loads(static_text)
        except ValueError as error:
            raise DataError(f'Invalid committed patch files for {patch}: {error}') from None
        set_number = static.get('set_number')
        if document.get('patch') != patch or static.get('patch') != patch or type(set_number) is not int:
            raise DataError(f'Committed patch files for {patch} disagree on their patch or set')
        families = _families(set_number)
        fields = tagged(document.get('fields'), 'tunables', families=families)
        missing = set(families)-set(fields)-{'opponent_growth_correction_by_stage'}
        if missing:
            raise DataError(f'Committed tunables miss fields: {sorted(missing)}')
        try:
            file_commit = subprocess.run(["git", "-C", str(repository), "log", "-1", "--format=%H", commit, "--", tunables_path], capture_output=True, check=True, text=True).stdout.strip()
            blob = subprocess.run(["git", "-C", str(repository), "rev-parse", f"{commit}:{tunables_path}"], capture_output=True, check=True, text=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            raise DataError('Cannot read accepted tunables identity from the pinned Git commit') from None
        return CommittedTunables(repository, file_commit, commit, blob, patch, set_number, tunables_path, document, fields)
    raise DataError('No committed patch tunables at HEAD; commit data/<patch>/tunables.toml first')


def runtime_repository():
    """Return the Git checkout containing the running harness package."""
    try:
        result = subprocess.run(['git', '-C', str(Path(__file__).resolve().parent),
            'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=True)
        return Path(result.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        raise DataError('Running harness source requires a Git checkout for replay identity') from None


def producer_identity():
    """Identify running producer source independently of the accepted-data checkout."""
    package = Path(__file__).resolve().parent
    git_failed = False
    def git(*args):
        nonlocal git_failed
        try:
            result = subprocess.run(['git', '-C', str(root or package), *args], capture_output=True, check=False)
        except OSError:
            git_failed = True
            return b''
        git_failed |= result.returncode != 0
        return result.stdout if result.returncode == 0 else b''
    root = None
    root = git('rev-parse', '--show-toplevel').decode().strip()
    commit = git('rev-parse', 'HEAD').decode().strip()
    runtime, mismatches = {}, 0
    for name in ('tft_data', 'tft_engine', 'tft_review', 'tft_harness', 'tft_core'):
        module = sys.modules.get(name)
        if module is None and name == 'tft_core':
            continue
        module = module or importlib.import_module(name)
        source = Path(module.__file__).resolve().parent
        prefix = 'core/src/tft_core' if name == 'tft_core' else f'core/packages/{name[4:]}/src/{name}'
        for path in sorted(source.rglob('*.py')):
            relative = f'{prefix}/{path.relative_to(source).as_posix()}'
            content = path.read_bytes()
            runtime[relative] = hashlib.sha256(content).hexdigest()
            expected = Path(root)/relative if root else None
            mismatches += expected is None or not expected.is_file() or expected.read_bytes() != content
    source_hash = hashlib.sha256(json.dumps(runtime, sort_keys=True).encode()).hexdigest()
    paths = ('core/src', 'core/packages', 'core/uv.lock', 'core/pyproject.toml')
    status = git('status', '--porcelain=v1', '--untracked-files=all', '--', *paths)
    diff = git('diff', 'HEAD', '--binary', '--', *paths)
    result = {'commit': commit or 'unavailable', 'runtime_source_hash': source_hash,
        'runtime_mismatch_count': mismatches, 'source_matches_checkout': bool(root) and not mismatches and not git_failed,
        'dirty': bool(status or mismatches or git_failed), 'python': '.'.join(map(str, sys.version_info[:3]))}
    if status:
        result['dirty_hash'] = hashlib.sha256(status+diff+source_hash.encode()).hexdigest()
    return result


def _finite(value):
    if isinstance(value, bool) or value is None:
        return True
    if isinstance(value, (int, float)):
        return isfinite(value)
    if isinstance(value, str):
        return True
    if isinstance(value, dict):
        return all(isinstance(key, str) and _finite(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return all(_finite(item) for item in value)
    return False


def write_candidate(committed, updates, destination, *, citation, generated_at=None, notes=(), sources=None, provenance=None, citations=None):
    """Write a whole candidate copy of ``committed`` with ``updates`` applied.

    Only fitted families (1, 2 and 3) can change. Each changed field records
    its fit citation. Existing files are never replaced, including the
    committed file and earlier candidates.
    """
    if not updates:
        raise DataError('A candidate requires at least one fitted tunable')
    if not isinstance(citation, str) or not citation.strip():
        raise DataError('Candidate tunables require a fit citation')
    families = _families(committed.set_number)
    for name, value in updates.items():
        if families.get(name) not in ('1', '2', '3'):
            raise DataError(f'Candidates change fitted families only: {name}')
        if not _finite(plain(value)):
            raise DataError(f'Candidate value must be finite TOML data: {name}')
    destination = Path(destination).resolve()
    data_root = (committed.repository/'data').resolve()
    if any(ancestor == data_root or (ancestor.exists() and data_root.exists()
            and ancestor.samefile(data_root)) for ancestor in (destination, *destination.parents)):
        raise DataError('Candidates are never written into the committed data directory')
    document = plain(committed.document)
    document['fields'] = dict(document['fields'])
    for name, value in sorted(updates.items()):
        document['fields'][name] = {'value': plain(value), 'source': (sources or {}).get(name, 'owner'),
            'citation': (citations or {}).get(name, citation), 'family': families[name]}
    tagged(document['fields'], 'candidate tunables', families=families)
    producer = (provenance or {}).get('runtime_code') or producer_identity()
    document['harness_candidate'] = {'accepted_file_commit': committed.commit, 'accepted_blob': committed.blob,
        'accepted_path': committed.path, 'accepted_checkout_head': committed.code_commit,
        'code_commit': producer['commit'], 'producer': producer, 'status': 'unaccepted',
        'provenance': plain(provenance or {})}
    if not _finite(document['harness_candidate']):
        raise DataError('Candidate provenance must be finite TOML data')
    body = tomli_w.dumps(document)
    if tomllib.loads(body) != document:
        raise DataError('Candidate tunables do not round-trip through TOML')
    generated_at = generated_at or datetime.now(UTC)
    header = [f'# Candidate tunables for patch {committed.patch}, written by tft-harness.',
        f'# Base: {committed.path} at commit {committed.commit}; Git blob {committed.blob}.',
        f'# Code identity: {producer["commit"]}; runtime source hash {producer["runtime_source_hash"]}.',
        f'# Generated {generated_at.isoformat()}. Changed: {", ".join(sorted(updates))}.',
        f'# Accept by copying this file to {committed.path} and committing it.',
        *(f'# {line}' for note in notes for line in str(note).splitlines())]
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = generated_at.strftime('%Y%m%dT%H%M%S%fZ')
    for attempt in range(1000):
        suffix = f'-{attempt}' if attempt else ''
        path = destination/f'tunables-{committed.patch}-{stamp}{suffix}.toml'
        try:
            with open(path, 'x', encoding='utf-8', opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
                output.write('\n'.join(header)+'\n\n'+body)
            return path
        except FileExistsError:
            continue
    raise DataError('Could not choose a new candidate file name')
