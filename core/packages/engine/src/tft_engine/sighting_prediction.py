"""Normalized trait-event likelihood under explicitly supported unit-set priors."""
from dataclasses import dataclass

from tft_data import DataError

from .capacity import CapacityModel
from .opponents import infer_opponent, round_index, unit_prior_rate
from .power import keyed, tunable
from .trait_forms import unit_trait_variants


@dataclass(frozen=True)
class SightingPrediction:
    probability: float | None
    reason: str | None
    model: str = 'normalized_unit_set_prior/zero-emblem/deterministic-form'


def predict_sighting(sighting, data, *, previous=None):
    """Score the joint compatible-board event, never a product of marginals.

    This slice supports deterministic forms without latent emblem assignment.
    Other observation laws require explicit immutable joint inputs. A missing
    law remains unavailable rather than becoming a uniform game assumption.
    """
    if previous is not None and (previous.opponent_id != sighting.opponent_id
        or round_index(previous.round_id,data) > round_index(sighting.round_id,data)):
        raise DataError('Prediction requires causal previous inference for the same opponent')
    if int(tunable(data,'emblem_slack_max')) != 0:
        return SightingPrediction(None,'emblem_assignment_joint_law_unavailable')
    capacity = CapacityModel(data)
    if capacity.traits or capacity.augments or capacity.items:
        return SightingPrediction(None,'capacity_joint_law_unavailable')
    roster = sorted((entity for entity in data.entities.values() if entity.kind == 'unit'),key=lambda entity:entity.id)
    if any(len(unit_trait_variants(entity.id,data)) != 1 for entity in roster):
        return SightingPrediction(None,'active_form_joint_law_unavailable')
    posterior = infer_opponent(sighting,data,previous=previous)
    if posterior.evidence_mass is None:
        return SightingPrediction(None,posterior.fallback_reason or 'inference_normalizer_unavailable')
    budget = capacity.base(sighting.level)
    sizes = keyed(tunable(data,'size_level_prior'),sighting.level)
    zero_emblem = keyed(tunable(data,'emblem_count_prior'),0)
    if sizes is None or zero_emblem is None or zero_emblem <= 0:
        raise DataError('Positive zero-emblem and physical-size priors required')
    states = {(0,0):1.0}
    cap = data.tunables.get('opponent_inference_state_cap')
    for entity in roster:
        cost = capacity.cost(entity.id)
        rate = unit_prior_rate(entity.id,sighting.round_id,data,previous)
        following = dict(states)
        for (size,slots), mass in states.items():
            if size >= 28 or slots+cost > budget:
                continue
            key = (size+1,slots+cost)
            following[key] = following.get(key,0)+mass*rate
        if cap is not None and len(following) > cap.value:
            return SightingPrediction(None,'joint_prior_state_cap_exhausted')
        states = following
    normalizer = zero_emblem*sum(mass*float(keyed(sizes,size) or 0) for (size,_),mass in states.items())
    if normalizer <= 0:
        raise DataError('Unit-set prior has no positive legal mass')
    probability = posterior.evidence_mass/normalizer
    if not 0 <= probability <= 1+1e-9:
        raise DataError('Trait event mass exceeds normalized prior')
    return SightingPrediction(min(1,probability),None)
