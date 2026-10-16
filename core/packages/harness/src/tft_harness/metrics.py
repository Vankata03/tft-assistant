"""Causal prediction rows with explicit outcome eligibility and source pins."""
from collections import Counter
from math import isfinite

from tft_data import DataError
from tft_engine.lobby import alive_lobby
from tft_engine.planning import observed_phase, read, required


# Report-only diagnostics never become fitted gates merely by adding a metric.
FITTED_METRICS = ('fight_brier', 'fight_log_loss', 'damage_mae',
    'next_sighting_log_loss', 'expected_placement_mae', 'hit_log_loss')
LINE_METRICS = ('line_gold_mae', 'line_level_mae', 'line_hp_mae')
REPORT_METRICS = LINE_METRICS+('opponent_board_brier',)


def number(value):
    return type(value) in (int, float) and isfinite(value)


def placement_truth(batch, outcome=None):
    """The log's own placement first; validated late match truth only fills its absence."""
    ends = [event for event in batch.observations if event['kind'] == 'game_end']
    value = ends[-1]['payload'].get('placement') if ends else None
    if type(value) is int and 1 <= value <= 8:
        return value, 'game_end'
    # Storage rejects outcomes that conflict with a logged placement.
    if outcome is not None:
        return outcome['placement'], 'riot_match'
    return None, None


def selected_line(context):
    # simulate_lines requires these inputs, including required()'s completeness
    # certificates. Capture's explicit stale markers can invalidate even young
    # reads; every metric consuming this selected prediction must honor them.
    required_fields = ('board', 'bench', 'inventory_complete', 'gold', 'hp', 'level',
        'xp', 'streak', 'lobby', 'lobby_complete')
    for field in required_fields:
        if f'stale_field:{field}' in context.unavailable:
            raise DataError(f'stale_origin_required_field:{field}')
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


def placement_rows(batch, data, *, partial, outcome=None):
    rows, excluded = [], Counter()
    metric = 'expected_placement_mae'
    truth, source = placement_truth(batch, outcome)
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
            excluded.update((metric, str(error)) for metric in LINE_METRICS)
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


def unit_key(unit_id, data):
    from tft_engine.shop_math import canonical_id
    return canonical_id(unit_id, data) if unit_id in data.entities else unit_id


def final_unit_ids(outcome, data, participant_id=None):
    """Canonical unit identities on one participant's validated final match board."""
    participant_id = outcome['owner_id'] if participant_id is None else participant_id
    row = next(row for row in outcome['participants'] if row['participant_id'] == participant_id)
    return {unit_key(unit['character_id'], data) for unit in row['units']}


def opponent_final_joins(batch, data, outcome):
    """Join scouted opponents to match participants only by a uniquely observed elimination.

    Match participants carry no captured display identity. A certified complete
    lobby that loses exactly one opponent between consecutive observations
    fixes that opponent's placement; anything else stays unjoined.
    """
    from datetime import datetime

    lobbies = []
    for context in batch.contexts:
        if 'capture_gap' in context.unavailable or 'stale_field:lobby' in context.unavailable:
            continue
        try:
            alive = frozenset(alive_lobby(batch.snapshot_for(context), data))
        except (DataError, KeyError, TypeError, ValueError):
            continue
        lobbies.append((context, alive))
    calendar = {round_id: index for index, round_id in enumerate(data.static['round_order'].value)}

    def death_rounds(index):
        """Calendar rounds whose combat could hold a loss between two certified lobbies."""
        (before, _), (after, _) = lobbies[index], lobbies[index+1]
        start, end = (calendar.get(context.snapshot['round_id']) for context in (before, after))
        if start is None or end is None or end < start:
            return None
        # A planning witness of a later round precedes that round's combat.
        if end > start and observed_phase(batch.snapshot_for(after), data) in ('planning', 'roll_down'):
            end -= 1
        return set(range(start, end+1))

    windows = {index: death_rounds(index) for index in range(len(lobbies)-1)
        if lobbies[index][1]-lobbies[index+1][1]}
    stage_of = {index: round_id.split('-')[0] for round_id, index in calendar.items()}
    by_placement = {row['placement']: row for row in outcome['participants']}
    sighted = dict.fromkeys(event['payload']['opponent_id'] for event in batch.observations
        if event['kind'] == 'sighting')
    joins, excluded = {}, Counter()
    for opponent in sighted:
        seen = [index for index, (_, alive) in enumerate(lobbies) if opponent in alive]
        if not seen:
            excluded['opponent_never_certified_alive'] += 1
            continue
        last = seen[-1]
        if last+1 >= len(lobbies):
            excluded['opponent_outlived_capture'] += 1
            continue
        (before, alive), (after, remaining) = lobbies[last], lobbies[last+1]
        if remaining != alive-{opponent}:
            excluded['elimination_order_not_unique'] += 1
            continue
        rounds = windows[last]
        if not rounds or len({stage_of[index] for index in rounds}) != 1:
            excluded['last_stage_alive_ambiguous'] += 1
            continue
        # Capture order inside one round does not prove Riot's within-round
        # placement, so any other loss that may share the round blocks the join.
        if any(index != last and (other is None or other & rounds) for index, other in windows.items()):
            excluded['same_round_elimination_order_ambiguous'] += 1
            continue
        # The owner and every certified opponent were alive just before.
        placement = len(alive)+1
        if outcome['placement'] >= placement or placement not in by_placement:
            excluded['elimination_join_conflicts_with_outcome'] += 1
            continue
        final_round = by_placement[placement].get('last_round')
        if final_round is not None and any(row.get('last_round') == final_round
                for row in outcome['participants'] if row['placement'] not in (1, placement)):
            excluded['same_round_elimination_order_ambiguous'] += 1
            continue
        stage = stage_of[min(rounds)]
        until = datetime.fromisoformat(after.snapshot['captured_at'])
        scouted = [event for event in batch.observations if event['kind'] == 'sighting'
            and event['payload']['opponent_id'] == opponent and event['seq'] < after.log_seq
            and str(event['payload'].get('round_id', '')).split('-')[0] == stage
            and datetime.fromisoformat(event['timestamp']) <= until]
        if not scouted:
            excluded['not_scouted_in_last_stage_alive'] += 1
            continue
        joins[opponent] = {'participant': by_placement[placement], 'placement': placement,
            'sighting': scouted[-1], 'context': before}
    return joins, excluded


def infer_from_history(batch, data, opponent, sighting):
    """Chain trait inference over every causal sighting of one opponent."""
    from tft_engine.opponents import infer_opponent
    from tft_review.contracts import history_prefix

    inferred = None
    history = history_prefix(batch.observations, through_seq=sighting['seq'], captured_at=sighting['timestamp'])
    for row in history.sightings:
        if row.opponent_id == opponent:
            inferred = infer_opponent(row, data, previous=inferred)
            if inferred.fallback_reason:
                raise DataError('opponent_inference_unavailable')
    if inferred is None:
        raise DataError('opponent_inference_unavailable')
    return inferred


def opponent_board_rows(batch, data, outcome):
    """Report-only Brier score of inferred unit presence against the joined final board."""
    metric = 'opponent_board_brier'
    rows, excluded = [], Counter()
    if outcome is None:
        excluded[(metric, 'match_outcome_unavailable')] += 1
        return rows, excluded
    joins, reasons = opponent_final_joins(batch, data, outcome)
    excluded.update({(metric, reason): count for reason, count in reasons.items()})
    for opponent, join in joins.items():
        try:
            inferred = infer_from_history(batch, data, opponent, join['sighting'])
        except (DataError, KeyError, ValueError, TypeError) as error:
            excluded[(metric, str(error))] += 1
            continue
        predicted = Counter()
        for unit_id, probability in inferred.probabilities.items():
            predicted[unit_key(unit_id, data)] += probability
        final = final_unit_ids(outcome, data, join['participant']['participant_id'])
        universe = sorted(set(predicted) | final)
        loss = sum((min(1., predicted[unit])-(unit in final))**2 for unit in universe)/len(universe) if universe else 0.
        context = join['context']
        rows.append({'game_id': batch.game_id, 'log_seq': context.log_seq,
            'observation_seq': join['sighting']['seq'], 'stage': int(inferred.round_id.split('-')[0]),
            'metric': metric, 'prediction': dict(predicted), 'truth': tuple(sorted(final)), 'loss': loss,
            'naive_prediction': None, 'data_snapshot_id': data.snapshot_id, 'seed': context.seed,
            'opponent_id': opponent, 'final_placement': join['placement'],
            'sighting_round_id': inferred.round_id, 'join': 'unique_observed_elimination',
            'truth_source': 'riot_match'})
    return rows, excluded
