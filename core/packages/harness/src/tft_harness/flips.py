"""Paired A/B/A reversals, qualified by domain inputs and planning phases."""
from collections import Counter, defaultdict
from datetime import datetime

from tft_engine.planning import field_age, observed_phase
from tft_engine.registry import CORE_DEPENDENCY_FIELDS, default_hooks
from tft_review import ReplayProducer
from tft_review.contracts import frozen_json, json_value

from .diagnostics import _choice, _decisions
from .measurement import mean_by_game
from .overlay import TunableOverlay


def domain_fields(domain, hooks):
    if domain in ('econ', 'transition', 'pivot'):
        return tuple(dict.fromkeys(CORE_DEPENDENCY_FIELDS+tuple(name
            for hook in hooks for name in hook.fit_required_fields+hook.dependency_fields)))
    hook = next((hook for hook in hooks if hook.name == domain), None)
    if hook is None:
        return None
    return tuple(dict.fromkeys(hook.required_fields+hook.fit_required_fields+hook.dependency_fields
        +((hook.activation_field,) if hook.activation_field else ())))


def input_state(batch, context, data, names):
    snapshot = batch.snapshot_for(context)
    state = {}
    for name in names:
        field = snapshot.fields.get(name)
        state['field:'+name] = None if field is None else {
            'value': json_value(field.value), 'source': field.source, 'confidence': field.confidence,
            'fresh': (f'stale_field:{name}' not in context.unavailable
                and field.age_seconds(snapshot.captured_at) <= field_age(data, name, snapshot))}
    if 'board_settled_since' in names and snapshot.field('board_settled_since'):
        state['board_settled'] = (snapshot.captured_at-datetime.fromisoformat(
            snapshot.field('board_settled_since'))).total_seconds() >= data.tunables['board_settle_seconds'].value
    for kind in ('sighting', 'fight_result', 'fight_incomplete', 'capture_gap'):
        state['history:'+kind] = tuple(event['seq'] for event in batch.observations
            if event['seq'] <= context.prefix_through_seq and event['kind'] == kind
            and datetime.fromisoformat(event['timestamp']) <= snapshot.captured_at)
    return state


def measure_flips(batch, data, hooks, *, keys=None):
    contexts = {context.log_seq: context for context in batch.contexts}
    phases = {}
    # Calendar positions preserve elapsed phases even when capture missed a round.
    calendar = {round_id: index for index, round_id in enumerate(data.static['round_order'].value)}
    for context in batch.contexts:
        snapshot = batch.snapshot_for(context)
        if observed_phase(snapshot, data) in ('planning', 'roll_down'):
            if snapshot.round_id in calendar:
                phases[context.log_seq] = calendar[snapshot.round_id]
    result, trails, examples = {}, defaultdict(list), []
    for key, record in sorted(_decisions(batch).items()):
        domain, context = record.decision, contexts[record.log_seq]
        stats = result.setdefault(domain, {'eligible_decisions': 0, 'flips': 0,
            'explained_reversals': 0, 'excluded': Counter(), 'explanations': Counter()})
        fields = domain_fields(domain, hooks)
        reason = ('unpaired_decision' if keys is not None and key not in keys else
            'capture_gap' if 'capture_gap' in context.unavailable else
            'not_planning_phase' if context.log_seq not in phases else
            'paused_advice' if record.advice.get('payload', {}).get('paused') else
            'undeclared_domain_dependencies' if fields is None else None)
        if reason:
            stats['excluded'][reason] += 1
            trails[domain].clear()
            continue
        stats['eligible_decisions'] += 1
        current = {'key': key, 'phase': phases[context.log_seq], 'choice': _choice(record),
            'inputs': input_state(batch, context, data, fields)}
        trail = trails[domain]
        if trail and trail[-1]['choice'] == current['choice']:
            # Keep the newest A in A/A/B/A, but never count timer captures as phases.
            trail[-1] = current
            continue
        trail.append(current)
        if len(trail) < 3:
            continue
        left, middle, right = trail[-3:]
        if left['choice'] != right['choice'] or right['phase']-left['phase'] > 2:
            continue
        states = [input_state(batch, witness, data, fields) for witness in batch.contexts
            if left['key'][0] <= witness.log_seq <= right['key'][0]]
        changed = [name for name in left['inputs'] if any(state[name] != left['inputs'][name] for state in states)]
        if changed:
            stats['explained_reversals'] += 1
            stats['explanations'].update(changed)
        else:
            stats['flips'] += 1
            examples.append({'game_id': batch.game_id, 'decision': domain,
                'log_seqs': [point['key'][0] for point in (left, middle, right)]})
    return result, examples


def summarize_flips(rows):
    counts = Counter(flips=0, eligible_decisions=0, explained_reversals=0)
    excluded, explanations = Counter(), Counter()
    for _, stats in rows:
        counts.update({key: stats[key] for key in ('flips', 'eligible_decisions', 'explained_reversals')})
        excluded.update(stats['excluded'])
        explanations.update(stats['explanations'])
    return dict(counts)|{'rate': mean_by_game((game, stats['flips']/stats['eligible_decisions'])
        for game, stats in rows if stats['eligible_decisions']),
        'excluded': dict(excluded), 'explanations': dict(explanations)}


def flip_rates(harness, game_ids=None, *, candidate=None, limit=20):
    if type(limit) is not int or not 0 <= limit <= 100:
        raise ValueError('Flip example limit must be between zero and 100')
    games = harness._games(game_ids)
    accepted = ReplayProducer(harness.sessions, harness.data_store, repository=harness.repository,
        hooks=harness.hooks, decision_segmentation='semantic')
    overlay = TunableOverlay(harness.data_store, candidate) if candidate is not None else None
    proposed = ReplayProducer(harness.sessions, overlay, repository=harness.repository,
        hooks=harness.hooks, decision_segmentation='semantic', hook_version='flips:'+overlay.identity) if overlay else None
    hooks = default_hooks() if harness.hooks is None else tuple(harness.hooks)
    aggregates, examples = {}, []
    for game in games:
        before = accepted.produce(game['game_id'])
        after = proposed.produce(game['game_id']) if proposed else None
        keys = None
        if after is not None:
            if {row.log_seq: row.seed for row in before.contexts} != {row.log_seq: row.seed for row in after.contexts}:
                raise ValueError('Candidate cannot preserve original replay seeds; flip gate unavailable')
            keys = _decisions(before).keys() & _decisions(after).keys()
        old, private = measure_flips(before, harness.data_store.get(before.identity['data_snapshot_id']), hooks, keys=keys)
        new = measure_flips(after, overlay.get(after.identity['data_snapshot_id']), hooks, keys=keys)[0] if after else {}
        for domain in old.keys() | new.keys():
            aggregate = aggregates.setdefault(domain, {'old': [], 'new': []})
            for label, measured in (('old', old), ('new', new)):
                if domain in measured:
                    aggregate[label].append((game['game_id'], measured[domain]))
        if not game['review_locked']:
            examples.extend(private)
    domains = {}
    for domain, aggregate in aggregates.items():
        old, new = summarize_flips(aggregate['old']), summarize_flips(aggregate['new'])
        paired = {game: stats['eligible_decisions'] for game, stats in aggregate['old']} == {
            game: stats['eligible_decisions'] for game, stats in aggregate['new']}
        unpaired = any(stats['excluded'].get('unpaired_decision') for _, stats in aggregate['old']+aggregate['new'])
        comparable = proposed is not None and paired and not unpaired and old['rate'] is not None and new['rate'] is not None
        domains[domain] = old|{'candidate': new if proposed else None,
            'gate': {'status': ('pass' if new['rate'] <= old['rate'] else 'fail') if comparable else 'unavailable',
                'reason': None if comparable else 'unpaired_or_missing_eligible_decisions' if proposed else 'no_candidate'}}
    return frozen_json({'domains': domains, 'examples': examples[:limit],
        'weighting': 'equal games; reversals/eligible decisions within game',
        'window': 'three planning phases inclusive; timer captures do not advance phase',
        'target_share': .05, 'target_is_gate': False})
