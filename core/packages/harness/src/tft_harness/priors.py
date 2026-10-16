"""Fit family-3 priors from explicitly qualified public aggregate cohorts.

``evidence`` is a JSON object with schema ``public_prior_cohorts_v1`` and
``cohorts``. Each cohort binds id, patch, source (metatft or tactics.tools),
HTTPS citation, timezone-aware start/end/updated_at, distinct_boards and rows.
The qualification object must explicitly certify public_aggregate,
distinct_boards and independent_rows. These are producer attestations, not
qualification inferred from raw Statistic rows. The caller must verify them
against the cited publication. No owner logs enter this estimator.

Unit/trait rows contain exact integer successes/trials and unit_star or
breakpoint. Item rows contain entity_id, item_id, trials, mean placement gain
and variance of the matched placement contrast, including baseline uncertainty.
Augment rows contain entity_id, trials, mean placement delta, variance and the
qualified tier prior_mean on the same scale. Variances are individual-outcome
variances, not variances of means. Row identities must be unique and the cohort
producer must certify independent sampling units (no overlapping fitted rows).

Current-patch fits use only the latest qualified cohort. Explicit distinct
boards gate the fit; entity sample counts never establish patch population.
Beta-binomial marginal likelihood estimates binomial strengths. Normal
hierarchical moments estimate placement strengths without inventing variance.
The flag multiplier uses flagged early/late pairs from disjoint cohorts across
patches, training on older patches and checking the newest unseen patch.
Missing evidence carries committed fields. All outputs remain candidates.
"""
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse
from math import exp, isfinite, lgamma, log

from tft_data.config import STATISTICS_MIN_SAMPLES
from tft_data.models import plain
from tft_engine.power import lobby_rate, logit, sigmoid

FAMILY_3 = ('cost_star_baseline', 'unit_prior_strength', 'trait_prior_strength',
    'item_class_prior', 'item_prior_strength', 'augment_prior_strength', 'augment_flag_prior_multiplier')
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


def _integer(value, label, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{label} requires an exact integer >= {minimum}')
    return value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise ValueError(f'{label} requires a finite number')
    return value


def _time(value):
    try:
        result = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError('Cohort times require ISO timestamps') from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Cohort times require timezones')
    return result


def _cohorts(evidence, data):
    if not isinstance(evidence, dict) or evidence.get('schema') != 'public_prior_cohorts_v1':
        raise ValueError('Public prior evidence requires public_prior_cohorts_v1 schema')
    cohorts = evidence.get('cohorts')
    if not isinstance(cohorts, list):
        raise ValueError('Public prior evidence requires a cohort list')
    identities, qualified = set(), []
    for original in cohorts:
        if not isinstance(original, dict):
            raise ValueError('Public prior cohort must be an object')
        cohort = dict(original)
        for key in ('id', 'patch', 'source', 'citation'):
            if not isinstance(cohort.get(key), str) or not cohort[key].strip():
                raise ValueError(f'Cohort requires {key}')
        if cohort['id'] in identities:
            raise ValueError('Duplicate public cohort id')
        identities.add(cohort['id'])
        citation = urlparse(cohort['citation'])
        host = citation.hostname or ''
        domain = {'metatft': 'metatft.com', 'tactics.tools': 'tactics.tools'}.get(cohort['source'])
        if (domain is None or citation.scheme != 'https' or citation.username or citation.password
                or not (host == domain or host.endswith('.'+domain))):
            raise ValueError('Cohort requires a public provider HTTPS citation bound to its source')
        qualification = cohort.get('qualification', {})
        if not isinstance(qualification, dict) or any(qualification.get(key) is not True
                for key in ('public_aggregate', 'distinct_boards', 'independent_rows')):
            raise ValueError('Cohort requires explicit public/distinct-board/independent-row qualification')
        start, end, updated = (_time(cohort.get(key)) for key in ('start', 'end', 'updated_at'))
        if not start < end <= updated:
            raise ValueError('Cohort must bind ordered source observation and publication times')
        _integer(cohort.get('distinct_boards'), 'distinct_boards')
        rows = cohort.get('rows')
        if not isinstance(rows, list):
            raise ValueError('Cohort requires aggregate rows')
        keys = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Cohort row must be an object')
            kind = row.get('kind')
            entity = data.entities.get(row.get('entity_id'))
            expected = 'unit' if kind == 'item' else kind
            if kind not in ('unit', 'trait', 'item', 'augment') or entity is None or entity.kind not in (
                    ('unit', 'unit_form') if expected == 'unit' else (expected,)):
                raise ValueError('Cohort row requires a known matching entity')
            trials = _integer(row.get('trials'), 'trials', minimum=1)
            if kind in ('unit', 'trait'):
                successes = _integer(row.get('successes'), 'successes')
                if successes > trials:
                    raise ValueError('successes cannot exceed trials')
                key = 'unit_star' if kind == 'unit' else 'breakpoint'
                _integer(row.get(key), key, minimum=1)
                if kind == 'unit' and entity.cost is None:
                    raise ValueError('Unit prior evidence requires a cost')
            else:
                _number(row.get('mean'), 'placement delta')
                if _number(row.get('variance'), 'placement variance') <= 0:
                    raise ValueError('Placement variance must be positive')
                if not -7 <= row['mean'] <= 7:
                    raise ValueError('Placement delta must lie in [-7, 7]')
                if kind == 'item':
                    item = data.entities.get(row.get('item_id'))
                    if item is None or item.kind != 'item' or any('item_class' not in e.values for e in (entity, item)):
                        raise ValueError('Item prior evidence requires known holder/item classes')
                else:
                    _number(row.get('prior_mean'), 'augment tier prior mean')
                    if not -7 <= row['prior_mean'] <= 7 or type(row.get('flagged', False)) is not bool:
                        raise ValueError('Invalid augment prior or flag')
            key = (kind, row['entity_id'], row.get('unit_star'), row.get('breakpoint'), row.get('item_id'))
            if key in keys:
                raise ValueError('Duplicate aggregate row identity')
            keys.add(key)
        if sum(row['trials'] for row in rows) > cohort['distinct_boards']:
            raise ValueError('Independent aggregate rows exceed the certified distinct-board population')
        cohort['_start'], cohort['_end'] = start, end
        qualified.append(cohort)
    for index, cohort in enumerate(qualified):
        for other in qualified[:index]:
            if cohort['patch'] == other['patch'] and max(cohort['_start'], other['_start']) < min(cohort['_end'], other['_end']):
                raise ValueError('Public cohort observation windows overlap within a patch')
    return sorted(qualified, key=lambda row: (row['_end'], row['id']))


def _normal_strength(rows):
    """Rows are (mean, outcome variance, count, prior mean)."""
    if len(rows) < 2:
        return None, 'insufficient_rows'
    between = sum((mean-prior)**2-variance/n for mean, variance, n, prior in rows)/len(rows)
    if between <= 0:
        return None, 'no_between_row_variance'
    return sum(variance for _, variance, _, _ in rows)/len(rows)/between, None


def _temporal_multiplier(cohorts, strength, reference):
    pairs = []
    patches = sorted({c['patch'] for c in cohorts}, key=lambda patch:
        min(c['_start'] for c in cohorts if c['patch'] == patch))
    for patch in patches:
        current = [c for c in cohorts if c['patch'] == patch]
        if len(current) < 2:
            continue
        early, late = current[0], current[-1]
        if early['source'] != late['source']:
            continue
        targets = {r['entity_id']: r for r in late['rows'] if r['kind'] == 'augment'}
        rows = []
        for row in early['rows']:
            target = targets.get(row['entity_id'])
            if (row['kind'] == 'augment' and row.get('flagged') is True and target is not None
                    and row['prior_mean'] == target['prior_mean']):
                rows.append((row, target))
        if rows:
            pairs.append((patch, rows))
    if len(pairs) < 2:
        return None, 'cross_patch_holdout_unavailable', None
    training, holdout = pairs[:-1], pairs[-1]
    holdout_start = min(c['_start'] for c in cohorts if c['patch'] == holdout[0])
    if any(c['_end'] > holdout_start for c in cohorts if c['patch'] in {p for p, _ in training}):
        return None, 'nonchronological_cross_patch_holdout', None
    def loss(multiplier, groups):
        values = []
        for _, rows in groups:
            # Equal weight per patch; normal target likelihood up to constants.
            values.append(sum(((r['trials']*r['mean']+strength*multiplier*r['prior_mean'])
                /(r['trials']+strength*multiplier)-t['mean'])**2/(t['variance']/t['trials'])
                for r, t in rows)/len(rows))
        return sum(values)/len(values)
    candidate, bounded = _golden_log(lambda value: -loss(value, training), 1., 1000.)
    if bounded:
        return None, 'temporal_optimum_at_bound', None
    candidate_loss, reference_loss = loss(candidate, [holdout]), loss(reference, [holdout])
    diagnostics = {'method': 'normal temporal prediction loss; equal patches',
        'training_patches': [patch for patch, _ in training], 'holdout_patch': holdout[0],
        'candidate_loss': candidate_loss, 'reference_loss': reference_loss,
        'strength': strength, 'bounds': [1., 1000.]}
    return (candidate, None, diagnostics) if candidate_loss <= reference_loss else (
        None, 'temporal_holdout_regression', diagnostics)


def fit_priors(data, *, evidence=None, min_boards=STATISTICS_MIN_SAMPLES):
    """Produce unaccepted prior candidates; raw rounded statistics cannot qualify."""
    _integer(min_boards, 'min_boards', minimum=1)
    if evidence is None:
        return PriorFit('unqualified_public_evidence', data.patch, 0, min_boards,
            carried={name: 'qualified_public_cohorts_unavailable' for name in FAMILY_3})
    cohorts = _cohorts(evidence, data)
    current = [cohort for cohort in cohorts if cohort['patch'] == data.patch]
    selected = current[-1] if current else None
    boards = selected['distinct_boards'] if selected else 0
    if boards < min_boards:
        return PriorFit('insufficient_boards', data.patch, boards, min_boards,
            carried={name: 'insufficient_boards' for name in FAMILY_3})
    rows = selected['rows']
    fields, carried = {}, {}
    diagnostics = {'cohort': {key: selected[key] for key in (
        'id', 'patch', 'source', 'citation', 'updated_at', 'start', 'end', 'distinct_boards', 'qualification')}}
    lobby = lobby_rate(data)
    baseline = {cost: dict(stars) for cost, stars in plain(data.tunables['cost_star_baseline'].value).items()}
    pooled = {}
    for row in rows:
        if row['kind'] == 'unit':
            key = (str(data.entities[row['entity_id']].cost), str(row['unit_star']))
            cell = pooled.setdefault(key, [0, 0])
            cell[0] += row['successes']
            cell[1] += row['trials']
    for (cost, stars), (successes, trials) in pooled.items():
        if 0 < successes < trials:
            baseline.setdefault(cost, {})[stars] = logit(successes/trials)-logit(lobby)
    if any(0 < k < n for k, n in pooled.values()):
        fields['cost_star_baseline'] = baseline
    else:
        carried['cost_star_baseline'] = 'no_interior_unit_star_statistics'
    for kind, name in (('unit', 'unit_prior_strength'), ('trait', 'trait_prior_strength')):
        observations = []
        for row in rows:
            if row['kind'] != kind:
                continue
            if kind == 'unit':
                prior = baseline.get(str(data.entities[row['entity_id']].cost), {}).get(str(row['unit_star']))
                if prior is None:
                    continue
                mean = sigmoid(logit(lobby)+float(prior))
            else:
                mean = lobby
            observations.append((row['successes'], row['trials'], mean))
        strength, reason = _beta_binomial_strength(observations)
        if strength is None:
            carried[name] = reason
        else:
            fields[name] = strength
            diagnostics[name] = {'rows': len(observations), 'method': 'beta-binomial marginal likelihood'}
    classes = {}
    for row in rows:
        if row['kind'] == 'item':
            unit, item = (data.entities[row[key]] for key in ('entity_id', 'item_id'))
            key = (str(unit.values['item_class'].value), str(item.values['item_class'].value))
            classes.setdefault(key, []).append(row)
    means = {key: sum(r['mean']*r['trials'] for r in values)/sum(r['trials'] for r in values)
        for key, values in classes.items()}
    if means:
        table = {unit: dict(items) for unit, items in plain(data.tunables['item_class_prior'].value).items()}
        for (unit, item), mean in means.items():
            table.setdefault(unit, {})[item] = mean
        fields['item_class_prior'] = table
    else:
        carried['item_class_prior'] = 'insufficient_item_rows'
    item_rows = [(r['mean'], r['variance'], r['trials'], means[key])
        for key, values in classes.items() for r in values]
    augment_rows = [(r['mean'], r['variance'], r['trials'], r['prior_mean'])
        for r in rows if r['kind'] == 'augment' and not r.get('flagged', False)]
    for name, observations in (('item_prior_strength', item_rows), ('augment_prior_strength', augment_rows)):
        strength, reason = _normal_strength(observations)
        if strength is None:
            carried[name] = reason
        else:
            fields[name] = strength
            diagnostics[name] = {'rows': len(observations), 'method': 'normal hierarchical method of moments'}
    # Keep this strength fixed across temporal patches; do not learn it from the held-out patch.
    strength = float(data.tunables['augment_prior_strength'].value)
    reference = float(data.tunables['augment_flag_prior_multiplier'].value)
    if strength <= 0 or not isfinite(strength) or reference < 1 or not isfinite(reference):
        multiplier, reason, detail = None, 'qualified_fixed_augment_prior_unavailable', None
    else:
        multiplier, reason, detail = _temporal_multiplier(cohorts, strength, reference)
    if multiplier is None:
        carried['augment_flag_prior_multiplier'] = reason
    else:
        # The holdout used the committed strength. Jointly changing it would invalidate that test.
        if 'augment_prior_strength' in fields:
            fields.pop('augment_prior_strength')
            carried['augment_prior_strength'] = 'fixed_for_temporal_multiplier_holdout'
        fields['augment_flag_prior_multiplier'] = multiplier
    if detail:
        diagnostics['augment_flag_prior_multiplier'] = detail
    diagnostics['public_cohorts'] = [{key: c[key] for key in (
        'id', 'patch', 'source', 'citation', 'updated_at', 'start', 'end')} for c in cohorts]
    return PriorFit('candidate' if fields else 'no_estimable_priors', data.patch, boards, min_boards,
        fields, carried, diagnostics)
