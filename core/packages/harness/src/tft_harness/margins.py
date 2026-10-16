"""Offline family-2 margins from declared paired and model-gap uncertainty.

Paired guards are read from replayed Engine records: the advised option
against its runner-up on the same seed tape. Model error is the spread of that
guard difference across replays under declared family-1 parameter draws. This
module does not fit models, manufacture missing draws or publish accepted
tunables; per-stage values go to a candidate tunables file.
"""
from dataclasses import dataclass
from math import hypot, isfinite, sqrt
from statistics import stdev

from tft_data import DataError, TaggedValue
from tft_data.config import TUNABLE_FAMILIES

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
    if inputs.rollout_differences is None:
        reason = 'paired_rollout_uncertainty_unavailable'
    elif len(inputs.rollout_differences) < 2:
        reason = 'insufficient_paired_rollouts'
    elif inputs.model_gap_draws is None:
        reason = 'model_gap_uncertainty_unavailable'
    elif len(inputs.model_gap_draws) < 2:
        reason = 'insufficient_model_gap_draws'
    if reason:
        return MarginEstimate(inputs.target, inputs.stage, inputs.kind, inputs.units,
            inputs.floor.value, z, None, None, reason,
            tuple(value for value in (inputs.floor.citation, inputs.rollout_citation, inputs.model_citation) if value))
    try:
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
    """One decision's best option against its runner-up on the shared rollout tape."""
    game_id: str
    log_seq: int
    occurrence: int
    decision_id: str
    kind: str
    stage: str
    best_option: str
    runner_up: str
    differences: tuple[float, ...]

    @property
    def key(self):
        # Decision ids digest the valuation; logged points and options pair draws.
        return (self.game_id, self.log_seq, self.kind, self.occurrence, self.best_option, self.runner_up)

    @property
    def mean(self):
        return sum(self.differences)/len(self.differences)


def _rollouts(option, seed):
    after = option.get('payload', {}).get('after')
    if not after or after.get('seed') != seed:
        return None
    values = after.get('rollout_placements')
    if not values or any(isinstance(value, bool) or not isinstance(value, (int, float))
                         or not isfinite(value) for value in values):
        return None
    return tuple(float(value) for value in values)


def paired_guards(batches, *, kind):
    """Paired placement differences (runner-up minus best) for one decision kind.

    The best option is the Engine's advised option; the runner-up is the other
    option with the lowest expected placement on the same seed tape. Decisions
    without two comparable same-seed rollout vectors are omitted.
    """
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
                str(rounds[record.log_seq]).split('-')[0], best['option_id'], runner_up,
                tuple(other-chosen for other, chosen in zip(rollouts, best_rollouts))))
    return tuple(guards)


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
    reason and leave the stage at its floor when none remain.
    """
    from collections import Counter

    if _GUARD_UNITS.get(target) != 'placement':
        raise DataError('Rollout-placement margins apply to placement-unit targets only')
    by_draw = [{guard.key: guard.mean for guard in draw} for draw in draw_guards]
    grouped = {}
    for guard in guards:
        model = tuple(draw[guard.key] for draw in by_draw if guard.key in draw)
        estimate = estimate_margin(MarginInput(target, guard.stage, guard.kind, 'placement', floor,
            costly_or_sticky, guard.differences, model, rollout_citation, model_citation))
        grouped.setdefault(guard.stage, []).append(estimate)
    result = StageMargins()
    for stage, estimates in grouped.items():
        available = [estimate for estimate in estimates if estimate.reason is None]
        reasons = Counter(estimate.reason for estimate in estimates if estimate.reason)
        value = floor.value
        if available:
            unfloored = [estimate.z*hypot(estimate.mc_standard_error, estimate.model_standard_deviation)
                for estimate in available]
            value = max(floor.value, _finite_number(sqrt(sum(item*item for item in unfloored)/len(unfloored))))
        result[stage] = {'value': value, 'z': estimates[0].z, 'decisions': len(estimates),
            'available': len(available), 'reasons': dict(reasons), 'units': 'placement',
            'aggregation': 'root mean square of per-decision margins; sourced floor',
            'citations': (floor.citation, rollout_citation, model_citation)}
    return result


def fit_margins(harness, parameters, *, metric='fight_log_loss', draws=8, seed=0,
        max_evaluations=64, fixed=None):
    """Produce family-2 candidates from actual Engine tapes and bootstrap refits.

    A missing compatible guard or source floor is explicitly carried; no
    sensitivity vector, fabricated rollout or absent model error becomes a fit.
    """
    from dataclasses import replace
    from .fitting import model_uncertainty, current_set_games
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
    replayed = replay_draws(harness, [{}]+uncertainty['parameters'], training)
    current = getattr(harness.data_store, 'current', None)
    if current is None:
        first = next(game for game in games if game['game_id'] in training)
        current = harness.data_store.get(first['data_snapshot_id'])
    else:
        current = harness.data_store.get(current.snapshot_id)
    fields, diagnostics = {}, {}
    carried['comp_defining_margin'] = 'comp_commit_paired_guard_unavailable'
    for target, kind, sticky in (('line_margin', 'econ', False),
            ('wisp_buy_margin', 'wisp', False)):
        if target not in current.tunables:
            continue
        guards = paired_guards(replayed[0], kind=kind)
        if not guards:
            continue
        floor = current.tunables[target]
        original = plain(floor.value)
        stages = sorted({guard.stage for guard in guards})
        result = {}
        for stage in stages:
            value = original.get(stage) if isinstance(original, dict) else original
            if value is None or not floor.citation:
                continue
            result.update(stage_margins([guard for guard in guards if guard.stage == stage],
                [paired_guards(batch, kind=kind) for batch in replayed[1:]], target=target,
                floor=replace(floor, value=value), costly_or_sticky=sticky,
                rollout_citation='Original logged seed; actual paired Engine rollout placements',
                model_citation=f'Training-game bootstrap refits; draws={draws}, seed={seed}'))
        diagnostics[target] = result
        available = {stage: row['value'] for stage, row in result.items() if row['available']}
        if available:
            # All historical stages remain valid when the Engine reads a table.
            all_stages = {str(round_id).split('-')[0] for round_id in current.value('round_order')}
            table = dict(original) if isinstance(original, dict) else {stage: original for stage in all_stages}
            table.update(available)
            fields[target] = table
            carried.pop(target, None)
    return {'fields': fields, 'carried': carried, 'diagnostics': diagnostics,
        'model': {key: value for key, value in uncertainty.items() if key != 'parameters'}}
