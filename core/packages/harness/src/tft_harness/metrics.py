"""Causal prediction rows with explicit outcome eligibility and source pins."""
from collections import Counter
from math import isfinite

from tft_data import DataError
from tft_engine.lobby import alive_lobby
from tft_engine.planning import read, required


# Report-only diagnostics never become fitted gates merely by adding a metric.
FITTED_METRICS = ('fight_brier', 'fight_log_loss', 'damage_mae',
    'next_sighting_log_loss', 'expected_placement_mae', 'hit_log_loss')
REPORT_METRICS = ('line_gold_mae', 'line_level_mae', 'line_hp_mae')


def number(value):
    return type(value) in (int, float) and isfinite(value)


def placement_truth(batch):
    ends = [event for event in batch.observations if event['kind'] == 'game_end']
    value = ends[-1]['payload'].get('placement') if ends else None
    return (value, 'game_end') if type(value) is int and 1 <= value <= 8 else (None, None)


def selected_line(context):
    result = context.evaluation
    if not result or not result.get('plan', {}).get('line'):
        raise DataError('selected_line_unavailable')
    plan = result['plan']
    selected = next((row for row in result['line_results'].get(plan['target'], ())
        if row['line']['id'] == plan['line']['id']), None)
    if selected is None:
        raise DataError('selected_line_unavailable')
    return selected


def prediction_row(batch, context, data, metric, prediction, truth, *, naive=None, **extra):
    return {'game_id': batch.game_id, 'log_seq': context.log_seq,
        'observation_seq': context.log_seq, 'stage': int(context.snapshot['round_id'].split('-')[0]),
        'metric': metric, 'prediction': prediction, 'truth': truth, 'loss': abs(prediction-truth),
        'naive_prediction': naive, 'data_snapshot_id': data.snapshot_id, 'seed': context.seed, **extra}


def placement_rows(batch, data, *, partial):
    rows, excluded = [], Counter()
    metric = 'expected_placement_mae'
    truth, source = placement_truth(batch)
    for context in batch.contexts:
        if 'semantic_duplicate' in context.unavailable:
            continue
        try:
            if 'capture_gap' in context.unavailable:
                raise DataError('capture_gap')
            if partial:
                raise DataError('partial_game_over_25_percent_gaps')
            if truth is None:
                raise DataError('terminal_placement_unavailable')
            snapshot = batch.snapshot_for(context)
            try:
                opponents = alive_lobby(snapshot, data)
                hp = read(snapshot, data, 'hp')
                stale = {reason.removeprefix('stale_field:') for reason in context.unavailable
                    if reason.startswith('stale_field:')}
                if (stale.intersection(('hp', 'lobby', 'lobby_complete')) or required(snapshot, data, ('hp',))
                    or not number(hp) or hp <= 0 or snapshot.fields['hp'].confidence <= 0):
                    raise DataError('own_hp_unavailable')
            except (DataError, KeyError, TypeError, ValueError):
                raise DataError('fresh_complete_hp_rank_unavailable') from None
            prediction = selected_line(context)['expected_placement']
            if not number(prediction):
                raise DataError('expected_placement_unavailable')
            # Average tied ranks avoids imposing an unobserved tie breaker.
            rank = 1+sum(value > hp for value in opponents.values())+.5*sum(value == hp for value in opponents.values())
            rows.append(prediction_row(batch, context, data, metric, prediction, truth,
                naive=rank, truth_source=source))
        except (DataError, KeyError, ValueError, TypeError) as error:
            excluded[(metric, str(error))] += 1
    return rows, excluded


def horizon_observation(batch, context, selected, data):
    """Projections include round rewards; truth is the next planning opening."""
    from datetime import datetime

    projection = selected['projections'][-1]
    order = tuple(data.static['round_order'].value)
    index = order.index(projection['round_id'])+1
    if index >= len(order):
        raise DataError('horizon_successor_unavailable')
    targets = [row for row in batch.contexts if row.log_seq > context.log_seq
        and row.snapshot['round_id'] == order[index]
        and datetime.fromisoformat(row.snapshot['captured_at']) > datetime.fromisoformat(context.snapshot['captured_at'])]
    if not targets:
        raise DataError('horizon_observation_unavailable_or_censored')
    # The first observation is the only possible opening witness. Never use a
    # later, richer board after the player has already acted in that phase.
    target = targets[0]
    start, end = map(datetime.fromisoformat, (context.snapshot['captured_at'], target.snapshot['captured_at']))
    if any(event['kind'] == 'capture_gap'
        and datetime.fromisoformat(event['payload']['end']) > start
        and (event['payload']['start'] is None or datetime.fromisoformat(event['payload']['start']) < end)
        for event in batch.observations):
        raise DataError('horizon_crosses_capture_gap')
    state = batch.snapshot_for(target)
    if read(state, data, 'planning_phase') is not True:
        raise DataError('horizon_opening_not_observed')
    intervening = [event for event in batch.observations
        if context.log_seq < event['seq'] < target.log_seq and event['kind'] in {
            'roll', 'level_up', 'purchase', 'shop_buy', 'shop_purchase', 'sell'}
        and event['timestamp'] >= target.snapshot['captured_at']]
    if intervening:
        raise DataError('horizon_opening_already_acted')
    return projection, target, state


def line_rows(batch, data):
    rows, excluded = [], Counter()
    for context in batch.contexts:
        if 'semantic_duplicate' in context.unavailable:
            continue
        try:
            if 'capture_gap' in context.unavailable:
                raise DataError('capture_gap')
            selected = selected_line(context)
            projection, target, state = horizon_observation(batch, context, selected, data)
        except (DataError, KeyError, ValueError, TypeError, IndexError) as error:
            excluded.update((metric, str(error)) for metric in REPORT_METRICS)
            continue
        # This is an observed residual, not a counterfactual accuracy claim.
        # A delivered recommendation alone cannot prove an entire future policy.
        for field in ('gold', 'level', 'hp'):
            metric = f'line_{field}_mae'
            truth = read(state, data, field)
            if (f'stale_field:{field}' in target.unavailable or not number(truth)
                or not number(projection.get(field))):
                excluded[(metric, 'fresh_horizon_field_unavailable')] += 1
                continue
            rows.append(prediction_row(batch, context, data, metric, projection[field], truth,
                residual=projection[field]-truth, horizon_round_id=projection['round_id'],
                truth_round_id=state.round_id, truth_log_seq=target.log_seq,
                policy_status='unconfirmed', policy_reason='whole_horizon_policy_not_confirmed',
                interpretation='observed_residual_not_counterfactual_truth'))
    return rows, excluded


def hit_rows(batch, data):
    """Score identifiable fixed-level, single-goal natural shops; never invent a paid-roll stop."""
    from math import log
    from tft_engine.shop_math import canonical_id, hit_probability, key_goals, owned_copies
    from tft_engine.planning import owned_board
    from tft_engine.opponents import opponents_from_history
    from tft_review.observed_line import observed_line

    rows, excluded = [], Counter()
    for context in batch.contexts:
        if 'semantic_duplicate' in context.unavailable:
            continue
        snapshot = batch.snapshot_for(context)
        target = (context.evaluation or {}).get('plan', {}).get('target')
        try:
            if 'capture_gap' in context.unavailable:
                raise DataError('capture_gap')
            if target is None or read(snapshot, data, 'comp_lock') != target:
                raise DataError('confirmed_player_goals_unavailable')
            selected = selected_line(context)
            projection, terminal, state = horizon_observation(batch, context, selected, data)
            interval = [event for event in batch.observations if context.log_seq < event['seq'] < terminal.log_seq]
            if any(event['kind'] == 'roll' for event in interval) or selected['line']['rolls']:
                raise DataError('paid_roll_stopping_policy_unidentifiable')
            actual, _ = observed_line(batch, context, data)
            if actual.rolls or actual.levels:
                raise DataError('fixed_level_shop_policy_unavailable')
            if required(snapshot, data, ('board', 'bench', 'shop', 'slot_count', 'level', 'gold')):
                raise DataError('initial_shop_chain_fields_unavailable')
            if required(state, data, ('board', 'bench', 'inventory_complete')):
                raise DataError('complete_horizon_ownership_unavailable')
            if any(event['kind'] in {'tracking_ambiguity', 'sell', 'unit_grant', 'wisp_purchase', 'carousel_pick'} for event in interval):
                raise DataError('shop_policy_has_unidentified_ownership_changes')
            if (read(snapshot, data, 'remaining_effects_complete') is not True
                or read(snapshot, data, 'remaining_effects') or read(snapshot, data, 'held_augments_complete') is not True
                or read(snapshot, data, 'held_augments')):
                raise DataError('shop_modifiers_not_qualified')
            goals = key_goals(data.guides[target], data)
            if len(goals) != 1:
                raise DataError('joint_goal_shop_chain_unavailable')
            unit, goal = next(iter(goals.items()))
            owned = owned_copies(owned_board(snapshot, data), data)
            needed = max(0, goal-owned.get(unit, 0))
            if needed and any(offer.get('unit_id') and canonical_id(offer['unit_id'], data) == unit
                for offer in read(snapshot, data, 'shop')):
                raise DataError('initial_offered_goal_requires_conditional_chain')
            level, slots = read(snapshot, data, 'level'), read(snapshot, data, 'slot_count')
            witnesses = [row for row in batch.contexts if context.log_seq <= row.log_seq <= terminal.log_seq]
            for witness in witnesses:
                captured = batch.snapshot_for(witness)
                if (read(captured, data, 'comp_lock') != target or read(captured, data, 'level') != level
                    or read(captured, data, 'slot_count') != slots):
                    raise DataError('goals_level_or_slots_changed_or_stale')
            if any(point['level'] != level for point in selected['projections']):
                raise DataError('changing_level_requires_nonstationary_shop_chain')
            horizon = tuple(point['round_id'] for point in selected['projections'])
            openings = []
            for round_id in horizon[1:]:
                seen = [row for row in witnesses if row.snapshot['round_id'] == round_id]
                if not seen:
                    raise DataError('natural_shop_observations_incomplete')
                opening = batch.snapshot_for(seen[0])
                offers = read(opening, data, 'shop')
                if offers is None or len(offers) != slots:
                    raise DataError('natural_shop_observations_incomplete')
                openings.extend(offer for offer in offers if offer.get('unit_id')
                    and canonical_id(offer['unit_id'], data) == unit)
            purchases = sum(event['payload'].get('copies', 0) for event in interval
                if event['kind'] == 'purchase' and canonical_id(event['payload']['unit_id'], data) == unit)
            if any(event['kind'] == 'purchase' and canonical_id(event['payload']['unit_id'], data) != unit for event in interval):
                raise DataError('off_goal_spending_requires_conditional_shop_chain')
            final = owned_copies(owned_board(state, data), data)
            if final.get(unit, 0) != owned.get(unit, 0)+purchases:
                raise DataError('goal_ownership_not_joined_to_purchases')
            if purchases < min(needed, len(openings)):
                raise DataError('offered_goal_not_bought_policy_unidentifiable')
            if read(snapshot, data, 'gold') < needed*data.entities[unit].cost:
                raise DataError('goal_purchase_affordability_unavailable')
            contested = Counter()
            for opponent in opponents_from_history(batch.history_for(context), snapshot.round_id, data,
                opponent_ids=tuple(alive_lobby(snapshot, data))):
                contested.update(opponent.expected_copies)
            naive = hit_probability(unit, needed, len(horizon)-1, slots, level, data,
                owned=owned, contested=contested)
            truth = int(final.get(unit, 0) >= goal)
            prediction = selected['hit_probability']
            probability = prediction if truth else 1-prediction
            row = prediction_row(batch, context, data, 'hit_log_loss', prediction, truth, naive=naive,
                policy_status='confirmed_no_paid_rolls', goals=goals, gold_floor=None,
                shops=len(horizon)-1, slots=slots, level=level, owned=owned, contested=dict(contested),
                horizon_round_id=projection['round_id'], truth_log_seq=terminal.log_seq,
                naive_source='tft_engine.shop_math.hit_probability')
            row['loss'] = -log(probability) if probability > 0 else None
            rows.append(row)
        except (DataError, KeyError, ValueError, TypeError, IndexError) as error:
            excluded[('hit_log_loss', str(error))] += 1
    return rows, excluded
