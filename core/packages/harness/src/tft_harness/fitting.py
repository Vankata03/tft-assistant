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
from math import exp, isfinite, log, prod, sqrt

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
class SimplexRange:
    """A probability vector fitted with K-1 bounded logits; the last logit is zero.

    Bounds apply to log(p_i/p_last), so finite ranges describe strictly positive
    probabilities. Fixed probability vectors may contain zeros. ``start`` must
    lie in the declared logit bounds. ``keys`` returns a category map when set.
    """
    size: int = 3
    low: float = -8.
    high: float = 8.
    start: tuple[float, ...] | None = None
    keys: tuple[str, ...] | None = None

    def __post_init__(self):
        if type(self.size) is not int or not 2 <= self.size <= 129:
            raise ValueError('Simplex range requires 2–129 categories')
        ContinuousRange(self.low, self.high)
        if not -350 <= self.low < self.high <= 350:
            raise ValueError('Simplex range logits must stay within [-350,350] to preserve positive mass')
        if self.keys is not None and (not isinstance(self.keys, (tuple, list)) or len(self.keys) != self.size
                or any(not isinstance(key, str) or not key for key in self.keys) or len(set(self.keys)) != self.size):
            raise ValueError('Simplex range keys must identify each category exactly once')
        if self.start is not None:
            if (not isinstance(self.start, (tuple, list)) or len(self.start) != self.size
                    or any(isinstance(p, bool) or not isinstance(p, (int, float))
                        or not isfinite(p) or p <= 0 for p in self.start)
                    or abs(sum(self.start)-1) > 1e-9):
                raise ValueError('Simplex range start requires positive probabilities summing to one')
            if any(not self.low <= log(p/self.start[-1]) <= self.high for p in self.start[:-1]):
                raise ValueError('Simplex range start lies outside its logit bounds')


def _contains_range(value):
    if isinstance(value, (ContinuousRange, SimplexRange)):
        return True
    return isinstance(value, dict) and any(_contains_range(v) for v in value.values())


def _label(path):
    """Dotted coordinate label; private aggregate reports scrub any path separator."""
    return '.'.join(map(str, path))


class _SearchSpace:
    """Flatten declared nested maps into identifiable bounded scalar coordinates."""

    def __init__(self, template):
        self.template, self.coordinates = template, {}
        def visit(value, path):
            if isinstance(value, ContinuousRange):
                self.coordinates[path] = value
            elif isinstance(value, SimplexRange):
                for index in range(value.size-1):
                    start = log(value.start[index]/value.start[-1]) if value.start else (value.low+value.high)/2
                    self.coordinates[path+(index,)] = ContinuousRange(value.low, value.high, start)
            elif isinstance(value, dict):
                if not value or any(not isinstance(key, str) or not key for key in value):
                    raise ValueError('Nested fitting maps require nonempty string keys')
                for key, child in value.items():
                    visit(child, path+(key,))
            elif isinstance(value, (list, tuple)):
                # Lists inside a template are fixed Engine values, never candidate grids.
                if any(_contains_range(child) for child in value):
                    raise ValueError('Nested ranges require maps or SimplexRange probability vectors')
                for index, child in enumerate(value):
                    visit(child, path+(index,))
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValueError('Continuous template constants require finite numbers')
        visit(template, ())
        if len(self.coordinates) > 128:
            raise ValueError('Continuous fitting supports at most 128 coordinates')

    def expand(self, values):
        def build(value, path):
            if isinstance(value, ContinuousRange):
                return values[path]
            if isinstance(value, SimplexRange):
                logits = [values[path+(index,)] for index in range(value.size-1)]+[0.]
                maximum = max(logits)
                weights = [exp(point-maximum) for point in logits]
                probabilities = [weight/sum(weights) for weight in weights]
                return dict(zip(value.keys, probabilities)) if value.keys is not None else probabilities
            if isinstance(value, dict):
                return {key: build(child, path+(key,)) for key, child in value.items()}
            if isinstance(value, (list, tuple)):
                return list(value)
            return value
        return build(self.template, ())

    def description(self):
        return {_label(path): {'low': value.low, 'high': value.high, 'start': value.start}
            for path, value in self.coordinates.items()}


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
    if set(parameters) & set(fixed):
        raise ValueError('Fixed normalization fields cannot also be fitted')
    strict_positive = {'fight_scale', 'win_scale_by_stage', 'survivor_scale_by_stage',
        'sighting_half_life_rounds', 'opponent_growth_correction_by_stage'}
    def domain(name, value):
        if isinstance(value, SimplexRange):
            return
        if isinstance(value, ContinuousRange):
            if value.low < 0 or (name in strict_positive and value.low == 0):
                raise ValueError(f'{name} search violates its physical domain')
        elif isinstance(value, dict):
            for child in value.values():
                domain(name, child)
        elif isinstance(value, (tuple, list)):
            for child in value:
                domain(name, child)
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) \
                or value < 0 or (name in strict_positive and value == 0):
            raise ValueError(f'{name} search violates its physical domain')
    for name, value in (parameters | fixed).items():
        domain(name, value)
    ranges = [_contains_range(value) for value in parameters.values()]
    if any(ranges) and not all(ranges):
        raise ValueError('Continuous ranges cannot be mixed with grid values in one fit')
    continuous = all(ranges)
    if continuous:
        _SearchSpace(parameters)
    if not continuous:
        if any(not isinstance(values,(tuple,list)) or not values for values in parameters.values()):
            raise ValueError('Fit requires an explicit nonempty candidate grid per parameter')
        if type(max_candidates) is not int or not 1 <= max_candidates <= 4096 or prod(map(len,parameters.values())) > max_candidates:
            raise ValueError('Declared fitting search budget exceeded')
    varied = lambda name: name in parameters and (continuous or len(parameters[name]) > 1)
    if any(varied(scale) for scale in ('fight_scale', 'win_scale_by_stage')) and any(varied(name) for name in ('unit_weight','trait_weight','item_weight')) \
            and not ('unit_weight' in fixed and not isinstance(fixed['unit_weight'], bool)
                and isinstance(fixed['unit_weight'], (int, float)) and isfinite(fixed['unit_weight'])
                and fixed['unit_weight'] > 0) \
            and not (not continuous and len(parameters.get('unit_weight',())) == 1):
        raise ValueError('Joint power/scale fitting requires an explicit fixed unit-weight normalization')
    return continuous


class _Objective:
    """Training objective with memoized replays and the frozen eligible-truth check."""

    def __init__(self, harness, training, metric, fixed, budget, weights=None):
        self.harness, self.training, self.metric, self.fixed, self.budget = harness, training, metric, fixed, budget
        self.memo, self.tested = {}, []
        self.weights = weights
        baseline, original = harness._evaluate(training, harness.data_store)
        if metric not in baseline.metrics:
            raise ValueError('Fit objective is unavailable')
        self.reference_rows = [row for row in original if row['metric'] == metric]
        self.fight_rows = [row for row in original if row['metric'] == 'fight_brier']
        if not self.reference_rows:
            raise ValueError('Fit objective has no qualified training truth')
        self.keys = {(row['game_id'], row['observation_seq']) for row in self.reference_rows}
        self.reference = mean_by_game((row['game_id'], row['loss']) for row in self.reference_rows)

    def mean(self, rows):
        if not self.weights:
            return mean_by_game((row['game_id'], row['loss']) for row in rows)
        by_game = {}
        for row in rows:
            by_game.setdefault(row['game_id'], []).append(row['loss'])
        if any(value is None for values in by_game.values() for value in values):
            return None
        total = sum(self.weights.get(game, 0) for game in by_game)
        return sum(sum(values)/len(values)*self.weights.get(game, 0)
            for game, values in by_game.items())/total if total else None

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
        objective = self.mean(rows) if eligible else None
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
    start_value = float('inf')
    if start is not None:
        start_value = evaluate(start)
        if start_value <= value:
            best, value = start, start_value
    bound = None
    for edge in (low, high):
        if abs(best-edge) <= .01*(high-low):
            edge_value = evaluate(edge)
            if edge_value <= value and edge_value < start_value:
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
    by_stage = {name for name in ranges if name.endswith('_by_stage') and isinstance(ranges[name], ContinuousRange)}
    if any(name.endswith('_by_stage') and name not in by_stage for name in ranges):
        raise ValueError('Per-stage continuous fitting requires one pooled ContinuousRange per field')
    stages = _stages(harness, training) if by_stage else []
    if by_stage and not stages:
        raise ValueError('Per-stage fitting requires the historical round order')

    def expand(values):
        return {name: ({stage: value for stage in stages} if name in by_stage else value)
            for name, value in values.items()}

    space = _SearchSpace(ranges)
    current = {path: (declared.start if declared.start is not None else (declared.low+declared.high)/2)
        for path, declared in space.coordinates.items()}
    # Reserve one evaluation for the final shrunk candidate, so budget exhaustion
    # cannot publish an unshrunk stage optimum as the fitted result.
    budget = objective.budget
    if budget is not None:
        objective.budget = max(1, budget-1)
    objective(expand(space.expand(current)))
    at_bound = set()
    coordinate_report = {}
    starts = dict(current)

    def search(evaluate, declared, start):
        samples = []
        def measured(point):
            value = evaluate(point)
            if isfinite(value):
                samples.append((point, value))
            return value
        for anchor in (start, declared.low, declared.high):
            measured(anchor)
        point, loss, bound = _golden(measured, declared.low, declared.high, start, tolerance)
        spread = max((value for _, value in samples), default=0)-min((value for _, value in samples), default=0)
        status = 'budget_exhausted' if objective.exhausted else 'converged'
        if len({point for point, _ in samples}) >= 3 and spread <= 1e-10:
            point, loss, bound = start, evaluate(start), None
            status = 'objective_flat_retained_start' if spread <= 1e-14 else 'objective_weak_retained_start'
        return point, loss, bound, {'status': status, 'profile_loss_range': spread,
            'at_bound': bound, 'qualified': status == 'converged'}
    for _ in range(max_cycles if len(current) > 1 else 1):
        moved = 0.0
        for path, declared in space.coordinates.items():
            point, loss, bound, diagnostic = search(lambda value: objective(expand(space.expand(current | {path: value}))),
                declared, starts[path])
            coordinate_report[_label(path)] = diagnostic
            if not isfinite(loss):
                break
            moved = max(moved, abs(point-current[path])/(declared.high-declared.low))
            current[path] = point
            label = _label(path)
            (at_bound.add if bound is not None else at_bound.discard)(label)
            if objective.exhausted:
                break
        if moved <= tolerance or objective.exhausted:
            break
    pooled = space.expand(current)
    candidate = expand(pooled)
    counts = {}
    for row in objective.fight_rows:
        count = objective.weights.get(row['game_id'], 0) if objective.weights is not None else 1
        counts[str(row['stage'])] = counts.get(str(row['stage']), 0)+count
    stage_report = {}
    for stage in stages:
        fights = counts.get(stage, 0)
        qualified_count = fights >= stage_split_min_fights
        unshrunk, bounds, diagnostics = {}, {}, {}
        status = 'insufficient_fights' if not qualified_count else 'budget_exhausted' if objective.exhausted else 'converged'
        if qualified_count and not objective.exhausted:
            for name in sorted(by_stage):
                declared = ranges[name]
                fixed = dict(candidate)
                point, loss, bound, diagnostic = search(
                    lambda value: objective(fixed | {name: dict(fixed[name]) | {stage: value}}),
                    declared, pooled[name])
                diagnostics[name] = diagnostic
                if bound is not None:
                    bounds[name] = bound
                if diagnostic['status'] != 'converged' or not isfinite(loss):
                    status = diagnostic['status']
                    break
                unshrunk[name] = point
        split = qualified_count and status == 'converged' and len(unshrunk) == len(by_stage)
        stage_report[stage] = {'fights': fights, 'count_qualified': qualified_count,
            'split': split, 'status': status, 'at_bound': bounds,
            'coordinates': diagnostics, 'unshrunk': unshrunk if split else None}
    for name in by_stage:
        candidate[name] = {stage: ((row['fights']*row['unshrunk'][name]+stage_split_min_fights*pooled[name])
            /(row['fights']+stage_split_min_fights) if row['split'] else pooled[name])
            for stage, row in stage_report.items()}
    objective.budget = budget
    value = objective(candidate)
    return candidate, value, {'pooled': pooled, 'at_bound': sorted(at_bound),
        'coordinates': coordinate_report,
        'stages': stage_report if by_stage else {},
        'shrinkage': f'fights divided by (fights plus {stage_split_min_fights}) toward pooled' if by_stage else None}


def _retain_flat_grid(objective, parameters, best):
    """Keep accepted coordinates (else the declared grid start) on flat profiles."""
    coordinates = {}
    games = [game for game in objective.harness.sessions.list_games() if game['game_id'] in objective.training]
    for name in parameters:
        profile = [row for row in objective.tested if row['objective'] is not None
            and all(value == best[1][key] for key, value in row['parameters'].items() if key != name)]
        if len(profile) < 2:
            continue
        spread = max(row['objective'] for row in profile)-min(row['objective'] for row in profile)
        if spread > 1e-10:
            continue
        accepted = [json_value(objective.harness.data_store.get(game['data_snapshot_id']).tunable(name)) for game in games]
        common = accepted and all(value == accepted[0] for value in accepted)
        retained = next((row for row in profile if common and row['parameters'][name] == accepted[0]), None)
        source = 'accepted' if retained is not None else 'declared_grid_start'
        if retained is None:
            retained = next(row for row in profile if row['parameters'][name] == parameters[name][0])
        best = retained['objective'], retained['parameters']
        coordinates[name] = {'status': 'objective_flat_retained_'+source if spread <= 1e-14 else 'objective_weak_retained_'+source,
            'profile_loss_range': spread, 'qualified': False}
    return best, coordinates


def fit(harness, parameters, *, metric='fight_log_loss', bootstrap_seed=0, bootstrap_draws=2000, max_candidates=256,
        max_evaluations=64, set_id=None, stage_split_min_fights=STAGE_SPLIT_MIN_FIGHTS,
        tolerance=1e-4, fixed=None):
    from .evaluation import chronological_split
    from .metrics import FITTED_METRICS
    if metric not in FITTED_METRICS:
        raise ValueError('Report-only metrics cannot be fitted')
    fixed = dict(fixed or {})
    continuous = _validate(parameters, fixed, max_candidates)
    if type(max_evaluations) is not int or not 3 <= max_evaluations <= 256:
        raise ValueError('Continuous fitting requires an evaluation budget of 3–256')
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
            viable = [row for row in objective.tested if row['objective'] is not None]
            if not viable:
                raise ValueError('No finite eligible candidate inside the declared fitting ranges')
            winner = min(viable, key=lambda row: row['objective'])
            best, value = winner['parameters'], winner['objective']
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
        best, coordinates = _retain_flat_grid(objective, parameters, best)
        extra = {'coordinates': coordinates}
        method = 'exhaustive declared grid'
        convergence = 'global minimum on supplied finite grid; continuous optimum not claimed'
    evaluated = harness.evaluate([game['game_id'] for game in current], candidate=fixed | best[1],
        bootstrap_seed=bootstrap_seed, bootstrap_draws=bootstrap_draws)
    return FitReport(best[1],training,holdout,{'metric':metric,'reference':objective.reference,
        'reference_reason':None if objective.reference is not None else 'infinite_log_loss',
        'candidate':best[0],'weighting':'equal games',
        'likelihood':'equal-game-weighted mean loss; per-fight likelihood not claimed'},evaluated.gates,
        {'method':method,'evaluations':len(objective.tested),'candidates':objective.tested,
         'convergence':convergence,'set_id':set_id,'fixed':fixed,
         'ranges': _SearchSpace(parameters).description() if continuous else None,
         **({'at_bound':[], 'pooled':{}, 'stages':{}, 'shrinkage':None} | extra),
         'publication':'unaccepted; owner Git commit required'})


def model_uncertainty(harness, parameters, *, metric='fight_log_loss', draws=32, seed=0,
        max_evaluations=64, fixed=None):
    """Refit training games under a deterministic game bootstrap; never use holdout truth.

    These draws estimate fitted parameter uncertainty. They are distinct from
    declared sensitivity draws and from Monte Carlo rollout uncertainty.
    """
    from collections import Counter
    from random import Random
    from .evaluation import chronological_split
    from .metrics import FITTED_METRICS
    if metric not in FITTED_METRICS or type(draws) is not int or not 2 <= draws <= 128:
        raise ValueError('Model uncertainty requires a fitted metric and 2–128 bootstrap refits')
    if type(max_evaluations) is not int or not 3 <= max_evaluations <= 256:
        raise ValueError('Model refitting requires an evaluation budget of 3–256')
    if harness.sessions.active_game_id:
        raise ValueError('Model refitting cannot run during an active game')
    if harness.sessions.run:
        pinned = [game for game in harness.sessions.list_games() if game['pinned']]
        if any(not game['finished'] or game['placement'] is None for game in pinned) or len(pinned)%10:
            raise ValueError('During the run family 1 refits require a completed ten-game block boundary')
    fixed = dict(fixed or {})
    continuous = _validate(parameters, fixed, 256)
    _, games = current_set_games(harness)
    training, holdout = chronological_split([game for game in games if game['finished']])
    if len(training) < 2 or not holdout:
        raise ValueError('Model uncertainty requires at least two training games and a holdout')
    rng, fitted, diagnostics = Random(seed), [], []
    for _ in range(draws):
        weights = Counter(rng.choices(training, k=len(training)))
        objective = _Objective(harness, training, metric, fixed,
            max_evaluations if continuous else None, weights=weights)
        if continuous:
            candidate, value, diagnostic = _continuous(harness, objective, parameters, training,
                stage_split_min_fights=STAGE_SPLIT_MIN_FIGHTS, tolerance=1e-4)
            diagnostics.append({'budget_exhausted': objective.exhausted,
                'stages': diagnostic['stages'], 'coordinates': diagnostic['coordinates']})
            if isfinite(value):
                fitted.append(fixed | candidate)
                continue
        else:
            names = tuple(sorted(parameters))
            for values in product(*(parameters[name] for name in names)):
                objective(dict(zip(names, values)))
        viable = [row for row in objective.tested if row['objective'] is not None]
        if not viable:
            raise ValueError('Bootstrap refit has no finite eligible model')
        best = min(viable, key=lambda row: row['objective'])
        (_, candidate), coordinates = _retain_flat_grid(objective, parameters, (best['objective'], best['parameters'])) if not continuous else ((best['objective'], best['parameters']), {})
        if not continuous:
            diagnostics.append({'budget_exhausted': False, 'coordinates': coordinates, 'stages': {}})
        fitted.append(fixed | candidate)
    return {'method': 'training-game bootstrap refits', 'metric': metric, 'seed': seed,
        'training_games': len(training), 'holdout_games': len(holdout),
        'draws': draws, 'parameters': fitted, 'refits': diagnostics,
        'qualified': not any(row['budget_exhausted'] or any(not value['qualified']
            for value in row['coordinates'].values()) for row in diagnostics)}
