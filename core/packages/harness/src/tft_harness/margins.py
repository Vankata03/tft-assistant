"""Offline family-2 margins from declared paired and model-gap uncertainty.

Guards are read from replayed Engine evidence in each target's own units:
placement guards pair two options or comps on the same seed tape (Lines,
Wisps, pivots, comp-defining leads, reviewed player choices); power and share
guards are exact Engine values (kept-board and shop power gaps, threat shares)
with no Monte Carlo term. Model error is the spread of each guard across
replays under family-1 parameter draws. This module does not fit models,
manufacture missing draws or publish accepted tunables; values go to a
candidate tunables file.
"""
from dataclasses import dataclass
from math import hypot, isfinite, sqrt, isclose
from statistics import stdev, covariance

from tft_data import DataError, TaggedValue
from tft_data.config import TUNABLE_FAMILIES

from .overlay import TunableOverlay

_GUARD_UNITS = {
    'pivot_margin_by_stage': 'placement', 'pivot_reraise_extra': 'placement',
    'transition_tolerance': 'power', 'line_margin': 'placement',
    'comp_defining_margin': 'placement', 'board_power_buy_min': 'power',
    'wisp_buy_margin': 'placement', 'threat_share_on': 'share',
    'threat_share_off': 'share', 'review_min_cost': 'placement',
}


def _finite_number(value):
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise DataError('Margin uncertainty requires finite numeric values')
        return float(value)
    except OverflowError as error:
        raise DataError('Margin value exceeds the supported numeric range') from error


@dataclass(frozen=True)
class MarginInput:
    target: str
    stage: str
    kind: str
    units: str
    floor: TaggedValue
    costly_or_sticky: bool
    rollout_differences: tuple[float, ...] | None
    model_gap_draws: tuple[float, ...] | None
    rollout_citation: str
    model_citation: str
    # Exact deterministic guards (board power, threat share) have no Monte
    # Carlo term; their standard error is the family-1 model spread alone.
    deterministic: bool = False
    # Components share a random prefix but may have different sample counts.
    rollout_components: tuple[tuple[float, ...], ...] | None = None

    def __post_init__(self):
        if not isinstance(self.target, str) or TUNABLE_FAMILIES.get(self.target) != '2':
            raise DataError('Margins accept known family-2 targets only')
        if self.units != _GUARD_UNITS[self.target]:
            raise DataError('Uncertainty must use the target guard units')
        for name in ('stage', 'kind'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DataError(f'Margin requires a declared {name}')
        if (not isinstance(self.floor, TaggedValue) or self.floor.family != '2'
            or not isinstance(self.floor.citation, str) or not self.floor.citation.strip()):
            raise DataError('Margin requires a sourced family-2 floor')
        if _finite_number(self.floor.value) < 0:
            raise DataError('Margin floor must be nonnegative')
        if type(self.costly_or_sticky) is not bool:
            raise DataError('Margin requires an explicit costly/sticky classification')
        if type(self.deterministic) is not bool or (self.deterministic and self.rollout_differences is not None):
            raise DataError('A deterministic guard has no rollout vector')
        if self.rollout_components is not None:
            if (self.deterministic or self.rollout_differences is not None
                    or not isinstance(self.rollout_components, (tuple, list))
                    or not 1 <= len(self.rollout_components) <= 2
                    or not isinstance(self.rollout_citation, str) or not self.rollout_citation.strip()):
                raise DataError('Conditional components require one or two sourced shared-prefix tapes')
            components = []
            for vector in self.rollout_components:
                if not isinstance(vector, (tuple, list)):
                    raise DataError('Conditional components require sample vectors')
                components.append(tuple(_finite_number(value) for value in vector))
            object.__setattr__(self, 'rollout_components', tuple(components))
        for name, citation_name in (('rollout_differences', 'rollout_citation'), ('model_gap_draws', 'model_citation')):
            values = getattr(self, name)
            citation = getattr(self, citation_name)
            if not isinstance(citation, str) or (values is not None and not citation.strip()):
                raise DataError(f'Margin requires {citation_name}')
            if values is not None:
                if not isinstance(values, (tuple, list)):
                    raise DataError('Margin uncertainty requires declared sample vectors')
                object.__setattr__(self, name, tuple(_finite_number(value) for value in values))


@dataclass(frozen=True)
class MarginEstimate:
    target: str
    stage: str
    kind: str
    units: str
    value: float
    z: int
    mc_standard_error: float | None
    model_standard_deviation: float | None
    reason: str | None
    citations: tuple[str, ...]


def estimate_margin(inputs: MarginInput) -> MarginEstimate:
    """Return an unaccepted per-kind/stage margin in the declared guard units."""
    z = 2 if inputs.costly_or_sticky else 1
    reason = None
    if inputs.deterministic:
        pass
    elif inputs.rollout_components is not None:
        if any(len(vector) < 2 for vector in inputs.rollout_components):
            reason = 'insufficient_paired_rollouts'
    elif inputs.rollout_differences is None:
        reason = 'paired_rollout_uncertainty_unavailable'
    elif len(inputs.rollout_differences) < 2:
        reason = 'insufficient_paired_rollouts'
    elif inputs.model_gap_draws is None:
        reason = 'model_gap_uncertainty_unavailable'
    elif len(inputs.model_gap_draws) < 2:
        reason = 'insufficient_model_gap_draws'
    if reason is None and inputs.model_gap_draws is None:
        reason = 'model_gap_uncertainty_unavailable'
    elif reason is None and len(inputs.model_gap_draws) < 2:
        reason = 'insufficient_model_gap_draws'
    if reason:
        return MarginEstimate(inputs.target, inputs.stage, inputs.kind, inputs.units,
            inputs.floor.value, z, None, None, reason,
            tuple(value for value in (inputs.floor.citation, inputs.rollout_citation, inputs.model_citation) if value))
    try:
        if inputs.deterministic:
            mc_error = 0.0
        elif inputs.rollout_components is not None:
            vectors = inputs.rollout_components
            variance = sum(stdev(vector)**2 / len(vector) for vector in vectors)
            if len(vectors) == 2:
                left, right = vectors
                overlap = min(len(left), len(right))
                variance += 2 * covariance(left[:overlap], right[:overlap]) * overlap / (len(left)*len(right))
            if variance < -1e-12:
                return MarginEstimate(inputs.target, inputs.stage, inputs.kind, inputs.units,
                    inputs.floor.value, z, None, None, 'invalid_conditional_variance_estimate',
                    (inputs.floor.citation, inputs.rollout_citation, inputs.model_citation))
            mc_error = sqrt(max(0.0, variance))
        else:
            mc_error = stdev(inputs.rollout_differences) / sqrt(len(inputs.rollout_differences))
        model_error = stdev(inputs.model_gap_draws)
        value = _finite_number(z * hypot(mc_error, model_error))
    except OverflowError as error:
        raise DataError('Margin uncertainty exceeds the supported numeric range') from error
    return MarginEstimate(inputs.target, inputs.stage, inputs.kind, inputs.units,
        max(inputs.floor.value, value), z,
        mc_error, model_error, None,
        (inputs.floor.citation, inputs.rollout_citation, inputs.model_citation))


@dataclass(frozen=True)
class PairedGuard:
    """One guarded difference at a replayed decision, in the target's units.

    ``differences`` is the per-rollout difference on the shared seed tape.
    A deterministic guard (board power, threat share) has no tape and carries
    its exact ``value``. Conditional Wisp guards carry one or two shared-prefix
    components plus their exact fitted mean. Missing tapes stay unavailable.
    """
    game_id: str
    log_seq: int
    occurrence: int
    decision_id: str
    kind: str
    stage: str
    best_option: str
    runner_up: str
    differences: tuple[float, ...] | None
    units: str = 'placement'
    value: float | None = None
    base_key: str | None = None
    components: tuple[tuple[float, ...], ...] | None = None
    line_ids: tuple[tuple[str, ...], tuple[str, ...]] | None = None
    fixed_board: object = None
    valuations: object = None

    def __post_init__(self):
        from tft_review.contracts import frozen_json
        for name in ('fixed_board', 'valuations'):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, frozen_json(getattr(self, name)))

    @property
    def key(self):
        # Decision ids digest the valuation; logged points and options pair draws.
        return (self.game_id, self.log_seq, self.kind, self.occurrence, self.best_option, self.runner_up)

    @property
    def deterministic(self):
        return self.differences is None and self.components is None and self.value is not None

    @property
    def mean(self):
        if self.components is not None:
            return self.value
        if self.differences:
            return sum(self.differences)/len(self.differences)
        return self.value


def _finite_vector(values):
    if not values or any(isinstance(value, bool) or not isinstance(value, (int, float))
                         or not isfinite(value) for value in values):
        return None
    return tuple(float(value) for value in values)


def _finite(value):
    return None if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) else float(value)


def _rollouts(option, seed):
    after = option.get('payload', {}).get('after')
    if not after or after.get('seed') != seed:
        return None
    return _finite_vector(after.get('rollout_placements'))


def _stage(round_id):
    return str(round_id).split('-')[0]


def _conditional_wisp(options, seed):
    """Retain integrated outcome and price estimators on their actual tapes.

    The price estimator may use fewer lanes. Its covariance with the integrated
    outcome estimator comes only from the shared prefix, not invented draws.
    """
    buys = [option for option in options.values() if option.get('action') == 'buy'
        and option.get('payload', {}).get('outcomes')]
    skips = [option for option in options.values() if option.get('action') == 'skip']
    if len(buys) != 1 or len(skips) != 1:
        return None
    buy, skip = buys[0], skips[0]
    payload = buy['payload']
    baseline = _rollouts(skip, seed)
    gain = _finite(payload.get('placement_gain'))
    if baseline is None or gain is None:
        return None
    vectors, probabilities = [], []
    for outcome in payload['outcomes']:
        probability = _finite(outcome.get('probability'))
        before, after = outcome.get('before', {}), outcome.get('after', {})
        left, right = _finite_vector(before.get('rollout_placements')), _finite_vector(after.get('rollout_placements'))
        if (probability is None or probability <= 0 or before.get('seed') != seed or after.get('seed') != seed
                or left != baseline or right is None or len(right) != len(baseline)):
            return None
        probabilities.append(probability)
        vectors.append(tuple(probability*(a-b) for a, b in zip(left, right)))
    if not vectors or not isclose(sum(probabilities), 1.0):
        return None
    components = [tuple(sum(row[index] for row in vectors) for index in range(len(baseline)))]
    pairing = payload.get('pairing')
    if pairing == 'conditional_outcomes_integrated_on_shared_tape_with_overlapping_gold_pair_covariance':
        price = payload.get('gold_pair', {})
        before, after = price.get('before', {}), price.get('after', {})
        left, right = _finite_vector(before.get('rollout_placements')), _finite_vector(after.get('rollout_placements'))
        if (before.get('seed') != seed or after.get('seed') != seed or left is None or right is None
                or len(left) != len(right) or len(left) > len(baseline) or left != baseline[:len(left)]):
            return None
        components.append(tuple(a-b for a, b in zip(left, right)))
    elif pairing != 'conditional_outcomes_with_price_on_shared_tape':
        return None
    # The Engine's exact fit terms can shift the mean without changing MC noise.
    return buy['option_id'], skip['option_id'], gain, tuple(components)


class GuardCollection(tuple):
    """Guard evidence retaining the replay needed to revalue fixed comparisons."""
    def __new__(cls, values, batches, data_store=None):
        result = super().__new__(cls, values)
        object.__setattr__(result, 'batches', tuple(batches))
        object.__setattr__(result, 'data_store', data_store)
        return result

    def __setattr__(self, name, value):
        raise AttributeError('Guard evidence is immutable')


def paired_guards(batches, *, kind, reference=None):
    """Paired placement differences (runner-up minus best) for one decision kind.

    The best option is the Engine's advised option; the runner-up is the other
    option with the lowest expected placement on the same seed tape. Decisions
    without two comparable same-seed rollout vectors are omitted.
    """
    if reference is not None:
        return fixed_guards(batches, reference)
    batches = tuple(batches)
    guards = []
    for batch in batches:
        rounds = {context.log_seq: context.snapshot['round_id'] for context in batch.contexts}
        occurrences = {}
        for record in batch.records:
            if record.decision != kind or record.log_seq not in rounds:
                continue
            occurrence = occurrences.get(record.log_seq, 0)
            occurrences[record.log_seq] = occurrence+1
            options = {option['option_id']: option for option in record.options}
            conditional = _conditional_wisp(options, record.seed) if kind == 'wisp' else None
            if conditional is not None:
                buy_id, skip_id, gain, components = conditional
                guards.append(PairedGuard(batch.game_id, record.log_seq, occurrence, record.decision_id,
                    kind, _stage(rounds[record.log_seq]), buy_id, skip_id, None,
                    value=gain, components=components))
                continue
            best = options.get(record.advice.get('option_id'))
            best_rollouts = _rollouts(best, record.seed) if best else None
            if best_rollouts is None:
                continue
            rivals = sorted(((option.get('expected_placement'), option_id, rollouts)
                for option_id, option in options.items() if option_id != best['option_id']
                for rollouts in (_rollouts(option, record.seed),)
                if rollouts is not None and len(rollouts) == len(best_rollouts)
                and isinstance(option.get('expected_placement'), (int, float))), key=lambda row: (row[0], row[1]))
            if not rivals:
                continue
            _, runner_up, rollouts = rivals[0]
            guards.append(PairedGuard(batch.game_id, record.log_seq, occurrence, record.decision_id, kind,
                _stage(rounds[record.log_seq]), best['option_id'], runner_up,
                tuple(other-chosen for other, chosen in zip(rollouts, best_rollouts)),
                valuations=_line_valuations(batch, record.log_seq, (best, options[runner_up])) if kind == 'econ' else None))
    return GuardCollection(guards, batches)


def _comp_tape(evaluation, comp_id, seed, line_ids=None):
    """Per-rollout comp fit score: the best Line's tape plus the exact domain terms."""
    fit = evaluation.get('comp_fits', {}).get(comp_id)
    rows = evaluation.get('line_results', {}).get(comp_id)
    if not fit or not fit.get('simulated') or not rows:
        return None
    # The Engine's simulation term is its first minimal expected-placement Line.
    leader = min(rows, key=lambda row: row['expected_placement'])
    candidates = rows if line_ids is None else [row for row in rows if row['line']['id'] in line_ids]
    if not candidates or (line_ids is not None and {row['line']['id'] for row in candidates} != set(line_ids)):
        return None
    best = min(candidates, key=lambda row: row['expected_placement'])
    tape = _finite_vector(best.get('rollout_placements')) if best.get('seed') == seed else None
    score, expected = _finite(fit.get('score')), _finite(leader.get('expected_placement'))
    if tape is None or score is None or expected is None:
        return None
    return tuple(value+score-expected for value in tape)


_PLAN_GUARDS = {'pivot': ('pivot', 'target', 'challenger'),
    'pivot_reraise': ('pivot', 'target', 'challenger'),
    'comp_defining': ('comp_defining', 'second', 'top')}


def plan_guards(batches, *, kind, reference=None):
    """Comp-fit differences the Game plan compared, from the Engine's own guard evidence.

    ``pivot`` is the committed target's score minus its challenger's, keyed by
    the pivot margin's stage or ``post_roll_down``; ``pivot_reraise`` is the
    same comparison against the rejected comp, keyed by stage with the pivot
    margin key as ``base_key``. ``comp_defining`` is the Open plan's runner-up
    minus its leader, only where the augment term decides commitment. Both comp
    tapes share the evaluation's seed, so domain terms cancel in the noise.
    """
    if reference is not None:
        return fixed_guards(batches, reference)
    name, left_name, right_name = _PLAN_GUARDS[kind]
    batches = tuple(batches)
    guards = []
    for batch in batches:
        for context in batch.contexts:
            evaluation = context.evaluation or {}
            guard = evaluation.get('guards', {}).get(name)
            if not guard or (name == 'pivot' and bool(guard['reraise']) != (kind == 'pivot_reraise')):
                continue
            left, right = guard[left_name], guard[right_name]
            left_tape, right_tape = (_comp_tape(evaluation, comp, context.seed) for comp in (left, right))
            stage = _stage(context.snapshot['round_id'])
            differences = (tuple(a-b for a, b in zip(left_tape, right_tape))
                if left_tape and right_tape and len(left_tape) == len(right_tape) else None)
            guards.append(PairedGuard(batch.game_id, context.log_seq, 0,
                f"{context.snapshot.get('snapshot_id')}:{kind}", kind,
                guard['margin_key'] if kind == 'pivot' else stage, left, right, differences,
                base_key=guard.get('margin_key') if kind == 'pivot_reraise' else None,
                line_ids=tuple(tuple(row['line']['id'] for row in evaluation['line_results'][comp])
                    for comp in (left, right)) if left_tape and right_tape else None,
                valuations=tuple({'comp_id': comp,
                    'lines': tuple(row['line'] for row in evaluation['line_results'][comp]),
                    'backup_id': evaluation.get('guards', {}).get('simulation_backups', {}).get(comp),
                    'domain': True, 'rollouts': len(left_tape)} for comp in (left, right)) if left_tape and right_tape else None))
    return GuardCollection(guards, batches)


def transition_guards(batches):
    """Kept-board power minus the recommended board's, for each advised swap.

    The Engine keeps the current board when this exceeds ``transition_tolerance``.
    Power is deterministic, so only family-1 model error enters the margin.
    """
    batches = tuple(batches)
    guards = []
    for batch in batches:
        rounds = {context.log_seq: context.snapshot['round_id'] for context in batch.contexts}
        for record in batch.records:
            numbers = record.advice.get('numbers', {})
            if record.decision != 'transition' or record.advice.get('option_id') != 'transition':
                continue
            kept, power = _finite(numbers.get('current_power')), _finite(numbers.get('power'))
            if kept is None or power is None or record.log_seq not in rounds:
                continue
            payload = record.advice.get('payload', {})
            swap = repr((tuple(payload.get('swap_out', ())), tuple(payload.get('swap_in', ()))))
            guards.append(PairedGuard(batch.game_id, record.log_seq, 0, record.decision_id, 'transition',
                _stage(rounds[record.log_seq]), swap, 'kept_board', None, 'power', kept-power,
                fixed_board=payload.get('board')))
    return GuardCollection(guards, batches)


def shop_guards(batches):
    """Board-power gains of shop units that only the power threshold can make eligible."""
    batches = tuple(batches)
    guards = []
    for batch in batches:
        rounds = {context.log_seq: context.snapshot['round_id'] for context in batch.contexts}
        for record in batch.records:
            if record.decision != 'shop' or record.log_seq not in rounds:
                continue
            for option in record.options:
                payload = option.get('payload', {})
                gain = _finite(payload.get('power_gain'))
                # Key, backup-key and pair reasons are decided before the threshold.
                if option.get('action') != 'buy' or payload.get('eligible_reason') not in ('power', None) or gain is None:
                    continue
                guards.append(PairedGuard(batch.game_id, record.log_seq, 0, record.decision_id, 'shop',
                    _stage(rounds[record.log_seq]), option['option_id'], 'current_board', None, 'power', gain))
    return GuardCollection(guards, batches)


def share_guards(batches):
    """Threat shares that the positioning hysteresis compared against its thresholds."""
    batches = tuple(batches)
    guards = []
    for batch in batches:
        rounds = {context.log_seq: context.snapshot['round_id'] for context in batch.contexts}
        for record in batch.records:
            payload = record.advice.get('payload', {})
            if record.decision != 'positioning' or payload.get('threats_available') is not True or record.log_seq not in rounds:
                continue
            for tag, share in sorted(payload.get('threat_shares', {}).items()):
                share = _finite(share)
                if share is None:
                    continue
                guards.append(PairedGuard(batch.game_id, record.log_seq, 0, record.decision_id, 'positioning',
                    _stage(rounds[record.log_seq]), str(tag), 'threat_share', None, 'share', share))
        present = {(guard.log_seq, guard.best_option) for guard in guards if guard.game_id == batch.game_id}
        for context in batch.contexts:
            shares = (context.evaluation or {}).get('guards', {}).get('threat_shares', {})
            for tag, value in shares.items():
                if (context.log_seq, tag) not in present and _finite(value) is not None:
                    guards.append(PairedGuard(batch.game_id, context.log_seq, 0,
                        f"{context.snapshot.get('snapshot_id')}:positioning", 'positioning',
                        _stage(context.snapshot['round_id']), tag, 'threat_share', None, 'share', float(value)))
    return GuardCollection(guards, batches)


def review_guards(batches, data_store):
    """Player-minus-Engine placement gaps that ``review_min_cost`` screens as close calls.

    Each batch is attributed by the review policy against ``data_store``. Only
    differing observed choices with a valued cost count; the paired tape is the
    two choices' same-seed rollouts, else the gap is counted as unavailable.
    """
    from tft_review.policy import ReviewPolicy
    batches = tuple(batches)
    guards = []
    for batch in batches:
        if not batch.records:
            continue
        data = data_store.get(batch.records[0].data_snapshot_id)
        report = ReviewPolicy(min_cost=0).build(batch, data=data)
        contexts = {context.log_seq: context for context in batch.contexts}
        occurrences = {}
        for row in report.timeline:
            occurrence = occurrences.get((row['log_seq'], row['category']), 0)
            occurrences[(row['log_seq'], row['category'])] = occurrence+1
            engine, player = row['engine_choice'], row['player_choice']
            if row['cost'] is None or not row['differed'] or engine is None or player is None:
                continue
            context = contexts[row['log_seq']]
            left, right = _rollouts(player, context.seed), _rollouts(engine, context.seed)
            differences = (tuple(a-b for a, b in zip(left, right))
                if left and right and len(left) == len(right) else None)
            guards.append(PairedGuard(batch.game_id, row['log_seq'], occurrence, row['engine_decision_id'],
                'review:'+row['category'], _stage(row['round_id']), engine['option_id'], player['option_id'],
                differences,
                valuations=_line_valuations(batch, row['log_seq'], (engine, player)) if row['category'] == 'econ' else None))
    return GuardCollection(guards, batches, data_store)


def _line_valuations(batch, log_seq, options):
    context = next(context for context in batch.contexts if context.log_seq == log_seq)
    plan = (context.evaluation or {}).get('plan', {})
    lines = [option.get('payload', {}).get('after', {}).get('line') for option in options]
    if not plan.get('target') or not all(lines):
        return None
    return tuple({'comp_id': plan['target'], 'lines': (line,), 'backup_id': plan.get('backup'),
        'domain': False, 'rollouts': len(option['payload']['after']['rollout_placements'])}
        for line, option in zip(lines, options))


def _fixed_tape(batch, context, data, valuation):
    from tft_engine import Line, simulate_lines
    from tft_engine.lobby import alive_lobby
    from tft_engine.opponents import opponents_from_history
    snapshot, history = batch.snapshot_for(context), batch.history_for(context)
    opponents = opponents_from_history(history, snapshot.round_id, data,
        opponent_ids=tuple(alive_lobby(snapshot, data)))
    count = valuation.get('rollouts')
    if count is None:
        return None
    scored = min(simulate_lines(snapshot, history, data, valuation['comp_id'],
        tuple(Line.from_dict(dict(line)) for line in valuation['lines']), seed=context.seed,
        backup_id=valuation['backup_id'], rollouts=count, opponents=opponents),
        key=lambda row: row.expected_placement)
    offset = 0
    if valuation['domain']:
        fit = (context.evaluation or {}).get('comp_fits', {}).get(valuation['comp_id'])
        if fit is None:
            return None
        offset = sum(term['delta'] for name, term in fit['terms'].items() if name != 'simulation')
    return tuple(value+offset for value in scored.rollout_placements)


def fixed_guards(batches, reference, data_store=None):
    """Evaluate the reference options and orientation at every original logged point.

    A missing original option stays unavailable. It never becomes a substitute
    best option or a silently omitted draw in the uncertainty estimator.
    """
    from dataclasses import replace
    from tft_review.contracts import frozen_json
    result = []
    contexts = {(batch.game_id, context.log_seq): (batch, context)
        for batch in batches for context in batch.contexts}
    for guard in reference:
        entry = contexts.get((guard.game_id, guard.log_seq))
        differences = components = value = None
        if entry is not None:
            batch, context = entry
            evaluation = context.evaluation or {}
            if guard.valuations is not None and data_store is not None:
                data = data_store.get(context.data_snapshot_id)
                try:
                    left, right = (_fixed_tape(batch, context, data, valuation) for valuation in guard.valuations)
                    if left and right and len(left) == len(right):
                        differences = (tuple(a-b for a, b in zip(left, right)) if guard.kind in _PLAN_GUARDS
                            else tuple(b-a for a, b in zip(left, right)))
                except (DataError, KeyError, TypeError, ValueError):
                    pass
            elif guard.kind in _PLAN_GUARDS:
                ids = guard.line_ids or (None, None)
                left, right = (_comp_tape(evaluation, comp, context.seed, line)
                    for comp, line in zip((guard.best_option, guard.runner_up), ids))
                if left and right and len(left) == len(right):
                    differences = tuple(a-b for a, b in zip(left, right))
            elif guard.kind == 'positioning':
                value = _finite(evaluation.get('guards', {}).get('threat_shares', {}).get(guard.best_option))
                if value is None:
                    candidates = share_guards((batch,))
                    value = next((row.value for row in candidates if row.key == guard.key), None)
            elif guard.kind == 'transition' and data_store is not None and guard.fixed_board is not None:
                from tft_engine import Board
                from tft_engine.planning import read
                from tft_engine.power import estimate_strength
                from tft_engine.capacity_fields import evidence_from_snapshot
                data = data_store.get(context.data_snapshot_id)
                snapshot = batch.snapshot_for(context)
                level = int(read(snapshot, data, 'level'))
                capacity = evidence_from_snapshot(snapshot, data)
                value = (estimate_strength(read(snapshot, data, 'board'), level, data, capacity=capacity).power
                    - estimate_strength(Board.from_dict(dict(guard.fixed_board)), level, data, capacity=capacity).power)
            else:
                category = guard.kind.removeprefix('review:')
                records = [record for record in batch.records if record.log_seq == guard.log_seq
                    and record.decision == category]
                # Option ids, rather than the draw's selected decision, bind the comparison.
                if guard.kind != 'shop':
                    records = records[guard.occurrence:guard.occurrence+1]
                options = {option['option_id']: option for record in records for option in record.options}
                if guard.kind.startswith('review:') and category == 'econ' and data_store is not None:
                    from tft_review.observed_line import value_observed_line
                    try:
                        observed, _ = value_observed_line(batch, context, data_store.get(context.data_snapshot_id))
                        options[observed['option_id']] = observed
                    except (DataError, KeyError, TypeError, ValueError):
                        pass
                if category == 'econ':
                    for rows in evaluation.get('line_results', {}).values():
                        for row in rows:
                            options.setdefault(row['line']['id'], {'payload': {'after': row}})
                best, other = options.get(guard.best_option), options.get(guard.runner_up)
                if guard.kind == 'shop':
                    value = _finite(best.get('payload', {}).get('power_gain')) if best else None
                elif guard.kind == 'transition':
                    value = next((row.value for row in transition_guards((batch,)) if row.key == guard.key), None)
                elif best is not None and other is not None:
                    conditional = _conditional_wisp(options, context.seed) if category == 'wisp' else None
                    if conditional is not None and conditional[:2] == (guard.best_option, guard.runner_up):
                        _, _, value, components = conditional
                    else:
                        left, right = _rollouts(best, context.seed), _rollouts(other, context.seed)
                        if left and right and len(left) == len(right):
                            differences = tuple(b-a for a, b in zip(left, right))
        result.append(replace(guard, differences=differences, value=value, components=components,
            fixed_board=frozen_json(guard.fixed_board) if guard.fixed_board is not None else None))
    return tuple(result)


def replay_draws(harness, draws, game_ids=None):
    """Replay finished games once per declared family-1 parameter draw.

    An empty draw replays the historical tunables. Seeds and logged decision
    points are those of the original log, so guards pair across draws.
    """
    from tft_review import ReplayProducer
    from .overlay import TunableOverlay

    if any(TUNABLE_FAMILIES.get(name) != '1' for draw in draws for name in draw):
        raise ValueError('Margin model draws vary family 1 parameters only')
    selected = None if game_ids is None else set(map(str, game_ids))
    games = [game['game_id'] for game in harness.sessions.list_games()
        if game['finished'] and (selected is None or game['game_id'] in selected)]
    result = []
    for draw in draws:
        store = TunableOverlay(harness.data_store, draw) if draw else harness.data_store
        producer = ReplayProducer(harness.sessions, store, repository=harness.repository,
            hooks=harness.hooks, hook_version='margin-draw:'+store.identity if draw else 'default')
        result.append(tuple(producer.produce(game_id) for game_id in games))
    return result


class StageMargins(dict):
    """Per-stage family-2 margins with their evidence; ``tunable_value`` is the file value."""

    def tunable_value(self):
        return {stage: row['value'] for stage, row in sorted(self.items(), key=lambda item: item[0])}


def stage_margins(guards, draw_guards, *, target, floor, costly_or_sticky, rollout_citation, model_citation):
    """Fixed per-stage margins from shared-tape and family-1 model uncertainty.

    Each decision's margin comes from ``estimate_margin``. A stage's value is
    the root mean square of its decisions' unfloored margins, never below the
    sourced floor. Decisions whose uncertainty is unavailable are counted by
    reason and leave the stage at its floor when none remain. Guards must be in
    the target's units; deterministic guards contribute model error only.
    """
    from collections import Counter

    units = _GUARD_UNITS.get(target)
    for guard in guards:
        if guard.units != units:
            raise DataError(f'{target} margins need {units} guards, not {guard.units} guards')
    draw_guards = [fixed_guards(draw.batches, guards, draw.data_store)
        if isinstance(draw, GuardCollection) else draw for draw in draw_guards]
    by_draw = [{guard.key: guard.mean for guard in draw if guard.mean is not None} for draw in draw_guards]
    grouped = {}
    missing_by_stage = {}
    for guard in guards:
        model = tuple(draw[guard.key] for draw in by_draw if guard.key in draw)
        incomplete = len(model) != len(by_draw)
        missing_by_stage[guard.stage] = missing_by_stage.get(guard.stage, 0)+len(by_draw)-len(model)
        estimate = estimate_margin(MarginInput(target, guard.stage, guard.kind, units, floor,
            costly_or_sticky, guard.differences, model, rollout_citation, model_citation,
            deterministic=guard.deterministic, rollout_components=guard.components))
        if units == 'share' and len(model) >= 2 and isclose(max(model), min(model), rel_tol=0, abs_tol=1e-12):
            from dataclasses import replace
            estimate = replace(estimate, value=floor.value, reason='invariant_share_not_noise_evidence')
        if incomplete:
            from dataclasses import replace
            estimate = replace(estimate, value=floor.value, mc_standard_error=None,
                model_standard_deviation=None, reason='incomplete_fixed_comparison_model_draws')
        grouped.setdefault(guard.stage, []).append(estimate)
    result = StageMargins()
    for stage, estimates in grouped.items():
        available = [estimate for estimate in estimates if estimate.reason is None]
        reasons = Counter(estimate.reason for estimate in estimates if estimate.reason)
        if reasons.get('incomplete_fixed_comparison_model_draws'):
            available = []
        value = floor.value
        unfloored = None
        if available:
            margins = [estimate.z*hypot(estimate.mc_standard_error, estimate.model_standard_deviation)
                for estimate in available]
            unfloored = _finite_number(sqrt(sum(item*item for item in margins)/len(margins)))
            value = max(floor.value, unfloored)
        result[stage] = {'value': value, 'unfloored': unfloored, 'z': estimates[0].z,
            'decisions': len(estimates), 'available': len(available), 'reasons': dict(reasons),
            'model_draws_required_per_decision': len(by_draw), 'missing_model_draw_values': missing_by_stage[stage],
            'units': units, 'aggregation': 'root mean square of per-decision margins; sourced floor',
            'citations': (floor.citation, rollout_citation, model_citation)}
    return result


def pooled(guards):
    """The same guards under one ``all`` key, for targets the Engine reads as a scalar."""
    from dataclasses import replace
    values = tuple(replace(guard, stage='all') for guard in guards)
    return GuardCollection(values, guards.batches, guards.data_store) if isinstance(guards, GuardCollection) else values


def reraise_extra(guards, draw_guards, *, floor, pivot_table, rollout_citation, model_citation):
    """Re-raise extra per stage: the re-raise guard's own margin beyond the pivot margin.

    A return to the rejected comp must clear z = 2 standard errors of that
    comparison. The pivot margin already applied at each decision (its stage,
    or ``post_roll_down`` after the Guide deadline) is subtracted; the result
    never falls below the sourced extra floor.
    """
    from dataclasses import replace

    def base(key):
        if not isinstance(pivot_table, dict):
            return float(pivot_table)
        value = float(pivot_table.get(key, pivot_table.get('default', 0)) if key != 'post_roll_down'
            else pivot_table.get('post_roll_down', pivot_table.get('default', 0)))
        return value

    def applied(guard):
        stage = base(guard.stage)
        return max(stage, base('post_roll_down')) if guard.base_key == 'post_roll_down' else stage

    totals = stage_margins(guards, draw_guards, target='pivot_reraise_extra', floor=replace(floor, value=0),
        costly_or_sticky=True, rollout_citation=rollout_citation, model_citation=model_citation)
    result = StageMargins()
    for stage, row in totals.items():
        decisions = [guard for guard in guards if guard.stage == stage]
        deficits, bases, required = [], [], []
        for guard in decisions:
            per_decision = stage_margins([guard], draw_guards, target='pivot_reraise_extra',
                floor=replace(floor, value=0), costly_or_sticky=True,
                rollout_citation=rollout_citation, model_citation=model_citation)[stage]
            if per_decision['unfloored'] is not None:
                bases.append(applied(guard))
                required.append(per_decision['unfloored'])
                deficits.append(per_decision['unfloored']-applied(guard))
        value = max([floor.value]+deficits) if row['available'] else floor.value
        result[stage] = row | {'value': value, 'reraise_margin': max(required) if required else None,
            'pivot_margin_applied': min(bases) if bases else None,
            'aggregation': 'maximum per-decision required margin minus its actual applied pivot base; sourced floor',
            'citations': (floor.citation, rollout_citation, model_citation)}
    return result


def share_band(row, *, on_floor, off_floor):
    """Preserve both sourced thresholds when a fixed-centre widening conflicts.

    ``fit_margins`` carries the pair with a reason when the measured half-width
    exceeds the sourced band. Noise alone cannot identify a different centre.
    """
    on, off = float(on_floor.value), float(off_floor.value)
    if not 0 <= off <= on <= 1:
        raise DataError('Threat share floors require 0 <= off <= on <= 1')
    half = (on-off)/2
    if row['unfloored'] is None or row['unfloored'] <= half:
        return on, off
    # Widening a fixed-centre band lowers off below its sourced minimum.
    # Preserve both floors until a different centre/noise contract is specified.
    return on, off


_STAGE_TARGETS = (
    ('line_margin', 'econ', False), ('wisp_buy_margin', 'wisp', False),
    ('pivot_margin_by_stage', 'pivot', True), ('comp_defining_margin', 'comp_defining', True),
    ('transition_tolerance', 'transition', False), ('board_power_buy_min', 'shop', False),
)


def _extract(kind, batches):
    if kind in ('econ', 'wisp'):
        return paired_guards(batches, kind=kind)
    if kind in _PLAN_GUARDS:
        return plan_guards(batches, kind=kind)
    return {'transition': transition_guards, 'shop': shop_guards, 'positioning': share_guards}[kind](batches)


def _floor(original, stage, target):
    if not isinstance(original, dict):
        return original
    value = original.get(stage)
    if value is None and target == 'pivot_margin_by_stage':
        # The Engine reads a missing pivot stage from ``default``.
        value = original.get('default')
    return value


def fit_margins(harness, parameters, *, metric='fight_log_loss', draws=8, seed=0,
        max_evaluations=64, fixed=None):
    """Produce family-2 candidates from actual Engine tapes and bootstrap refits.

    A missing compatible guard or source floor is explicitly carried; no
    sensitivity vector, fabricated rollout or absent model error becomes a fit.
    """
    from dataclasses import replace
    from .fitting import fit, model_uncertainty, current_set_games
    from .evaluation import chronological_split
    from tft_data.models import plain
    carried = {name: 'compatible_paired_guard_unavailable' for name, family in TUNABLE_FAMILIES.items()
        if family == '2'}
    if harness.sessions.run:
        return {'fields': {}, 'carried': {name: 'margins_frozen_during_live_run' for name in carried},
            'diagnostics': {}}
    _, games = current_set_games(harness)
    training, holdout = chronological_split([game for game in games if game['finished']])
    if len(training) < 2 or not holdout:
        return {'fields': {}, 'carried': {name: 'insufficient_training_games_for_model_uncertainty'
            for name in carried}, 'diagnostics': {}}
    uncertainty = model_uncertainty(harness, parameters, metric=metric, draws=draws,
        seed=seed, max_evaluations=max_evaluations, fixed=fixed)
    if not uncertainty.get('qualified', True):
        return {'fields': {}, 'carried': {name: 'unqualified_model_uncertainty_refits' for name in carried},
            'diagnostics': {}, 'model': {key: value for key, value in uncertainty.items() if key != 'parameters'}}
    centre = dict(fixed or {}) | dict(fit(harness, parameters, metric=metric,
        max_evaluations=max_evaluations, fixed=fixed, bootstrap_draws=20).parameters)
    draw_stores = [TunableOverlay(harness.data_store, draw) for draw in [centre]+uncertainty['parameters']]
    replayed = replay_draws(harness, [centre]+uncertainty['parameters'], training)
    current = getattr(harness.data_store, 'current', None)
    if current is None:
        first = next(game for game in games if game['game_id'] in training)
        current = harness.data_store.get(first['data_snapshot_id'])
    else:
        current = harness.data_store.get(current.snapshot_id)
    fields, diagnostics = {}, {}
    carried['comp_defining_margin'] = 'comp_commit_paired_guard_unavailable'
    drawn = ', '.join(sorted(parameters))
    model_citation = f'Training-game bootstrap refits of {drawn}; draws={draws}, seed={seed}'
    tape_citation = 'Original logged seed; actual paired Engine rollout placements'
    exact_citation = 'Exact deterministic Engine evidence; no Monte Carlo term'
    all_stages = {_stage(round_id) for round_id in current.value('round_order')}

    def sourced(target):
        floor = current.tunables.get(target)
        if floor is None or not floor.citation:
            carried[target] = 'sourced_floor_unavailable'
            return None
        return floor

    def settle(target, guards, result):
        diagnostics[target] = result
        if not any(row['available'] for row in result.values()):
            if guards:
                carried[target] = 'guard_uncertainty_unavailable'
            return False
        carried.pop(target, None)
        return True

    produced = {}
    for target, kind, sticky in _STAGE_TARGETS:
        if _GUARD_UNITS[target] == 'power' and any(
                centre.get(name, plain(current.tunables[name].value)) != plain(current.tunables[name].value)
                for name in ('unit_weight', 'trait_weight', 'item_weight')):
            carried[target] = 'power_floor_normalization_conversion_unqualified'
            diagnostics[target] = {'reason': carried[target]}
            continue
        guards = _extract(kind, replayed[0])
        if not guards:
            continue
        floor = sourced(target)
        if floor is None:
            continue
        original = plain(floor.value)
        result = StageMargins()
        for stage in sorted({guard.stage for guard in guards}):
            value = _floor(original, stage, target)
            if value is None:
                continue
            result.update(stage_margins([guard for guard in guards if guard.stage == stage],
                [fixed_guards(batch, guards, store) for batch, store in zip(replayed[1:], draw_stores[1:])], target=target,
                floor=replace(floor, value=value), costly_or_sticky=sticky,
                rollout_citation=exact_citation if all(guard.deterministic for guard in guards) else tape_citation,
                model_citation=model_citation))
        if settle(target, guards, result):
            # All historical stages remain valid when the Engine reads a table.
            table = dict(original) if isinstance(original, dict) else {stage: original for stage in all_stages}
            table.update({stage: row['value'] for stage, row in result.items() if row['available']})
            fields[target] = produced[target] = table

    guards = plan_guards(replayed[0], kind='pivot_reraise')
    floor = sourced('pivot_reraise_extra') if guards else None
    if floor is not None:
        pivot_floor = current.tunables.get('pivot_margin_by_stage')
        pivot_table = produced.get('pivot_margin_by_stage', plain(pivot_floor.value) if pivot_floor else None)
        original = plain(floor.value)
        if pivot_table is not None:
            result = StageMargins()
            for stage in sorted({guard.stage for guard in guards}):
                value = _floor(original, stage, 'pivot_reraise_extra')
                if value is None:
                    continue
                result.update(reraise_extra([guard for guard in guards if guard.stage == stage],
                    [fixed_guards(batch, guards, store) for batch, store in zip(replayed[1:], draw_stores[1:])],
                    floor=replace(floor, value=value), pivot_table=pivot_table,
                    rollout_citation=tape_citation, model_citation=model_citation))
            if settle('pivot_reraise_extra', guards, result):
                table = dict(original) if isinstance(original, dict) else {stage: original for stage in all_stages}
                table.update({stage: row['value'] for stage, row in result.items() if row['available']})
                fields['pivot_reraise_extra'] = table

    guards = pooled(share_guards(replayed[0]))
    on_floor, off_floor = (sourced(name) if guards else None for name in ('threat_share_on', 'threat_share_off'))
    if on_floor is not None and off_floor is not None:
        # Threat shares are exact; the floor is zero so the band, not a floor, bounds them.
        result = stage_margins(guards, [fixed_guards(batch, guards, store) for batch, store in zip(replayed[1:], draw_stores[1:])],
            target='threat_share_on', floor=replace(on_floor, value=0), costly_or_sticky=False,
            rollout_citation=exact_citation, model_citation=model_citation)
        on, off = share_band(result['all'], on_floor=on_floor, off_floor=off_floor)
        result['all'] = result['all'] | {'value': on, 'off_value': off,
            'aggregation': 'sourced hysteresis centre; half-width max(sourced, z * RMS share error)'}
        if result['all']['unfloored'] is not None and result['all']['unfloored'] > (float(on_floor.value)-float(off_floor.value))/2:
            diagnostics['threat_share_on'] = diagnostics['threat_share_off'] = result
            carried['threat_share_on'] = carried['threat_share_off'] = 'share_noise_band_conflicts_with_sourced_threshold_floors'
        elif settle('threat_share_on', guards, result):
            diagnostics['threat_share_off'] = result
            carried.pop('threat_share_off', None)
            fields['threat_share_on'], fields['threat_share_off'] = on, off
        elif guards:
            carried['threat_share_off'] = carried['threat_share_on']

    guards = pooled(review_guards(replayed[0], draw_stores[0]))
    floor = sourced('review_min_cost') if guards else None
    if floor is not None and not isinstance(plain(floor.value), dict):
        result = stage_margins(guards, [fixed_guards(batches, guards, store)
            for batches, store in zip(replayed[1:], draw_stores[1:])],
            target='review_min_cost', floor=floor, costly_or_sticky=False,
            rollout_citation=tape_citation, model_citation=model_citation)
        if settle('review_min_cost', guards, result):
            fields['review_min_cost'] = result['all']['value']
    return {'fields': fields, 'carried': carried, 'diagnostics': diagnostics,
        'model': {key: value for key, value in uncertainty.items() if key != 'parameters'} | {'centre_parameters': centre}}
