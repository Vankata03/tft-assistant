"""The pure Engine. Baseline callers import only tft_engine.allowlist."""
from .models import Advice, Board, FieldValue, GameHistory, GameSnapshot, TraitSighting, Unit, rank_advice
from .power import PowerEstimate, estimate_strength, strength, win_probability, placement, surviving_units
from .classifier import CompSimilarity, classify
from .opponents import InferredBoard, infer_opponent, age_weight
from .models import ScoredOption
from .growth import growth_curve, growth_curve_lookup, standard_level, star_mix
from .opponents import OpponentEstimate, estimate_opponent, opponents_from_history
from .planning import advise
from .planning import GamePlan, EngineEvaluation, EngineContext, evaluate
from .registry import FitTerm, DomainHook
from .lines import Line, LineResult, SimulationEffects, simulate_lines, snapshot_seed
from .comp_fit import CompFit
from .planning import best_choice_fit
from .lines import paired_value, candidate_lines
