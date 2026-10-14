"""Offline advice comparisons aligned to original logged decision points."""
from collections import Counter

from tft_review import ReplayProducer
from tft_review.contracts import frozen_json

from .overlay import TunableOverlay


def _decisions(batch):
    occurrences, indexed = Counter(), {}
    for row in batch.records:
        key = (row.log_seq, row.decision)
        index = occurrences[key]
        occurrences[key] += 1
        indexed[key+(index,)] = row
    return indexed


def _choice(row):
    return (row.advice.get('option_id'), row.advice.get('paused_reason'),
        row.advice.get('action') if not row.advice.get('option_id') else None)


def advice_diff(harness, candidate, game_ids=None, *, limit=20):
    if type(limit) is not int or not 0 <= limit <= 100:
        raise ValueError('Advice diff limit must be between zero and 100')
    overlay = TunableOverlay(harness.data_store, candidate)
    accepted = ReplayProducer(harness.sessions, harness.data_store,
        repository=harness.repository, hooks=harness.hooks)
    proposed = ReplayProducer(harness.sessions, overlay, repository=harness.repository,
        hooks=harness.hooks, hook_version='advice-diff:'+overlay.identity)
    selected = None if game_ids is None else set(map(str, game_ids))
    eligible, changed, exclusions, examples = 0, 0, Counter(), []
    for game in harness.sessions.list_games():
        if selected is not None and game['game_id'] not in selected:
            continue
        old, new = _decisions(accepted.produce(game['game_id'])), _decisions(proposed.produce(game['game_id']))
        for key in old.keys() | new.keys():
            if key not in old or key not in new:
                exclusions['unpaired_decision'] += 1
                continue
            before, after = old[key], new[key]
            eligible += 1
            if _choice(before) == _choice(after):
                continue
            changed += 1
            if game['review_locked']:
                continue
            difference = None if before.expected_placement is None or after.expected_placement is None else (
                after.expected_placement-before.expected_placement)
            examples.append({'game_id': game['game_id'], 'log_seq': key[0], 'decision': key[1],
                'occurrence': key[2], 'accepted_choice': before.advice.get('option_id'),
                'candidate_choice': after.advice.get('option_id'),
                'expected_placement_difference': difference})
    examples.sort(key=lambda row: (row['expected_placement_difference'] is None,
        -abs(row['expected_placement_difference'] or 0), int(row['game_id']), row['log_seq'],
        row['decision'], row['occurrence']))
    return frozen_json({'status': 'report_only', 'eligible_decisions': eligible,
        'changed_decisions': changed, 'changed_share': changed/eligible if eligible else None,
        'reason': None if eligible else 'no_paired_decisions', 'excluded': dict(exclusions),
        'largest_changes': examples[:limit], 'candidate_id': overlay.identity,
        'reference': 'historical immutable tunables; original log points and seeds'})
