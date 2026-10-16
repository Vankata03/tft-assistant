"""Observed choice attribution uses later actions, never later valuation inputs."""
from datetime import datetime
from dataclasses import replace
from math import isfinite, sqrt
from statistics import stdev

from .attribution import DisplayLog, follow_rate, shown_status
from .identity import digest
from .report import ReviewReport
from .sections import sections, surface_sections
from .observed_line import value_observed_line
from tft_data import DataError

_PICK_EVENTS = {'augment': 'augment_pick', 'item': 'item_pick', 'carousel': 'carousel_pick',
    'wisp': 'wisp_purchase', 'shop': 'purchase'}
_IDENTITIES = {'augment': ('slot', 'augment_id'), 'item': ('slot', 'item_id'),
    'carousel': ('slot', 'unit_id', 'item_id'), 'wisp': ('slot', 'wisp_id'), 'shop': ('slot', 'unit_id')}


def selected_option(record):
    selected = next((option for option in record.options
        if option['option_id'] == record.advice['option_id']), None)
    if selected is None and record.decision in {'transition', 'positioning', 'shop'} and record.advice.get('option_id'):
        selected = {'option_id': record.advice['option_id'], 'action': record.decision,
            'payload': dict(record.advice.get('payload', {})), 'expected_placement': None,
            'standard_error': None, 'reason': record.advice['reason']}
    return selected


def board_identity(board, *, positions=False):
    return sorted((unit['unit_id'], unit.get('stars', 1), tuple(sorted(unit.get('items', ()))),
        unit.get('position') if positions else None) for unit in board.get('units', ()))


def observed_board_call(record, batch):
    context = next(c for c in batch.contexts if c.log_seq == record.log_seq)
    later = [r.log_seq for r in batch.records if r.decision == record.decision and r.log_seq > record.log_seq]
    stop = min(later, default=float('inf'))
    # The next decision snapshot is also the observation of the previous action.
    candidates = [c for c in batch.contexts if record.log_seq < c.log_seq <= stop
        and c.snapshot['round_id'] == context.snapshot['round_id']]
    if record.decision == 'positioning':
        fight = next((e for e in batch.observations if e['kind'] == 'fight_start'
            and e['seq'] > record.log_seq and e['payload'].get('round_id') == context.snapshot['round_id']), None)
        if fight is None:
            return None, 'prefight_board_unavailable'
        candidates = [c for c in batch.contexts if record.log_seq <= c.log_seq < fight['seq']
            and c.snapshot['round_id'] == context.snapshot['round_id']]
    for observed in reversed(candidates):
        if any(e['kind'] in {'capture_gap', 'tracking_ambiguity', 'board_read_disagreement'}
                and record.log_seq < e['seq'] <= observed.log_seq for e in batch.observations):
            return None, 'capture_gap_prevents_action_attribution'
        field = observed.snapshot['fields'].get('comp_lock' if record.decision == 'pivot' else 'board')
        if not field or field['read_at'] != observed.timestamp:
            continue
        value = field['value']
        if record.decision == 'pivot':
            before = context.snapshot['fields'].get('comp_lock', {}).get('value')
            if value == before or not value:
                continue
            option = next((o for o in record.options if o['payload'].get('comp_id') == value), None)
            if option is None:
                return None, 'observed_comp_not_scored'
        else:
            selected = selected_option(record)
            payload = record.advice.get('payload', {})
            if record.decision == 'positioning':
                layout = payload.get('layout', ())
                units = value.get('units', ())
                if not layout:
                    return None, 'layout_unavailable'
                followed = all(isinstance(row.get('unit_index'), int)
                    and 0 <= row['unit_index'] < len(units)
                    and units[row['unit_index']]['unit_id'] == row.get('unit_id')
                    and units[row['unit_index']].get('position') == row.get('cell') for row in layout)
            elif payload.get('board'):
                followed = board_identity(value) == board_identity(payload['board'])
            else:
                return None, 'transition_operation_not_observable'
            if selected is None:
                return None, 'engine_choice_unavailable'
            option = dict(selected) if followed else dict(selected) | {
                'option_id': 'observed-board:'+digest(value), 'payload': {'board': value},
                'expected_placement': None, 'standard_error': None}
        return dict(option) | {'observed_at': observed.timestamp, 'observed_log_seq': observed.log_seq,
            'evidence': 'fresh_captured_comp_lock' if record.decision == 'pivot' else 'fresh_captured_board'}, None
    return None, 'confirmed_action_unavailable'


def observed_option(record, batch):
    if record.decision in {'transition', 'pivot', 'positioning'}:
        return observed_board_call(record, batch)
    kind = _PICK_EVENTS.get(record.decision)
    if kind is None:
        return None, 'player_policy_not_identified'
    context = next(context for context in batch.contexts if context.log_seq == record.log_seq)
    later = [other.log_seq for other in batch.records
        if other.decision == record.decision and other.log_seq > record.log_seq]
    stop = min(later, default=float('inf'))
    candidates, purchases = [], []
    for event in batch.observations:
        if (record.log_seq < event['seq'] < stop and event['kind'] == kind
            and datetime.fromisoformat(event['timestamp']) >= datetime.fromisoformat(context.timestamp)
            and (event['payload'].get('evidence') or kind in {'purchase', 'wisp_purchase'})):
            purchases.append(event)
            keys = _IDENTITIES[record.decision]
            matches = [option for option in record.options
                if option['action'] in ('pick', 'buy')
                and all(key in option['payload'] and key in event['payload']
                    and option['payload'][key] == event['payload'][key] for key in keys)]
            if len(matches) == 1:
                candidates.append((matches[0], event))
    if record.decision == 'shop' and record.advice.get('payload', {}).get('buys') and purchases:
        buys = [dict(event['payload']) for event in purchases]
        identity = lambda rows: sorted((row['slot'], row['unit_id']) for row in rows)
        followed = identity(buys) == identity(record.advice['payload']['buys'])
        latest = max(purchases, key=lambda event: event['seq'])
        return {'option_id': record.advice['option_id'] if followed else 'observed-shop:'+digest(buys),
            'action': 'shop', 'payload': {'buys': buys}, 'expected_placement': None, 'standard_error': None,
            'observed_at': latest['timestamp'], 'observed_log_seq': latest['seq'],
            'evidence': 'confirmed_purchase_events'}, None
    if len(candidates) != 1:
        return None, 'confirmed_choice_unavailable_or_ambiguous'
    option, event = candidates[0]
    return dict(option) | {'observed_log_seq': event['seq'],
        'observed_at': event['timestamp'], 'evidence': event['payload'].get('evidence', kind)}, None


def decision_segment(batch, record):
    """Snapshots and time interval until the next replayed point of the same decision."""
    later = [other.log_seq for other in batch.records
        if other.decision == record.decision and other.log_seq > record.log_seq]
    stop = min(later, default=None)
    contexts = [context for context in batch.contexts if context.log_seq >= record.log_seq
        and (stop is None or context.log_seq < stop)]
    start = datetime.fromisoformat(contexts[0].timestamp)
    end = next((datetime.fromisoformat(context.timestamp) for context in batch.contexts
        if context.log_seq == stop), None)
    return {context.snapshot['snapshot_id'] for context in contexts}, (start, end)


def mode_at(batch, seq):
    mode = batch.contexts[0].game_start['mode'] if batch.contexts else 'silent'
    for event in batch.observations:
        if event['seq'] > seq:
            break
        if event['kind'] == 'mode_change':
            mode = event['payload']['mode']
    return mode


def paired_uncertainty(selected, player, context):
    if selected is None or player is None:
        return None
    if selected['option_id'] == player['option_id']:
        return 0.0
    left, right = selected['payload'].get('after'), player['payload'].get('after')
    if not left or not right:
        return None
    if left.get('seed') != context.seed or right.get('seed') != context.seed:
        return None
    left, right = left.get('rollout_placements'), right.get('rollout_placements')
    if not left or not right or len(left) != len(right) or len(left) < 2:
        return None
    if any(type(value) not in (int, float) or not isfinite(value) for value in (*left, *right)):
        return None
    return stdev([a-b for a, b in zip(left, right)]) / sqrt(len(left))


def deviation_choice(choice):
    """Stable action meaning, excluding ids, valuation noise and observation clocks."""
    if choice is None:
        return None
    payload = choice['payload']
    keys = ('operation', 'augment_id', 'item_id', 'unit_id', 'wisp_id', 'slot',
        'comp_id', 'target', 'from', 'swap_in', 'swap_out', 'sell', 'hold', 'holder',
        'component', 'recipe', 'levels', 'rolls')
    meaning = {key: payload[key] for key in keys if key in payload}
    if choice['action'] == 'line':
        meaning = {key: sorted(payload.get(key, {}).values()) for key in ('levels', 'rolls')}
    if not meaning:
        return (choice['action'], choice['option_id'])
    return (choice['action'], digest(meaning))


def group_moments(points):
    groups, previous = [], {}
    for point in points:
        if point['category'] == 'positioning':
            continue
        signature = (point['category'],
            deviation_choice(point['engine_choice']), deviation_choice(point['player_choice']),
            point['shown']['status'])
        prior = previous.get(point['category'])
        if (point['differed'] and prior is not None and prior[0] == signature
            and prior[1]['differed'] and point['cost'] is not None and prior[1]['cost'] is not None):
            group = prior[1]
            group['members'].append(point['moment_id'])
            group['cost'] += point['cost']
            group['close_call'] = group['close_call'] and point['close_call']
            group['paired_uncertainty'] = None
            group['unavailable'] = dict(group['unavailable']) | {
                'paired_uncertainty': 'cross_decision_covariance_unavailable'}
            group['last_round_id'] = point['round_id']
        else:
            group = dict(point) | {'members': [point['moment_id']]}
            groups.append(group)
        previous[point['category']] = (signature, group)
    return groups


class ReviewPolicy:
    def __init__(self, *, min_cost):
        if type(min_cost) not in (int, float) or not isfinite(min_cost) or min_cost < 0:
            raise ValueError('Review cost floor must be finite and nonnegative')
        self.min_cost = float(min_cost)

    def build(self, batch, *, data=None):
        timeline, moments, category_costs, attributed, policies = [], [], {}, [], {}
        display = DisplayLog(batch.observations)
        for record in batch.records:
            context = next(context for context in batch.contexts if context.log_seq == record.log_seq)
            segment, window = decision_segment(batch, record)
            selected = selected_option(record)
            player, reason = observed_option(record, batch)
            if record.decision == 'econ' and data is not None and selected is not None:
                try:
                    player, original = value_observed_line(batch,context,data)
                    best = min(context.evaluation['line_results'].get(context.evaluation['plan']['target'], ()),
                        key=lambda row: (row['expected_placement'], row['line']['id']), default=original)
                    best_option = next((option for option in record.options if option['option_id'] == best['line']['id']), selected)
                    selected = dict(best_option)|{'payload':dict(best_option['payload'])|{'after':best}}
                    observed_end = player['payload']['observed_through_seq']
                    horizon = [row for row in batch.contexts if context.log_seq <= row.log_seq <= observed_end]
                    player = dict(player)|{'observed_at': horizon[-1].timestamp,
                        'payload': dict(player['payload'])|{'horizon_rounds': sorted({row.snapshot['round_id'] for row in horizon}),
                            'initial_level': context.snapshot['fields']['level']['value']}}
                    reason = None
                    policies[context.log_seq] = player
                except (DataError,KeyError,ValueError,TypeError) as error:
                    player,reason = None,str(error)
            cost = None
            if player is not None and selected is not None:
                expected, actual = selected['expected_placement'], player['expected_placement']
                if expected is not None and actual is not None:
                    cost = expected-actual
            uncertainty = paired_uncertainty(selected, player, context)
            close_call = cost is not None and max(0, -cost) < max(self.min_cost, uncertainty or 0)
            shown = shown_status(display, record, mode=mode_at(batch, record.log_seq), window=window,
                segment_snapshots=segment, player=player, cost=cost, close_call=close_call)
            unavailable = {} if uncertainty is not None else {'paired_uncertainty': 'paired_rollouts_unavailable'}
            if reason:
                unavailable['player_choice'] = reason
            if cost is None:
                unavailable['cost'] = 'player_choice_unavailable' if player is None else 'domain_does_not_value_placement'
            row = {'moment_id': digest([batch.game_id, record.log_seq, record.decision, record.decision_id]),
                'engine_decision_id': record.decision_id, 'log_seq': record.log_seq,
                'round_id': context.snapshot['round_id'], 'category': record.decision,
                'player_choice': player, 'engine_choice': selected, 'cost': cost,
                'paired_uncertainty': uncertainty, 'close_call': close_call,
                'differed': player is not None and selected is not None and player['option_id'] != selected['option_id'],
                'shown': shown, 'reason': record.advice['reason'], 'unavailable': unavailable,
                'evidence_path': ['evidence', 'replay', 'records', batch.records.index(record)]}
            options = record.options
            if player is not None and player['action'] == 'line' and not any(option['option_id'] == player['option_id'] for option in options):
                options = options+(player,)
            attributed.append(replace(record, observed_choice=player, cost=cost, options=options,
                paired_uncertainty=uncertainty, shown=shown, unavailable=unavailable))
            timeline.append(row)
            if record.decision != 'positioning':
                moments.append(row)
                if cost is not None:
                    category_costs[record.decision] = category_costs.get(record.decision, 0) + cost
        moments = group_moments(timeline)
        harmful = sorted((row for row in moments if row['cost'] is not None
            and row['cost'] < 0 and not row['close_call']), key=lambda row: (row['cost'], row['log_seq']))
        differed = [row for row in moments if row['cost'] is None and row['differed']]
        end = next((event for event in reversed(batch.observations) if event['kind'] == 'game_end'), None)
        placement = end['payload'].get('placement') if end else None
        summary = {'placement': {'value': placement, 'reason': None if placement is not None else 'final_placement_unavailable'},
            'category_costs': {kind: {'value': value, 'reason': None, 'label': 'estimated_signed_cost'}
                for kind, value in category_costs.items()},
            'follow_rate': follow_rate([row['shown'] for row in timeline]),
            'top5': (harmful+differed)[:5]}
        detail = sections(batch, data, policies=policies, timeline=timeline)
        return ReviewReport(batch.game_id, summary, tuple(timeline), tuple(moments),
            {'replay': replace(batch, records=tuple(attributed)).to_dict()},
            surface=surface_sections(detail, timeline), **detail)
