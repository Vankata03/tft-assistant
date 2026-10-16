"""Family-1 functional optimization on chronological training games of the current set.

Two declared search forms exist. An explicit finite grid is searched
exhaustively. Bounded continuous ranges use a deterministic golden-section
coordinate search. Per-stage tunables (``*_by_stage``) start pooled across
stages; a stage gets its own value only past the declared fight count, shrunk
toward the pooled value. Every result is an unaccepted candidate scored on the
chronological holdout by the existing comparative gates.
"""
from dataclasses import dataclass
from itertools import product
import json
from math import isfinite, prod, sqrt

from tft_data.config import TUNABLE_FAMILIES
from tft_review.contracts import frozen_json, json_value

from .measurement import mean_by_game
from .overlay import TunableOverlay

# Spec: "a stage gets its own value only past about 150 fights at that stage".
STAGE_SPLIT_MIN_FIGHTS = 150
_GOLDEN = (sqrt(5)-1)/2


@dataclass(frozen=True)
class ContinuousRange:
    """Declared closed search bounds for one family-1 scalar."""
    low: float
    high: float
    start: float | None = None

    def __post_init__(self):
        values = (self.low, self.high) + (() if self.start is None else (self.start,))
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value)
               for value in values) or not self.low < self.high:
            raise ValueError('Continuous range requires finite ordered bounds')
        if self.start is not None and not self.low <= self.start <= self.high:
            raise ValueError('Continuous range start must lie inside its bounds')


@dataclass(frozen=True)
class FitReport:
    parameters: object
    training_game_ids: tuple[str,...]
    holdout_game_ids: tuple[str,...]
    training_objective: object
    gates: object
    solver: object
    status: str = 'unaccepted_candidate'

    def __post_init__(self):
        for field in ('parameters','training_objective','gates','solver'):
            object.__setattr__(self,field,frozen_json(getattr(self,field)))


def current_set_games(harness, set_id=None):
    """Games of the declared set; default is the run's set, else the newest game's."""
    games = harness.sessions.list_games()
    declared = getattr(harness, 'current_set', None)
    if set_id is not None and declared is not None and str(set_id) != str(declared):
        raise ValueError(f'Fit set {set_id} differs from the harness current set {declared}')
    if set_id is None and declared is not None:
        set_id = declared
    if set_id is None:
        run = harness.sessions.run
        if run:
            set_id = run['set_id']
        else:
            ordered = sorted((game for game in games if game['finished']), key=lambda game: game['date'])
            set_id = ordered[-1]['set_id'] if ordered else None
    selected = [game for game in games if set_id is not None and game['set_id'] == str(set_id)]
    if not selected:
        raise ValueError(f'No logged games of set {set_id}')
    return str(set_id), selected


def _validate(parameters, fixed, max_candidates):
    if not parameters or any(TUNABLE_FAMILIES.get(name) != '1' for name in (*parameters, *fixed)):
        raise ValueError('Owner-log fitting accepts family 1 only')
    ranges = [isinstance(value, ContinuousRange) for value in parameters.values()]
    if any(ranges) and not all(ranges):
        raise ValueError('Continuous ranges cannot be mixed with grid values in one fit')
    continuous = all(ranges)
    if not continuous:
        if any(not isinstance(values,(tuple,list)) or not values for values in parameters.values()):
            raise ValueError('Fit requires an explicit nonempty candidate grid per parameter')
        if type(max_candidates) is not int or max_candidates < 1 or prod(map(len,parameters.values())) > max_candidates:
            raise ValueError('Declared fitting search budget exceeded')
    varied = lambda name: name in parameters and (continuous or len(parameters[name]) > 1)
    if varied('fight_scale') and any(varied(name) for name in ('unit_weight','trait_weight','item_weight')) \
            and not (not continuous and len(parameters.get('unit_weight',())) == 1):
        raise ValueError('Joint power/scale fitting requires an explicit fixed unit-weight normalization')
    return continuous


class _Objective:
    """Training objective with memoized replays and the frozen eligible-truth check."""

    def __init__(self, harness, training, metric, fixed, budget):
        self.harness, self.training, self.metric, self.fixed, self.budget = harness, training, metric, fixed, budget
        self.memo, self.tested = {}, []
        baseline, original = harness._evaluate(training, harness.data_store)
        if metric not in baseline.metrics:
            raise ValueError('Fit objective is unavailable')
        self.reference_rows = [row for row in original if row['metric'] == metric]
        if not self.reference_rows:
            raise ValueError('Fit objective has no qualified training truth')
        self.keys = {(row['game_id'], row['observation_seq']) for row in self.reference_rows}
        self.reference = mean_by_game((row['game_id'], row['loss']) for row in self.reference_rows)

    @property
    def exhausted(self):
        return self.budget is not None and len(self.tested) >= self.budget

    def __call__(self, candidate):
        key = json.dumps(json_value(candidate), sort_keys=True)
        if key in self.memo:
            return self.memo[key]
        if self.exhausted:
            return float('inf')
        overlay = TunableOverlay(self.harness.data_store, dict(self.fixed) | dict(candidate))
        _, rows = self.harness._evaluate(self.training, overlay, hook_version='fit:'+overlay.identity)
        rows = [row for row in rows if row['metric'] == self.metric]
        eligible = {(row['game_id'], row['observation_seq']) for row in rows} == self.keys
        objective = mean_by_game((row['game_id'], row['loss']) for row in rows) if eligible else None
        self.tested.append({'parameters': candidate, 'objective': objective,
            'reason': None if objective is not None else 'infinite_loss_or_changed_eligible_truth'})
        value = float('inf') if objective is None else objective
        self.memo[key] = value
        return value


def _golden(evaluate, low, high, start, tolerance):
    """Minimize a unimodal objective on [low, high]; returns (x, f(x), touched bound)."""
    width = (high-low)*tolerance
    a, b = low, high
    c, d = b-_GOLDEN*(b-a), a+_GOLDEN*(b-a)
    fc, fd = evaluate(c), evaluate(d)
    while b-a > width:
        if fc <= fd:
            b, d, fd = d, c, fc
            c = b-_GOLDEN*(b-a)
            fc = evaluate(c)
        else:
            a, c, fc = c, d, fd
            d = a+_GOLDEN*(b-a)
            fd = evaluate(d)
    best, value = (c, fc) if fc <= fd else (d, fd)
    if start is not None:
        start_value = evaluate(start)
        if start_value < value:
            best, value = start, start_value
    bound = None
    for edge in (low, high):
        if abs(best-edge) <= .01*(high-low):
            edge_value = evaluate(edge)
            if edge_value <= value:
                best, value, bound = edge, edge_value, edge
    return best, value, bound


def _stages(harness, training):
    stages = set()
    for game in harness.sessions.list_games():
        if game['game_id'] in training and game['data_snapshot_id']:
            data = harness.data_store.get(game['data_snapshot_id'])
            stages.update(str(round_id).split('-')[0] for round_id in data.value('round_order'))
    return sorted(stages, key=int)


def _continuous(harness, objective, ranges, training, *, stage_split_min_fights, tolerance, max_cycles=4):
    by_stage = {name for name in ranges if name.endswith('_by_stage')}
    stages = _stages(harness, training) if by_stage else []
    if by_stage and not stages:
        raise ValueError('Per-stage fitting requires the historical round order')

    def expand(values):
        return {name: ({stage: value for stage in stages} if name in by_stage else value)
            for name, value in values.items()}

    current = {name: (declared.start if declared.start is not None else (declared.low+declared.high)/2)
        for name, declared in ranges.items()}
    at_bound = set()
    for _ in range(max_cycles if len(ranges) > 1 else 1):
        moved = 0.0
        for name, declared in sorted(ranges.items()):
            point, _, bound = _golden(lambda value: objective(expand(current | {name: value})),
                declared.low, declared.high, current[name], tolerance)
            moved = max(moved, abs(point-current[name])/(declared.high-declared.low))
            current[name] = point
            (at_bound.add if bound is not None else at_bound.discard)(name)
        if moved <= tolerance or objective.exhausted:
            break
    pooled = dict(current)
    candidate = expand(pooled)
    counts = {}
    for row in objective.reference_rows:
        counts[str(row['stage'])] = counts.get(str(row['stage']), 0)+1
    stage_report = {}
    for stage in stages:
        fights = counts.get(stage, 0)
        split = fights >= stage_split_min_fights
        unshrunk = {}
        if split:
            for name in sorted(by_stage):
                declared = ranges[name]
                fixed = dict(candidate)
                point, _, _ = _golden(lambda value: objective(fixed | {name: dict(fixed[name]) | {stage: value}}),
                    declared.low, declared.high, pooled[name], tolerance)
                unshrunk[name] = point
        stage_report[stage] = {'fights': fights, 'split': split, 'unshrunk': unshrunk or None}
    for name in by_stage:
        candidate[name] = {stage: ((row['fights']*row['unshrunk'][name]+stage_split_min_fights*pooled[name])
            /(row['fights']+stage_split_min_fights) if row['split'] else pooled[name])
            for stage, row in stage_report.items()}
    value = objective(candidate)
    return candidate, value, {'pooled': pooled, 'at_bound': sorted(at_bound),
        'stages': stage_report if by_stage else {},
        'shrinkage': f'n/(n+{stage_split_min_fights}) toward pooled' if by_stage else None}


def fit(harness, parameters, *, metric='fight_log_loss', bootstrap_seed=0, bootstrap_draws=2000, max_candidates=256,
        max_evaluations=64, set_id=None, stage_split_min_fights=STAGE_SPLIT_MIN_FIGHTS,
        tolerance=1e-4, fixed=None):
    from .evaluation import chronological_split
    from .metrics import FITTED_METRICS
    if metric not in FITTED_METRICS:
        raise ValueError('Report-only metrics cannot be fitted')
    fixed = dict(fixed or {})
    continuous = _validate(parameters, fixed, max_candidates)
    if type(max_evaluations) is not int or max_evaluations < 3:
        raise ValueError('Continuous fitting requires an evaluation budget of at least three')
    if type(stage_split_min_fights) is not int or stage_split_min_fights < 1:
        raise ValueError('Stage split threshold must be a positive fight count')
    if not 0 < tolerance < 1:
        raise ValueError('Fit tolerance must be a fraction of each declared range')
    if harness.sessions.active_game_id:
        raise ValueError('A refit cannot run during an active game')
    games = harness.sessions.list_games()
    if harness.sessions.run:
        run_games = [game for game in games if game['pinned']]
        if any(not game['finished'] or game['placement'] is None for game in run_games) or len(run_games)%10:
            raise ValueError('During the run family 1 refits require a completed ten-game block boundary')
    set_id, current = current_set_games(harness, set_id)
    training, holdout = chronological_split([game for game in current if game['finished']])
    if not training or not holdout:
        raise ValueError('Chronological fitting requires disjoint training and holdout games')
    objective = _Objective(harness, training, metric, fixed, max_evaluations if continuous else None)
    extra = {}
    if continuous:
        best, value, extra = _continuous(harness, objective, parameters, training,
            stage_split_min_fights=stage_split_min_fights, tolerance=tolerance)
        if not isfinite(value):
            raise ValueError('No finite eligible candidate inside the declared fitting ranges')
        best = (value, best)
        method = 'bounded golden-section coordinate search'
        convergence = ('evaluation budget exhausted' if objective.exhausted else
            f'bracket below {tolerance} of each declared range; unimodal objective assumed')
    else:
        best = None
        names = tuple(sorted(parameters))
        for values in product(*(parameters[name] for name in names)):
            candidate = dict(zip(names,values))
            value = objective(candidate)
            if isfinite(value) and (best is None or value < best[0]):
                best = (value,candidate)
        if best is None:
            raise ValueError('No finite eligible candidate in declared fitting grid')
        method = 'exhaustive declared grid'
        convergence = 'global minimum on supplied finite grid; continuous optimum not claimed'
    evaluated = harness.evaluate([game['game_id'] for game in current], candidate=fixed | best[1],
        bootstrap_seed=bootstrap_seed, bootstrap_draws=bootstrap_draws)
    return FitReport(best[1],training,holdout,{'metric':metric,'reference':objective.reference,
        'reference_reason':None if objective.reference is not None else 'infinite_log_loss',
        'candidate':best[0],'weighting':'equal games'},evaluated.gates,
        {'method':method,'evaluations':len(objective.tested),'candidates':objective.tested,
         'convergence':convergence,'set_id':set_id,'fixed':fixed,
         'ranges':{name:{'low':value.low,'high':value.high,'start':value.start}
             for name,value in parameters.items()} if continuous else None,
         **({'at_bound':[], 'pooled':{}, 'stages':{}, 'shrinkage':None} | extra),
         'publication':'unaccepted; owner Git commit required'})
