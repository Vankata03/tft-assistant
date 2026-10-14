"""Offline family-2 margins from declared paired and model-gap uncertainty.

The caller supplies differences on a shared Engine rollout tape and draws of
that same guard difference under family-1 parameter uncertainty. This module
does not fit models, manufacture missing draws or publish accepted tunables.
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
