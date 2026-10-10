"""Trait-only inference; no opponent unit, item or position reads."""
from itertools import combinations
from .power import static

def unit_trait_variants(unit_id, data):
    entity = data.entities[unit_id]
    counts = {t: 1 for t in entity.traits}
    rules = data.static.get('trait_rules')
    pool = entity.values.get('pool_id') or entity.values.get('canonical_id')
    rule = rules.value.get(unit_id, rules.value.get(pool.value, {}) if pool else {}) if rules else {}
    if 'replace' in rule:
        result=tuple(dict(v) for v in rule['replace'])
        if entity.kind=='unit_form':
            result=tuple(v for v in result if set(v)==set(entity.traits))
            if not result:
                raise DataError(f'No trait rule matches active form: {unit_id}')
        return result
    counts.update(rule.get('counts', {}))
    choices = rule.get('choose_one', ({},))
    optional = tuple(rule.get('optional_traits', ()))
    result = []
    for choice in choices:
        for size in range(len(optional) + 1):
            for subset in combinations(optional, size):
                value = dict(counts)
                for trait, count in choice.items():
                    value[trait] = value.get(trait, 0) + int(count)
                for trait in subset:
                    value[trait] = value.get(trait, 0) + 1
                if value not in result:
                    result.append(value)
    if entity.kind=='unit_form' and pool and rule:
        result=[v for v in result if set(v)==set(entity.traits)]
        if not result:
            raise DataError(f'No trait rule matches active form: {unit_id}')
    return tuple(result)

from dataclasses import dataclass
from math import exp, log
from typing import Mapping
from tft_data.models import DataError, freeze
from .models import TraitSighting
from .power import tunable, keyed

@dataclass(frozen=True)
class InferredBoard:
    opponent_id: str
    round_id: str
    level: int
    probabilities: Mapping[str, float]
    certainty: float
    candidate_count: int
    fallback_reason: str | None = None
    def __post_init__(self):
        object.__setattr__(self, 'probabilities', freeze(self.probabilities))


def round_index(round_id, data):
    order = data.static.get('round_order')
    if order:
        try:
            return tuple(order.value).index(round_id)
        except ValueError:
            raise DataError(f'Unknown round: {round_id}') from None
    # TFT stage identifiers have seven rounds; this is chronology, not a fitted parameter.
    stage, phase = map(int, round_id.split('-'))
    return (stage - 1) * 7 + phase


def age_weight(rounds_old, data):
    full = float(tunable(data, 'sighting_full_weight_rounds'))
    half_life = float(tunable(data, 'sighting_half_life_rounds'))
    if half_life <= 0:
        raise DataError('Sighting half life must be positive')
    return 2 ** (-max(0, rounds_old - full) / half_life)


def unit_play_rate(unit_id, data):
    stats = [s for s in data.statistics if s.entity_id == unit_id and getattr(s, 'play_rate', None) is not None]
    stats.sort(key=lambda s: (s.source != 'tactics.tools', s.stale, s.changed))
    if stats:
        rate = float(stats[0].play_rate)
    else:
        tagged = data.entities[unit_id].values.get('play_rate')
        if tagged is None:
            raise DataError(f'Missing unit play rate: {unit_id}')
        rate = float(tagged.value)
    if not 0 < rate <= 1:
        raise DataError(f'Invalid unit play rate: {unit_id}')
    return rate


def infer_opponent(sighting: TraitSighting, data, *, previous: InferredBoard | None = None) -> InferredBoard:
    visible = sighting.traits
    hidden = sighting.hidden_traits
    slack = int(tunable(data, 'emblem_slack_max'))
    first_breakpoint = {}
    for entity in data.entities.values():
        if entity.kind == 'trait':
            value = entity.values.get('breakpoints')
            if value is None or not value.value:
                raise DataError(f'Missing trait breakpoints: {entity.id}')
            first_breakpoint[entity.id] = min(map(int, value.value))
    for trait in visible:
        if trait not in first_breakpoint:
            raise DataError(f'Unknown sighting trait: {trait}')
    previous_age = age_weight(max(0, round_index(sighting.round_id,data) - round_index(previous.round_id,data)),data) if previous else 0
    boost = float(tunable(data, 'sighting_persistence_weight'))
    roster = []
    for entity in sorted(data.entities.values(), key=lambda e:e.id):
        if entity.kind != 'unit':
            continue
        variants = []
        for counts in unit_trait_variants(entity.id, data):
            if any(t not in first_breakpoint for t in counts):
                raise DataError(f'Unknown trait grant for {entity.id}')
            if any(counts.get(t,0) > count for t,count in visible.items()):
                continue
            outside = {t:n for t,n in counts.items() if t not in visible and n > 0}
            if len(outside) > hidden or any(n >= first_breakpoint[t] for t,n in outside.items()):
                continue
            variants.append(counts)
        if not variants:
            continue
        rate = unit_play_rate(entity.id,data)
        if previous:
            rate *= 1 + (boost - 1) * previous.probabilities.get(entity.id,0) * previous_age
        roster.append((entity.id, tuple(variants), log(rate)))
    # Suffix capacities prune branches that cannot fill visible counts, even with emblems.
    suffix = [{t:0 for t in visible} for _ in range(len(roster)+1)]
    for i in range(len(roster)-1,-1,-1):
        suffix[i] = {t:suffix[i+1][t] + max(v.get(t,0) for v in roster[i][1]) for t in visible}
    size_table = keyed(tunable(data,'size_level_prior'),sighting.level)
    if not isinstance(size_table, Mapping):
        raise DataError(f'Missing size prior for level {sighting.level}')
    emblem_prior = tunable(data,'emblem_count_prior')
    # A state stores all feasible trait vectors for a distinct unit set. Grouping
    # equivalent vector families is exact even when a unit has several forms;
    # alternative forms never become extra posterior votes for that unit set.
    traits=tuple(sorted(first_breakpoint))
    trait_index={t:i for i,t in enumerate(traits)}
    empty=(0,)*len(traits)
    states={((empty,),0):(1.0,1,1.0,{})}
    tagged_cap=data.tunables.get('opponent_inference_state_cap')
    cap=int(tagged_cap.value) if tagged_cap else None
    if cap is not None and cap<1:
        raise DataError('Opponent inference state cap must be positive')
    def feasible(counts):
        if any(counts[trait_index[t]]>n for t,n in visible.items()):
            return False
        outside=[(t,counts[i]) for i,t in enumerate(traits) if t not in visible and counts[i]]
        return len(outside)<=hidden and all(n<first_breakpoint[t] for t,n in outside)
    for unit_id,variants,log_prior in roster:
        rate=exp(log_prior)
        vectors=tuple(set(tuple(v.get(t,0) for t in traits) for v in variants))
        next_states=dict(states)
        for (family,size),(weight,number,maximum,moments) in states.items():
            if size>=sighting.level:
                continue
            merged=tuple(sorted({tuple(a+b for a,b in zip(counts,vector)) for counts in family for vector in vectors if feasible(tuple(a+b for a,b in zip(counts,vector)))}))
            if not merged:
                continue
            key=(merged,size+1)
            old_weight,old_number,old_maximum,old_moments=next_states.get(key,(0.0,0,0.0,{}))
            updated=dict(old_moments)
            for id,moment in moments.items():
                updated[id]=updated.get(id,0.0)+moment*rate
            updated[unit_id]=updated.get(unit_id,0.0)+weight*rate
            next_states[key]=(old_weight+weight*rate,old_number+number,max(old_maximum,maximum*rate),updated)
            if cap is not None and len(next_states)>cap:
                return InferredBoard(sighting.opponent_id,sighting.round_id,sighting.level,{},0.0,0,f'Opponent inference state cap {cap} exhausted; no posterior retained')
        states=next_states
    total=maximum=0.0
    candidate_count=0
    moments={}
    for (family,size),(weight,number,top,first_moments) in states.items():
        best_prior=0.0
        for counts in family:
            outside={t:counts[i] for i,t in enumerate(traits) if t not in visible and counts[i]}
            missing_hidden=hidden-len(outside)
            possible_hidden=sum(t not in visible and t not in outside and first_breakpoint[t]>1 for t in traits)
            if missing_hidden>possible_hidden:
                continue
            residual=sum(n-counts[trait_index[t]] for t,n in visible.items())+missing_hidden
            if residual>slack:
                continue
            emblem,size_prior=keyed(emblem_prior,residual),keyed(size_table,size)
            if emblem is not None and size_prior is not None and emblem>0 and size_prior>0:
                best_prior=max(best_prior,float(emblem)*float(size_prior))
        if not best_prior:
            continue
        total+=weight*best_prior
        maximum=max(maximum,top*best_prior)
        candidate_count+=number
        for unit_id,moment in first_moments.items():
            moments[unit_id]=moments.get(unit_id,0.0)+moment*best_prior
    return InferredBoard(sighting.opponent_id,sighting.round_id,sighting.level,{id:moment/total for id,moment in moments.items()} if total else {},maximum/total if total else 0.0,candidate_count)

@dataclass(frozen=True)
class OpponentEstimate:
    opponent_id: str
    power: float
    level: int
    confidence: float
    age_weight: float
    inference_certainty: float
    probabilities: Mapping[str, float]
    expected_copies: Mapping[str, float]
    labels: tuple
    warnings: tuple[str, ...] = ()
    data_confidence: float = 1.0
    def __post_init__(self):
        object.__setattr__(self,'probabilities',freeze(self.probabilities))
        object.__setattr__(self,'expected_copies',freeze(self.expected_copies))


def estimate_opponent(sighting: TraitSighting | None, inferred: InferredBoard | None, round_id, data, *, opponent_id='', curve=None):
    from .growth import standard_level, growth_curve_lookup, expected_unit_power, average_unit_power, star_mix
    from .power import trait_term, stage_items
    from .classifier import classify
    if sighting is None or inferred is None or not inferred.candidate_count:
        return OpponentEstimate(sighting.opponent_id if sighting else opponent_id,growth_curve_lookup(round_id,data,curve=curve),standard_level(round_id,data),0.0,age_weight(max(0,round_index(round_id,data)-round_index(sighting.round_id,data)),data) if sighting else 0.0,0.0,{}, {},(),((inferred.fallback_reason if inferred and inferred.fallback_reason else 'No supported inference; par growth used'),))
    if inferred.opponent_id != sighting.opponent_id or inferred.round_id != sighting.round_id:
        raise ValueError('Inference does not match its sighting')
    rounds_old = max(0,round_index(round_id,data)-round_index(sighting.round_id,data))
    freshness = age_weight(rounds_old,data)
    units = 0.0
    data_confidence = 1.0
    warnings = []
    for unit_id,probability in inferred.probabilities.items():
        power,certainty,flags = expected_unit_power(unit_id,sighting.round_id,data)
        units += probability * power
        data_confidence = min(data_confidence, certainty)
        warnings.extend(flags)
    filler = max(0.0,sighting.level-sum(inferred.probabilities.values()))
    units += filler * average_unit_power(sighting.level,sighting.round_id,data)
    traits, trait_confidence, flags = trait_term(sighting.traits,data)
    data_confidence = min(data_confidence, trait_confidence)
    for name in ('unit_weight','trait_weight','item_weight','opponent_star_mix','emblem_count_prior','size_level_prior'):
        if data.tunables[name].source in ('default','carried'):
            data_confidence = min(data_confidence,float(tunable(data,'confidence_medium_min')))
            warnings.append(f'{name}: {data.tunables[name].source}')
    warnings.extend(flags)
    stage = int(sighting.round_id.split('-')[0])
    power = units * float(tunable(data,'unit_weight')) + traits * float(tunable(data,'trait_weight')) + stage_items(stage,data) * float(tunable(data,'item_weight'))
    power += growth_curve_lookup(round_id,data,curve=curve)-growth_curve_lookup(sighting.round_id,data,curve=curve)
    level = max(sighting.level,standard_level(round_id,data))
    copies = {}
    for unit_id,probability in inferred.probabilities.items():
        shares = star_mix(round_id,data.entities[unit_id].cost,data)
        copies[unit_id] = probability * sum(p*n for p,n in zip(shares,(1,3,9))) * freshness
    return OpponentEstimate(sighting.opponent_id,power,level,freshness*inferred.certainty*data_confidence,freshness,inferred.certainty,inferred.probabilities,copies,classify(inferred.probabilities,data),tuple(warnings),data_confidence)


def opponents_from_history(history, round_id, data, *, opponent_ids=(), curve=None):
    previous = {}
    sightings = {}
    for sighting in sorted(history.sightings,key=lambda s:round_index(s.round_id,data)):
        if round_index(sighting.round_id,data) > round_index(round_id,data):
            continue
        inferred = infer_opponent(sighting,data,previous=previous.get(sighting.opponent_id))
        previous[sighting.opponent_id] = inferred
        sightings[sighting.opponent_id] = sighting
    ids = sorted(set(opponent_ids) | set(sightings))
    return tuple(estimate_opponent(sightings.get(id),previous.get(id),round_id,data,opponent_id=id,curve=curve) for id in ids)
