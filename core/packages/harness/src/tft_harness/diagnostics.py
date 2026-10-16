"""Offline advice comparisons aligned to original logged decision points."""
from collections import Counter, defaultdict
from collections.abc import Mapping
import json

from tft_review import ReplayProducer
from tft_review.contracts import frozen_json, json_value

from .overlay import TunableOverlay
from .measurement import mean_by_game


def aggregate(rows):
    rows = list(rows)
    return {'value': mean_by_game(rows), 'eligible_rows': len(rows),
        'eligible_games': len({game for game, _ in rows}),
        'reason': None if rows else 'no_eligible_truth'}


def combine_aggregates(samples):
    samples = list(samples)
    result = aggregate((game, summary['value']) for game, summary in samples if summary['eligible_rows'])
    result['eligible_rows'] = sum(summary['eligible_rows'] for _, summary in samples)
    return result


def combine_diagnostics(rows, reports, counts):
    """Fold per-game summaries without retaining complete replay batches."""
    result = report_diagnostics(rows, (), counts)
    for name in ('follow_ignore_placement', 'expected_placement_by_follow_rate', 'positioning_residual'):
        result[name] = {band: combine_aggregates((game, report[name][band]) for game, report in reports)
            for band in result[name]}
    result['owner_disagree_rate'] = combine_aggregates((game, report['owner_disagree_rate']) for game, report in reports)
    excluded = Counter()
    for _, report in reports:
        excluded.update(report['excluded'])
    result['excluded'] = dict(excluded)
    names = {name for _, report in reports for name in report['stale_fields']}
    result['stale_fields'] = {}
    for name in sorted(names):
        samples = [(game, report['stale_fields'][name]) for game, report in reports if name in report['stale_fields']]
        result['stale_fields'][name] = {'silences': sum(row['silences'] for _, row in samples),
            'observations': sum(row['observations'] for _, row in samples),
            'share': mean_by_game((game, row['share']) for game, row in samples)}
    domains = {name for _, report in reports for name in report['delivery']['by_kind']}
    result['delivery']['by_kind'] = {}
    for name in sorted(domains):
        samples = [(game, report['delivery']['by_kind'][name]) for game, report in reports
            if name in report['delivery']['by_kind']]
        result['delivery']['by_kind'][name] = {key: combine_aggregates((game, row[key]) for game, row in samples)
            for key in ('too_late_share', 'capture_to_show_seconds', 'capture_to_show_over_budget_share')}
        result['delivery']['by_kind'][name].update({
            'missing_display_observations': sum(row['missing_display_observations'] for _, row in samples),
            'end_to_end_late_share': None, 'reason': 'game_change_timestamp_not_logged'})
    delivery_excluded = Counter()
    for _, report in reports:
        delivery_excluded.update(report['delivery']['excluded'])
    result['delivery']['excluded'] = dict(delivery_excluded)
    return result


def report_diagnostics(rows, games, counts):
    """Only aggregates escape this boundary, including for locked games."""
    curves = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row['metric'] == 'fight_brier':
            curves[str(row['stage'])][min(9, int(row['prediction']*10))].append(row)
    calibration = {stage: [{'lower': bucket/10, 'upper': (bucket+1)/10,
        'prediction': aggregate((row['game_id'], row['prediction']) for row in sample)['value'],
        'truth': aggregate((row['game_id'], row['truth']) for row in sample)['value'],
        'eligible_rows': len(sample), 'eligible_games': len({row['game_id'] for row in sample})}
        for bucket, sample in sorted(buckets.items())] for stage, buckets in sorted(curves.items())}
    follow_placement, expected, position = defaultdict(list), defaultdict(list), defaultdict(list)
    missing, stale, field_denominators, disagreement = Counter(), Counter(), Counter(), []
    latency_games = []
    for game in games:
        batch, data, review, placement, tags = (game[name] for name in ('batch', 'data', 'review', 'placement', 'tags'))
        game_id = batch.game_id
        followed = review.summary.get('follow_rate', {}).get('value')
        by_seq = {point['log_seq']: point for point in review.timeline if point['category'] == 'econ'}
        if followed is not None:
            band = 'low' if followed < 1/3 else 'medium' if followed < 2/3 else 'high'
            for row in rows:
                if row['game_id'] == game_id and row['metric'] == 'expected_placement_mae':
                    expected[band].append((game_id, row['prediction']))
        else:
            missing['follow_rate_unavailable'] += 1
        for point in review.timeline:
            status = point['shown'].get('status')
            if status in ('followed', 'engine_error', 'ignored') and placement is not None:
                follow_placement['ignored' if status == 'ignored' else 'followed'].append((game_id, placement))
            else:
                missing['follow_ignore:'+str(point['shown'].get('reason') or status)] += 1
        for row in rows:
            if row['game_id'] != game_id or row['metric'] != 'fight_brier':
                continue
            candidates = [record for record in batch.records if record.decision == 'positioning'
                and record.log_seq <= row['log_seq']]
            record = candidates[-1] if candidates else None
            payload = record.advice.get('payload', {}) if record else {}
            if not any(payload.get('adjustments', {}).values()):
                continue
            point = next((point for point in review.timeline if point['engine_decision_id'] == record.decision_id), None)
            status = point['shown'].get('status') if point else None
            if status in ('followed', 'engine_error', 'ignored'):
                position['ignored' if status == 'ignored' else 'followed'].append((game_id, row['prediction']-row['truth']))
            else:
                missing['positioning_follow_unavailable'] += 1
        if tags is None:
            missing['owner_tags_unavailable'] += 1
        elif tags:
            disagreement.append((game_id, sum(tag == 'disagree' for tag in tags.values())/len(tags)))
        from tft_engine.planning import field_age
        for context in batch.contexts:
            snapshot = batch.snapshot_for(context)
            for name, field in snapshot.fields.items():
                field_denominators[name] += 1
                stale[name] += (f'stale_field:{name}' in context.unavailable
                    or field.age_seconds(snapshot.captured_at) > field_age(data, name, snapshot))
        latency_games.append(delivery_diagnostics(batch))
        # Whole-horizon residual labels use actual B attribution when it is
        # present; absent attribution never turns generated advice into shown.
        for row in rows:
            if row['game_id'] == game_id and row['metric'].startswith('line_'):
                point = by_seq.get(row['log_seq'])
                row['initial_advice_status'] = point['shown']['status'] if point else 'unavailable'
    return {'status': 'report_only', 'calibration_by_stage': calibration,
        'follow_ignore_placement': {name: aggregate(follow_placement[name]) for name in ('followed', 'ignored')},
        'follow_ignore_interpretation': 'confounded descriptive placement; no causal or fitted gate',
        'expected_placement_by_follow_rate': {name: aggregate(expected[name]) for name in ('low', 'medium', 'high')},
        'follow_rate_bands': {'low': '[0,1/3)', 'medium': '[1/3,2/3)', 'high': '[2/3,1]'},
        'positioning_residual': {name: aggregate(position[name]) for name in ('followed', 'ignored')},
        'owner_disagree_rate': aggregate(disagreement), 'excluded': dict(missing),
        'stale_fields': {name: {'silences': stale[name], 'observations': total, 'share': stale[name]/total}
            for name, total in sorted(field_denominators.items())},
        'gap_share': counts['gap_rounds']/counts['known_rounds'] if counts['known_rounds'] else None,
        'gap_rounds': counts['gap_rounds'], 'known_rounds': counts['known_rounds'],
        'delivery': aggregate_deliveries(latency_games)}


def delivery_diagnostics(batch):
    """Read emitted deliveries/acks; invalidations after display are not drops."""
    from datetime import datetime

    rows, excluded = [], Counter()
    budgets = {'shop': .5, 'econ': 2., 'positioning': 2.5,
        'augment': 2., 'wisp': .5, 'carousel': 3.}
    for event in batch.observations:
        if event['kind'] != 'advice_delivery':
            continue
        payload = event['payload']
        summary = payload.get('summary', {})
        for advice in summary.get('advice', ()):
            key = (payload.get('delivery_revision'), advice.get('decision_id'), advice.get('option_id'))
            shown, dropped = [], []
            for witness in batch.observations:
                raw = witness['payload']
                if (raw.get('delivery_revision'), raw.get('decision_id')) != key[:2]:
                    continue
                if raw.get('option_id', key[2]) != key[2] or witness['seq'] <= event['seq']:
                    continue
                if witness['kind'] == 'ui_show':
                    shown.append(witness)
                elif witness['kind'] == 'advice_too_late':
                    dropped.append(witness)
            shown_at = min((datetime.fromisoformat(witness['timestamp']) for witness in shown), default=None)
            too_late = any(shown_at is None or datetime.fromisoformat(witness['timestamp']) < shown_at for witness in dropped)
            domain = advice.get('domain', advice.get('decision'))
            captured = payload.get('captured_at')
            latency = (shown_at-datetime.fromisoformat(captured)).total_seconds() if shown_at and captured else None
            if latency is not None and latency < 0:
                excluded['invalid_display_timestamp'] += 1
                latency = None
            budget = .25 if domain == 'shop' and summary.get('phase') == 'roll_down' else budgets.get(domain)
            rows.append({'game_id': batch.game_id, 'domain': domain or 'unknown',
                'too_late': int(too_late), 'latency': latency, 'budget': budget})
    if not rows:
        excluded['no_delivery_observations'] += 1
    return rows, excluded


def aggregate_deliveries(games):
    rows, exclusions = [], Counter()
    for values, excluded in games:
        rows.extend(values)
        exclusions.update(excluded)
    domains = {}
    for domain in sorted({row['domain'] for row in rows}):
        selected = [row for row in rows if row['domain'] == domain]
        observed = [row for row in selected if row['latency'] is not None and row['budget'] is not None]
        domains[domain] = {'too_late_share': aggregate((row['game_id'], row['too_late']) for row in selected),
            'capture_to_show_seconds': aggregate((row['game_id'], row['latency']) for row in observed),
            'capture_to_show_over_budget_share': aggregate((row['game_id'], int(row['latency'] > row['budget'])) for row in observed),
            'missing_display_observations': len(selected)-len(observed),
            'end_to_end_late_share': None, 'reason': 'game_change_timestamp_not_logged'}
    return {'by_kind': domains, 'excluded': dict(exclusions),
        'timing_scope': 'capture-to-display proxy; game-change-to-display truth is unavailable'}


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
    eligible, changed, exclusions, examples, differences, shares = 0, 0, Counter(), [], [], []
    for game in harness._games():
        if selected is not None and game['game_id'] not in selected:
            continue
        original_batch, candidate_batch = accepted.produce(game['game_id']), proposed.produce(game['game_id'])
        original_seeds = {context.log_seq: context.seed for context in original_batch.contexts}
        if original_seeds != {context.log_seq: context.seed for context in candidate_batch.contexts}:
            raise ValueError('Candidate cannot preserve original replay seeds; advice diff unavailable')
        old, new = _decisions(original_batch), _decisions(candidate_batch)
        game_eligible, game_changed = 0, 0
        for key in old.keys() | new.keys():
            if key not in old or key not in new:
                exclusions['unpaired_decision'] += 1
                continue
            before, after = old[key], new[key]
            eligible += 1
            game_eligible += 1
            if _choice(before) == _choice(after):
                continue
            changed += 1
            game_changed += 1
            difference = None if before.expected_placement is None or after.expected_placement is None else (
                after.expected_placement-before.expected_placement)
            if difference is not None:
                differences.append((game['game_id'], difference))
            if game['review_locked']:
                continue
            examples.append({'game_id': game['game_id'], 'log_seq': key[0], 'decision': key[1],
                'occurrence': key[2], 'accepted_choice': str(before.advice.get('option_id') or before.advice.get('action') or '')[:256],
                'accepted_recommendation': _summary(before),
                'candidate_choice': str(after.advice.get('option_id') or after.advice.get('action') or '')[:256],
                'candidate_recommendation': _summary(after),
                'expected_placement_difference': difference})
        if game_eligible:
            shares.append((game['game_id'], game_changed/game_eligible))
    examples.sort(key=lambda row: (row['expected_placement_difference'] is None,
        -abs(row['expected_placement_difference'] or 0), int(row['game_id']), row['log_seq'],
        row['decision'], row['occurrence']))
    return frozen_json({'status': 'report_only', 'eligible_decisions': eligible,
        'changed_decisions': changed, 'changed_share': changed/eligible if eligible else None,
        'game_weighted_changed_share': mean_by_game(shares),
        'expected_placement_difference': aggregate(differences),
        'reason': None if eligible else 'no_paired_decisions', 'excluded': dict(exclusions),
        'largest_changes': examples[:limit], 'candidate_id': overlay.identity,
        'reference': 'historical immutable tunables; original log points and seeds'})
