"""Private aggregate Markdown artifacts without decision identities or examples."""
from datetime import UTC, datetime
import json
import os
from pathlib import Path

from tft_review.contracts import json_value


_OMIT = {'examples', 'manifest', 'largest_changes', 'changed_points', 'rows',
    'target', 'conditioning', 'training_game_ids', 'holdout_game_ids',
    'eligible_game_ids', 'candidates', 'citation', 'citations'}


def aggregate_only(value):
    """Drop identity-bearing material even when games have unlocked reviews."""
    value = json_value(value)
    if isinstance(value, dict):
        return {key: aggregate_only(item) for key, item in value.items()
            if key not in _OMIT and not key.endswith(('_id', '_ids', '_path'))
            and 'puuid' not in key.lower()}
    if isinstance(value, list):
        return [aggregate_only(item) for item in value]
    if isinstance(value, str):
        # Errors can originate from filesystem or external payload validation.
        if '/' in value and not value.startswith('http'):
            return 'details omitted from aggregate artifact'
        if 'puuid' in value.lower():
            return 'private detail omitted'
    return value


def write_markdown(destination, reference, report=None, *, advice_diff=None, fit=None, priors=None, margins=None, checks=None, producer=None):
    destination = Path(destination)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    sections = [('Accepted reference', {'path': reference.path, 'file_commit': reference.commit,
        'Git blob': reference.blob, 'reference_checkout_head': reference.code_commit})]
    if producer is not None:
        sections.append(('Producer code identity', producer))
    if checks is not None:
        sections.append(('Widened candidate and hand-set checks', aggregate_only(checks)))
    if report is not None:
        identities = {json.dumps({key: row['replay_identity'].get(key) for key in
            ('commit', 'dirty', 'dirty_hash', 'runtime_source_hash')}, sort_keys=True)
            for row in report.manifest if 'replay_identity' in row}
        sections.append(('Replay cache identities', [json.loads(value) for value in sorted(identities)]))
        sections.extend([('Metrics and exclusions', aggregate_only(report.metrics)),
            ('Gates', aggregate_only(report.gates)), ('Coverage and gaps', aggregate_only(report.counts)),
            ('Calibration, report-only checks and flips', aggregate_only({name: report.metrics.get(name)
                for name in ('report_only', 'hand_set_checks', 'flip_rates')})),
            ('Advice diff', aggregate_only(advice_diff or {}))])
    if fit is not None:
        sections.append(('Fit diagnostics', aggregate_only({'status': fit.status,
            'training_objective': fit.training_objective, 'solver': fit.solver, 'gates': fit.gates})))
    if margins is not None:
        sections.append(('Margin uncertainty', aggregate_only(margins)))
    if priors is not None:
        sections.append(('Public prior qualification', aggregate_only(vars(priors))))
    sections.append(('Exclusions', {'policy': 'Missing truth is excluded per field; no imputation. Locked games contribute aggregates only.',
        'acceptance': 'Candidate only. Acceptance requires an owner commit to data; no automatic acceptance.'}))
    body = '# Harness evaluation\n\n'
    for title, value in sections:
        body += f'## {title}\n\n```json\n'+json.dumps(value, indent=2, allow_nan=False, sort_keys=True)+'\n```\n\n'
    if len(body.encode()) > 4_000_000:
        raise ValueError('Aggregate Markdown report exceeds the bounded artifact size')
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    path = destination/f'harness-{stamp}.md'
    with open(path, 'x', encoding='utf-8', opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
        output.write(body)
    return path
