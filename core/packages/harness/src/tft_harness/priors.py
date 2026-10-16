"""Family-3 priors from public statistics by empirical Bayes (``fit --priors``).

Only current-patch, non-stale statistics rows enter. A patch's priors are
recomputed only once its statistics pass about 500 boards; until then the
committed priors stay. The board count is a lower bound: the largest sample
count of any eligible row, because every row's boards belong to the patch.

Estimators, matched to how the Engine applies each prior:

- ``cost_star_baseline``: per cost and star, the sample-weighted top-4 rate
  of the current patch on the lobby logit scale.
- ``unit_prior_strength`` and ``trait_prior_strength``: the beta-binomial
  marginal-likelihood maximum of the prior sample size, centred on the
  cost-star prior and the lobby rate respectively.
- ``item_class_prior`` and ``item_prior_strength``: a normal hierarchical
  model of item placement deltas; class means and the method-of-moments
  between-row variance give the prior strength as noise over signal variance.

Augment priors stay carried until augment statistics and a cross-patch
holdout exist. Nothing here publishes data; results go to a candidate file.
"""
from dataclasses import dataclass, field
from math import exp, isfinite, lgamma, log

from tft_data.config import STATISTICS_MIN_SAMPLES
from tft_data.models import plain
from tft_engine.power import lobby_rate, logit, sigmoid

FAMILY_3 = ('cost_star_baseline', 'unit_prior_strength', 'trait_prior_strength',
    'item_class_prior', 'item_prior_strength', 'augment_prior_strength', 'augment_flag_prior_multiplier')
# Variance of a lobby's placements 1..8 when a row reports no variance.
LOBBY_PLACEMENT_VARIANCE = 63/12
_STRENGTH_BOUNDS = (1e-2, 1e6)


@dataclass(frozen=True)
class PriorFit:
    status: str
    patch: str
    boards: int
    min_boards: int
    fields: dict = field(default_factory=dict)
    carried: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)


def _golden_log(objective, low, high, *, iterations=80):
    """Maximize a unimodal function of log strength; returns (value, at upper bound)."""
    ratio = (5**.5-1)/2
    a, b = log(low), log(high)
    c, d = b-ratio*(b-a), a+ratio*(b-a)
    fc, fd = objective(exp(c)), objective(exp(d))
    for _ in range(iterations):
        if fc >= fd:
            b, d, fd = d, c, fc
            c = b-ratio*(b-a)
            fc = objective(exp(c))
        else:
            a, c, fc = c, d, fd
            d = a+ratio*(b-a)
            fd = objective(exp(d))
    point = exp((a+b)/2)
    return point, point >= high*.99


def _beta_binomial_strength(rows):
    """rows: (successes, trials, prior mean). Returns (strength or None, reason)."""
    rows = [(k, n, m) for k, n, m in rows if n > 0 and 0 < m < 1]
    if len(rows) < 2:
        return None, 'insufficient_rows'

    def likelihood(strength):
        return sum(lgamma(strength)-lgamma(strength*m)-lgamma(strength*(1-m))
            +lgamma(k+strength*m)+lgamma(n-k+strength*(1-m))-lgamma(n+strength) for k, n, m in rows)

    strength, unbounded = _golden_log(likelihood, *_STRENGTH_BOUNDS)
    if unbounded:
        return None, 'no_overdispersion_prior_unbounded'
    return strength, None


def _unit_rows(rows, data):
    for row in rows:
        entity = data.entities.get(row.entity_id)
        if (row.kind == 'unit' and row.unit_star is not None and row.item_id is None and row.comp_id is None
                and row.top4_rate is not None and entity is not None and entity.kind in ('unit', 'unit_form')):
            yield row, entity


def fit_priors(data, *, min_boards=STATISTICS_MIN_SAMPLES):
    rows = [row for row in data.statistics if row.patch == data.patch and not row.stale]
    boards = max((row.sample_count for row in rows), default=0)
    if boards < min_boards:
        return PriorFit('insufficient_boards', data.patch, boards, min_boards,
            carried={name: 'insufficient_boards' for name in FAMILY_3})
    lobby = lobby_rate(data)
    fields, carried, diagnostics = {}, {}, {}

    committed = plain(data.tunables['cost_star_baseline'].value)
    pooled = {}
    for row, entity in _unit_rows(rows, data):
        cell = pooled.setdefault((str(entity.cost), str(row.unit_star)), [0.0, 0])
        cell[0] += row.top4_rate*row.sample_count
        cell[1] += row.sample_count
    baseline = {cost: dict(stars) for cost, stars in committed.items()}
    cells = {}
    for (cost, stars), (wins, samples) in sorted(pooled.items()):
        if samples and 0 < wins/samples < 1:
            baseline.setdefault(cost, {})[stars] = logit(wins/samples)-logit(lobby)
            cells[f'{cost}/{stars}'] = samples
    if cells:
        fields['cost_star_baseline'] = baseline
        diagnostics['cost_star_baseline'] = {'cells': cells, 'scale': 'logit(top4) - logit(lobby)'}
    else:
        carried['cost_star_baseline'] = 'no_current_unit_star_statistics'

    unit_evidence = []
    for row, entity in _unit_rows(rows, data):
        prior = baseline.get(str(entity.cost), {}).get(str(row.unit_star))
        if prior is not None:
            unit_evidence.append((row.top4_rate*row.sample_count, row.sample_count,
                sigmoid(logit(lobby)+float(prior))))
    trait_evidence = [(row.top4_rate*row.sample_count, row.sample_count, lobby) for row in rows
        if row.kind == 'trait' and row.breakpoint is not None and row.top4_rate is not None]
    for name, evidence in (('unit_prior_strength', unit_evidence), ('trait_prior_strength', trait_evidence)):
        strength, reason = _beta_binomial_strength(evidence)
        if strength is None:
            carried[name] = reason
        else:
            fields[name] = strength
            diagnostics[name] = {'rows': len(evidence), 'method': 'beta-binomial marginal likelihood'}

    class_rows = {}
    for row in rows:
        if row.item_id is None:
            continue
        unit, item = data.entities.get(row.entity_id), data.entities.get(row.item_id)
        base = max((other for other in rows if other.entity_id == row.entity_id and other.kind == 'unit'
            and other.item_id is None), key=lambda other: other.sample_count, default=None)
        if (base is None or unit is None or item is None or row.sample_count <= 0
                or 'item_class' not in unit.values or 'item_class' not in item.values):
            continue
        variance = row.variance if row.variance is not None and isfinite(row.variance) and row.variance > 0 \
            else LOBBY_PLACEMENT_VARIANCE
        key = (str(unit.values['item_class'].value), str(item.values['item_class'].value))
        class_rows.setdefault(key, []).append((base.average_placement-row.average_placement,
            row.sample_count, variance))
    evidence = sum(len(values) for values in class_rows.values())
    if evidence < 2:
        carried['item_class_prior'] = carried['item_prior_strength'] = 'insufficient_item_rows'
    else:
        classes = {key: sum(d*n for d, n, _ in values)/sum(n for _, n, _ in values)
            for key, values in class_rows.items()}
        table = {unit: dict(items) for unit, items in plain(data.tunables['item_class_prior'].value).items()}
        for (unit, item), mean in classes.items():
            table.setdefault(unit, {})[item] = mean
        fields['item_class_prior'] = table
        residual = [((d-classes[key])**2-variance/n, variance)
            for key, values in class_rows.items() for d, n, variance in values]
        between = sum(value for value, _ in residual)/len(residual)
        if between <= 0:
            carried['item_prior_strength'] = 'no_between_row_variance'
        else:
            fields['item_prior_strength'] = (sum(variance for _, variance in residual)/len(residual))/between
            diagnostics['item_prior_strength'] = {'rows': len(residual), 'between_row_variance': between,
                'method': 'normal hierarchical method of moments'}
    carried['augment_prior_strength'] = ('augment_statistics_unavailable'
        if not any(row.kind == 'augment' for row in rows) else 'augment_prior_fit_not_implemented')
    carried['augment_flag_prior_multiplier'] = 'cross_patch_holdout_unavailable'
    return PriorFit('candidate' if fields else 'no_estimable_priors', data.patch, boards, min_boards,
        fields, carried, diagnostics)
