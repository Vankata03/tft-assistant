"""Offline advice comparisons aligned to original logged decision points."""
from collections import Counter
from collections.abc import Mapping
import json

from tft_review import ReplayProducer
from tft_review.contracts import frozen_json, json_value

from .overlay import TunableOverlay


def _decisions(batch):
    occurrences, indexed = Counter(), {}
    for row in batch.records:
        key = (row.log_seq, row.decision)
        index = occurrences[key]
        occurrences[key] += 1
        indexed[key+(index,)] = row
    return indexed


# Recommendation identity excludes forecasts, confidence, costs and rollout evidence.
# Nested physical board/action fields retain operation targets and execution order.
_OPERATION_FIELDS = frozenset(('operation', 'unit_id', 'unit_index', 'item_id', 'augment_id',
    'wisp_id', 'slot', 'slots', 'buys', 'sell', 'hold', 'swap_in', 'swap_out', 'board',
    'steps', 'layout', 'ranking', 'line_id', 'comp_id', 'levels', 'rolls', 'gold_floor',
    'target_level', 'target_round', 'bench', 'units', 'stars', 'items', 'position', 'cell',
    'from', 'to', 'overflow_sells', 'equip', 'recipient', 'line', 'transfers',
    'holder', 'holder_index', 'from_index', 'item_ids', 'consume_tool', 'pin_alternative',
    'adjustments'))
# Values of these fields are kept whole: round-keyed schedules and threat-adjustment flags.
_WHOLE_FIELDS = frozenset(('levels', 'rolls', 'adjustments'))
# The selected plan is operational; candidate rankings, similarity and historical
# player/divergence metadata describe evidence rather than the recommendation.
_GAME_PLAN_FIELDS = frozenset(('status', 'target', 'backup', 'pivot_from', 'pivot_to', 'line'))


def _targets(value):
    if isinstance(value, Mapping):
        result = {key: json_value(item) if key in _WHOLE_FIELDS else _targets(item)
            for key, item in value.items() if key in _OPERATION_FIELDS}
        plan = value.get('game_plan')
        if isinstance(plan, Mapping):
            result['game_plan'] = {key: _targets(item) if key == 'line' else json_value(item)
                for key, item in plan.items() if key in _GAME_PLAN_FIELDS}
        return result
    if isinstance(value, (tuple, list)):
        return [_targets(item) for item in value]
    return value


def _choice(row):
    payload = row.advice.get('payload', {})
    return (row.advice.get('option_id'), row.advice.get('action'),
        bool(payload.get('paused')), payload.get('reason') if payload.get('paused') else None,
        _targets(payload))


def _summary(row):
    return json.dumps({'action': row.advice.get('action'),
        'targets': _targets(row.advice.get('payload', {}))}, sort_keys=True, ensure_ascii=False)[:512]


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
        original_batch, candidate_batch = accepted.produce(game['game_id']), proposed.produce(game['game_id'])
        original_seeds = {context.log_seq: context.seed for context in original_batch.contexts}
        if original_seeds != {context.log_seq: context.seed for context in candidate_batch.contexts}:
            raise ValueError('Candidate cannot preserve original replay seeds; advice diff unavailable')
        old, new = _decisions(original_batch), _decisions(candidate_batch)
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
                'occurrence': key[2], 'accepted_choice': str(before.advice.get('option_id') or before.advice.get('action') or '')[:256],
                'accepted_recommendation': _summary(before),
                'candidate_choice': str(after.advice.get('option_id') or after.advice.get('action') or '')[:256],
                'candidate_recommendation': _summary(after),
                'expected_placement_difference': difference})
    examples.sort(key=lambda row: (row['expected_placement_difference'] is None,
        -abs(row['expected_placement_difference'] or 0), int(row['game_id']), row['log_seq'],
        row['decision'], row['occurrence']))
    return frozen_json({'status': 'report_only', 'eligible_decisions': eligible,
        'changed_decisions': changed, 'changed_share': changed/eligible if eligible else None,
        'reason': None if eligible else 'no_paired_decisions', 'excluded': dict(exclusions),
        'largest_changes': examples[:limit], 'candidate_id': overlay.identity,
        'reference': 'historical immutable tunables; original log points and seeds'})
