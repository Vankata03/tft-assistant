"""Declared bounded functional optimization on chronological training games."""
from dataclasses import dataclass
from itertools import product
from math import prod

from tft_data.config import TUNABLE_FAMILIES
from tft_review.contracts import frozen_json

from .measurement import mean_by_game
from .overlay import TunableOverlay


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


def fit(harness, parameter_grid, *, metric, bootstrap_seed, bootstrap_draws, max_candidates):
    from .evaluation import chronological_split
    if not parameter_grid or any(TUNABLE_FAMILIES.get(name) != '1' for name in parameter_grid):
        raise ValueError('Owner-log fitting accepts family 1 only')
    if any(not isinstance(values,(tuple,list)) or not values for values in parameter_grid.values()):
        raise ValueError('Fit requires an explicit nonempty candidate grid per parameter')
    if ('fight_scale' in parameter_grid and len(parameter_grid['fight_scale']) > 1
        and any(len(parameter_grid.get(name,())) > 1 for name in ('unit_weight','trait_weight','item_weight'))
        and not (len(parameter_grid.get('unit_weight',())) == 1)):
        raise ValueError('Joint power/scale fitting requires an explicit fixed unit-weight normalization')
    if type(max_candidates) is not int or max_candidates < 1 or prod(map(len,parameter_grid.values())) > max_candidates:
        raise ValueError('Declared fitting search budget exceeded')
    if harness.sessions.active_game_id:
        raise ValueError('A refit cannot run during an active game')
    games = harness.sessions.list_games()
    if harness.sessions.run:
        run_games = [game for game in games if game['pinned']]
        if any(not game['finished'] or game['placement'] is None for game in run_games) or len(run_games)%10:
            raise ValueError('During the run family 1 refits require a completed ten-game block boundary')
    training, holdout = chronological_split([game for game in games if game['finished']])
    if not training or not holdout:
        raise ValueError('Chronological fitting requires disjoint training and holdout games')
    baseline, original = harness._evaluate(training,harness.data_store)
    if metric not in baseline.metrics:
        raise ValueError('Fit objective is unavailable')
    reference_rows = [row for row in original if row['metric'] == metric]
    if not reference_rows:
        raise ValueError('Fit objective has no qualified training truth')
    keys = {(row['game_id'],row['observation_seq']) for row in reference_rows}
    reference = mean_by_game((row['game_id'],row['loss']) for row in reference_rows)
    tested, best = [], None
    names = tuple(sorted(parameter_grid))
    for values in product(*(parameter_grid[name] for name in names)):
        candidate = dict(zip(names,values))
        overlay = TunableOverlay(harness.data_store,candidate)
        _, rows = harness._evaluate(training,overlay,hook_version='fit:'+overlay.identity)
        rows = [row for row in rows if row['metric'] == metric]
        eligible = {(row['game_id'],row['observation_seq']) for row in rows} == keys
        objective = mean_by_game((row['game_id'],row['loss']) for row in rows) if eligible else None
        tested.append({'parameters':candidate,'objective':objective,
            'reason': None if objective is not None else 'infinite_loss_or_changed_eligible_truth'})
        if objective is not None and (best is None or objective < best[0]):
            best = (objective,candidate)
    if best is None:
        raise ValueError('No finite eligible candidate in declared fitting grid')
    evaluated = harness.evaluate(candidate=best[1],bootstrap_seed=bootstrap_seed,bootstrap_draws=bootstrap_draws)
    return FitReport(best[1],training,holdout,{'metric':metric,'reference':reference,
        'reference_reason':None if reference is not None else 'infinite_log_loss',
        'candidate':best[0],'weighting':'equal games'},evaluated.gates,
        {'method':'exhaustive declared grid','evaluations':len(tested),'candidates':tested,
         'convergence':'global minimum on supplied finite grid; continuous optimum not claimed',
         'publication':'unaccepted; owner Git commit required'})
