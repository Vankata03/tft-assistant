"""Target-independent whole-board declarations feed the shared likelihood math."""
from collections.abc import Mapping
from math import log

from tft_data import DataError, TaggedValue
from tft_engine import Board
from tft_engine.capacity import CapacityEvidence
from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, JointSightingPrediction, predict_joint_sighting
from tft_engine.opponents import round_index, unit_prior_rate

from .contracts import json_value


def sighting_law(data, *, opponent_id, round_id, level, previous=None, persistence=True):
    """Build support before any target traits or observed slot budget enter.

    Each source-declared weight describes a whole board, including correlations
    between forms, items and capacity. The existing fitted persistence model
    reweights that support; it does not turn trait marginals into an event law.
    """
    declaration = data.static.get('opponent_joint_support')
    if not isinstance(declaration, TaggedValue) or not isinstance(declaration.value, Mapping):
        raise DataError('joint_sighting_support_unavailable')
    raw = declaration.value
    state = data.sources.get(raw.get('provider'))
    if (not declaration.citation or state is None or state.qualified is not True
        or state.kind != 'statistics' or state.patch != data.patch
        or raw.get('patch') != data.patch or not state.cohort
        or any(value is None for value in state.cohort.values())
        or raw.get('cohort') != state.cohort
        or raw.get('source_updated_at') != state.updated_at.isoformat()):
        raise DataError('joint_sighting_support_unqualified')
    if previous is not None and (previous.opponent_id != opponent_id
        or round_index(previous.round_id, data) > round_index(round_id, data)):
        raise DataError('Joint persistence requires causal previous inference')
    rows = raw.get('rounds', {}).get(round_id, {}).get(str(level))
    if not isinstance(rows, (list, tuple)) or not rows:
        raise DataError('joint_sighting_support_context_unavailable')
    hypotheses = []
    for row in rows:
        board = Board.from_dict(json_value(row['board']))
        hypothesis = JointHypothesis(board, row['weight'],
            CapacityEvidence(**json_value(row.get('capacity', {}))), row.get('forms'))
        log_weight = (log(hypothesis.weight)
            if previous is not None and persistence and hypothesis.weight > 0 else None)
        if previous is not None and persistence:
            identities = set()
            for unit in board.units:
                entity = data.entities[unit.unit_id]
                pool = entity.values.get('pool_id') or entity.values.get('canonical_id')
                identity = pool.value if pool else unit.unit_id
                if identity in identities:
                    continue
                identities.add(identity)
                if log_weight is not None:
                    log_weight += log(unit_prior_rate(unit.unit_id, round_id, data, previous)) - log(
                        unit_prior_rate(unit.unit_id, round_id, data))
        hypotheses.append(JointHypothesis(board, hypothesis.weight, hypothesis.capacity,
            hypothesis.forms, log_weight=log_weight))
    return JointSightingLaw(data.snapshot_id, opponent_id, round_id, level, state.name,
        declaration.citation, tuple(hypotheses))


def forecast_sighting(sighting, data, *, previous=None, persistence=True):
    """Use the shared joint law, or the explicitly supported deterministic DP."""
    try:
        if 'opponent_joint_support' in data.static:
            law = sighting_law(data, opponent_id=sighting.opponent_id,
                round_id=sighting.round_id, level=sighting.level, previous=previous,
                persistence=persistence)
            return predict_joint_sighting(sighting, data, law)
        from tft_engine.sighting_prediction import predict_sighting

        result = predict_sighting(sighting, data, previous=previous if persistence else None)
        return JointSightingPrediction(result.probability, result.reason, result.model,
            log(result.probability) if result.probability is not None and result.probability > 0 else None)
    except (DataError, KeyError, TypeError, ValueError, AttributeError) as error:
        return JointSightingPrediction(None, str(error), None)
