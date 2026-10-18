"""Pure Game plan/history fold and per-domain advice orchestration."""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Mapping
from tft_data.models import DataError, Guide, freeze
from .models import Advice, ScoredOption, Board, Unit, rank_advice, _encode
from .power import tunable, estimate_strength, stage_tunable, item_category
from .lines import Line, guide_line, simulate_lines, candidate_lines, concrete_lines, snapshot_seed
from .opponents import opponents_from_history, round_index
from .classifier import classify
from .registry import FitTerm, DomainHook
from .comp_fit import CompFit, screen_comp, rounds_left_to_live
from .transition import strongest_owned_board, transition_advice
from .shop_math import hit_probability, owned_copies, key_goals, canonical_id
from .preparation import evaluation_scope, patch_calculation

@dataclass(frozen=True)
class GamePlan:
    status: str = 'open'
    target: str | None = None
    backup: str | None = None
    candidates: tuple[str,...] = ()
    line: Line | None = None
    pivot_from: str | None = None
    pivot_to: str | None = None
    rejected_target: str | None = None
    player_label: str | None = None
    divergence_round: str | None = None
    planning_round: str | None = None
    target_similarity: float = 0.0
    pivot_round: str | None = None
    observed_transition: Mapping | None = None
    divergence_snapshot_id: str | None = None
    def __post_init__(self):
        if self.observed_transition is not None:
            object.__setattr__(self, 'observed_transition', freeze(self.observed_transition))
    def to_dict(self):
        return _encode(self)

@dataclass(frozen=True)
class EngineEvaluation:
    plan: GamePlan
    comp_fits: Mapping[str,CompFit] = field(default_factory=dict)
    line_results: Mapping = field(default_factory=dict)
    recommended_board: Board | None = None
    advice: tuple[Advice,...] = ()
    workload: Mapping = field(default_factory=dict)
    simulation_diagnostics: Mapping = field(default_factory=dict,compare=False)
    # Offline margin evidence: the comps each plan guard compared at this step.
    guards: Mapping = field(default_factory=dict,compare=False)
    def __post_init__(self):
        object.__setattr__(self,'comp_fits',freeze(self.comp_fits))
        object.__setattr__(self,'line_results',freeze(self.line_results))
        object.__setattr__(self,'workload',freeze(self.workload))
        object.__setattr__(self,'simulation_diagnostics',freeze(self.simulation_diagnostics))
        object.__setattr__(self,'guards',freeze(self.guards))

@dataclass(frozen=True)
class EngineContext:
    snapshot: object
    history: object
    data: object
    plan: GamePlan
    comp_fits: Mapping
    line_results: Mapping
    recommended_board: Board | None
    seed: int = 0
    opponents: tuple = ()
    workload: Mapping = field(default_factory=dict)
    effects: object = None
    _simulation: object = field(default=None,compare=False,repr=False)
    guards: Mapping = field(default_factory=dict,compare=False)
    def __post_init__(self):
        object.__setattr__(self,'comp_fits',freeze(self.comp_fits))
        object.__setattr__(self,'line_results',freeze(self.line_results))
        object.__setattr__(self,'workload',freeze(self.workload))
        object.__setattr__(self,'guards',freeze(self.guards))


def paused(reason, *, missing=(), domain='status'):
    return Advice(domain,'Advice paused','information',0.0,'advice_paused',payload={'paused':True,'reason':reason,'missing':tuple(missing)},validity=('fields','data'))


def field_age(data,name,snapshot):
    table=tunable(data,'field_max_age_seconds')
    if isinstance(table,Mapping):
        if name=='shop' and snapshot.field('roll_down',max_age_seconds=float(table.get('roll_down',table['default']))):
            return float(table.get('shop_roll_down',table.get('shop',table['default'])))
        return float(table.get(name,table['default']))
    return float(table)


def read(snapshot,data,name):
    """Read source-tagged telemetry, preserving persistent accepted UI pins."""
    if name == "pinned_line":
        pin = snapshot.fields.get(name)
        if pin is not None and pin.source == "ui_pin":
            # An accepted local choice persists until unpin or lifecycle reset.
            # Its original command time cannot become future capture evidence.
            return pin.value if pin.read_at <= snapshot.captured_at else None
    return snapshot.field(name,max_age_seconds=field_age(data,name,snapshot))

def required(snapshot,data,names):
    names=tuple(names)
    if {'board','bench','owned_copies','slot_inventory'}.intersection(names) and 'inventory_complete' not in names:
        names+=('inventory_complete',)
    if 'lobby' in names and 'lobby_complete' not in names:
        names+=('lobby_complete',)
    missing=[]
    from .lobby import lobby_certificate_qualified
    for name in names:
        value=read(snapshot,data,name)
        if value is None or (name=='inventory_complete' and value is not True) or (name=='lobby_complete' and not lobby_certificate_qualified(snapshot,data)):
            missing.append(name)
    return tuple(missing)


def observed_phase(snapshot,data):
    phase=snapshot.field('phase',max_age_seconds=field_age(data,'phase',snapshot))
    planning=snapshot.field('planning_phase',max_age_seconds=field_age(data,'planning_phase',snapshot))
    if phase in ('planning','roll_down') and planning is True:
        return phase
    if phase in ('augment','carousel','combat','end') and planning is False:
        return phase
    return None


def comp_universe(snapshot,data):
    if not read(snapshot,data,'include_unguided'):
        return data
    guides=dict(data.guides)
    mapped={getattr(g,'cluster_id',None) or g.id for g in guides.values()}
    for entity in data.entities.values():
        if entity.kind!='comp' or entity.id in mapped:
            continue
        units=entity.values.get('units'); carries=entity.values.get('carry_ids')
        if not units or not carries:
            continue
        guides[entity.id]=Guide(entity.id,'unrated',tuple(units.value),carry_ids=tuple(carries.value),source='metatft')
    return replace(data,guides=guides)


def owned_board(snapshot,data=None):
    board=read(snapshot,data,'board') if data is not None else snapshot.field('board')
    bench=read(snapshot,data,'bench') if data is not None else snapshot.field('bench')
    return Board(board.units,bench,board.trait_counts) if board is not None and bench is not None else board


def domain_fit(hooks,id,context):
    result={}
    for hook in hooks:
        if hook.fit is None or required(context.snapshot,context.data,hook.fit_required_fields):
            continue
        term=hook.fit(id,context)
        if term is not None:
            result[hook.name]=term
    return result


def _past_main_roll_down(snapshot,data,guide):
    from .transition import main_roll_down
    deadline=main_roll_down(guide,data)
    return bool(deadline and round_index(snapshot.round_id,data)>=round_index(deadline,data))


def pivot_margin(snapshot,data,guide):
    values=tunable(data,'pivot_margin_by_stage')
    stage=snapshot.round_id.split('-')[0]
    if not isinstance(values,Mapping):
        return float(values)
    value=values.get(stage,values.get('default'))
    if value is None:
        raise DataError(f'Missing pivot margin for stage {stage}')
    margin=float(value)
    if _past_main_roll_down(snapshot,data,guide):
        margin=max(margin,float(values.get('post_roll_down',margin)))
    return margin


def _commit_trigger(snapshot,data,ordered,fits,guards=None):
    board=owned_board(snapshot,data)
    from .capacity import CapacityModel
    from .capacity_fields import evidence_from_snapshot
    capacity=evidence_from_snapshot(snapshot,data)
    CapacityModel(data).check(board,read(snapshot,data,'level'),capacity,check_observed=True)
    for id in ordered:
        guide=data.guides[id]
        keys={canonical_id(id,data) for id in set(guide.carry_ids)|set(getattr(guide,'key_ids',()))}
        if any(canonical_id(u.unit_id,data) in keys and u.stars>=2 for u in board.units+board.bench):
            return id
        for unit in board.units:
            if canonical_id(unit.unit_id,data) not in {canonical_id(id,data) for id in guide.carry_ids}:
                continue
            if any(item_category(item, data) == 'finished' for item in unit.items):
                return id
    if len(ordered)>1:
        top,second=fits[ordered[0]],fits[ordered[1]]
        lead=second.score-top.score
        augment=(second.terms.get('augment',FitTerm(0,'')).delta-top.terms.get('augment',FitTerm(0,'')).delta)
        if guards is not None and augment>lead/2:
            # Only here does comp_defining_margin decide the commitment.
            guards['comp_defining']={'top':ordered[0],'second':ordered[1]}
        if lead>=stage_tunable(data,'comp_defining_margin',snapshot.round_id) and augment>lead/2:
            return ordered[0]
    if round_index(snapshot.round_id,data)>=round_index(str(tunable(data,'commit_latest_round')),data):
        return ordered[0]
    return None


def _choose_plan(snapshot,data,previous,fits,guards=None):
    if guards is not None:
        guards.clear()
    eligible=[id for id,fit in fits.items() if fit.simulated]
    ordered=tuple(sorted(eligible or fits,key=lambda id:(fits[id].score,id)))
    cap=int(tunable(data,'open_candidate_count'))
    labels=classify(owned_board(snapshot,data),data)
    label=labels[0].label if labels and labels[0].label!='no comp' else None
    similarities={v.comp_id:v.similarity for v in labels}
    lock=read(snapshot,data,'comp_lock')
    if lock is not None and lock not in data.guides:
        raise DataError(f'Unknown locked comp: {lock}')
    target=previous.target if previous.target in fits else ordered[0]
    status=previous.status
    rejected=previous.rejected_target
    pivot_from=pivot_to=None
    divergence=previous.divergence_round
    divergence_snapshot_id=previous.divergence_snapshot_id
    pivot_round=previous.pivot_round
    adopt=False
    new_phase=snapshot.round_id!=previous.planning_round
    if status=='open':
        trigger=_commit_trigger(snapshot,data,ordered,fits,guards)
        status='committed' if trigger or lock else 'open'
        target=trigger or lock or ordered[0]
    elif label and label!=target and not lock:
        moving=similarities.get(target,0)>previous.target_similarity
        if previous.pivot_to==target and previous.pivot_round and new_phase and not moving:
            rejected=target; target=label; divergence=None; adopt=True
        elif previous.player_label==label and divergence and new_phase:
            rejected=target; target=label; divergence=None; adopt=True
        elif not moving:
            if not divergence or previous.player_label != label:
                divergence=snapshot.round_id
                divergence_snapshot_id=snapshot.snapshot_id
        else:
            divergence=None
    else:
        divergence=None
    observed_transition = ({'from': previous.target, 'to': target,
        'reason': 'observed_player_adoption', 'observed_since_round': previous.divergence_round,
        'onset_snapshot_id': previous.divergence_snapshot_id or snapshot.snapshot_id,
        'confirmed_round': snapshot.round_id, 'snapshot_id': snapshot.snapshot_id}
        if adopt else None)
    if divergence is None:
        divergence_snapshot_id=None
    if status=='committed' and not adopt:
        challenger=next((id for id in ordered if id!=target),None)
        if challenger:
            margin=pivot_margin(snapshot,data,data.guides[target])
            if challenger==rejected:
                margin+=stage_tunable(data,'pivot_reraise_extra',snapshot.round_id)
            if guards is not None:
                guards['pivot']={'target':target,'challenger':challenger,'reraise':challenger==rejected,
                    'margin_key':'post_roll_down' if _past_main_roll_down(snapshot,data,data.guides[target]) else snapshot.round_id.split('-')[0]}
            if fits[target].score-fits[challenger].score>margin:
                pivot_from=target; pivot_to=challenger; pivot_round=snapshot.round_id
                if not lock:
                    target=challenger
    if lock:
        target=lock; status='committed'
    backup=next((id for id in ordered if id!=target),None) if status=='committed' else None
    candidates=ordered[:cap] if status=='open' else tuple(id for id in (target,backup) if id)
    return GamePlan(status,target,backup,candidates,previous.line,pivot_from,pivot_to,rejected,label,divergence,snapshot.round_id,similarities.get(target,0),pivot_round,observed_transition,divergence_snapshot_id)


def _line_choice(snapshot,data,previous,plan,results):
    if not results:
        return plan
    best=min(results,key=lambda r:(r.expected_placement,r.line.id))
    old=next((r for r in results if previous.line and r.line.id==previous.line.id),None) if previous.target==plan.target else None
    chosen=old if old and old.expected_placement-best.expected_placement<=stage_tunable(data,'line_margin',snapshot.round_id) else best
    pin=read(snapshot,data,'pinned_line')
    if pin:
        id=pin.get('id') if isinstance(pin,Mapping) else str(pin)
        chosen=next((r for r in results if r.line.id==id),None)
        if chosen is None:
            raise DataError(f'Pinned Line {id} has no validated schedule')
    return replace(plan,line=chosen.line)


class SimulationCache:
    """Exact stochastic memo with optional LRU limits for a single Live owner.

    Keys contain semantic inputs, resolved effects, opponents, seeds and Lines.
    Entry and rollout/projection limits bound retained results across rereads.
    The ordinary Engine uses an unbounded memo scoped to its one request.
    """
    def __init__(self, *, max_entries=None, max_samples=None):
        from collections import OrderedDict
        self.memo = OrderedDict()
        self.max_entries, self.max_samples = max_entries, max_samples
        self.samples = 0
        self.reset_statistics()

    def reset_statistics(self):
        self.stats = {'simulation_requests':0,'simulation_cache_hits':0,'executed_simulation_calls':0,'executed_concrete_lines':0,'executed_rollouts':0}

    def workload(self):
        return freeze(self.stats)

    def __call__(self,snapshot,history,data,comp_id,lines,**options):
        import json
        from .effects import captured, combine
        from .lobby import alive_lobby
        alive_lobby(snapshot,data) # Coverage must qualify before any cache lookup.
        identity=id(data)
        names=('board','bench','gold','hp','level','xp','streak','lobby','lobby_complete','team_slot_budget','held_augments','held_augments_complete','item_bench','item_inventory_complete','slot_count','shop')
        effect=combine(captured(snapshot,data),options.get('effects'))
        inputs={'round':snapshot.round_id,'fields':{name:read(snapshot,data,name) for name in names},
            'comp':comp_id,'lines':tuple(lines),'options':options|{'effects':effect},'model':identity}
        key=json.dumps(_encode(inputs),sort_keys=True,separators=(',',':'),allow_nan=False)
        self.stats['simulation_requests']+=1
        if key in self.memo:
            self.stats['simulation_cache_hits']+=1
            self.memo.move_to_end(key)
            result, _, _ = self.memo[key]
        else:
            self.stats['executed_simulation_calls']+=1
            self.stats['executed_concrete_lines']+=len(lines)
            self.stats['executed_rollouts']+=len(lines)*int(options.get('rollouts') or tunable(data,'rollouts_full'))
            result=simulate_lines(snapshot,history,data,comp_id,lines,**options)
            samples=sum(len(row.rollout_placements)+len(row.rollout_deaths)+8*len(row.projections) for row in result)
            # Retaining each entry's immutable data prevents identity reuse;
            # eviction releases temporary choice/universe snapshots as well.
            self.memo[key]=(result,samples,data)
            self.samples+=samples
            while self.memo and ((self.max_entries is not None and len(self.memo)>self.max_entries)
                    or (self.max_samples is not None and self.samples>self.max_samples)):
                _,(_,removed,_)=self.memo.popitem(last=False)
                self.samples-=removed
        return result


def _simulation_reuse():
    return SimulationCache()

def _step(snapshot,history,data,previous,hooks,*,seed=None,effects=None,rollouts=None,_simulation=None):
    from .effects import captured, combine
    explicit_effects=effects
    captured(snapshot,data) # Validate dependent counters before planning; simulation resolves them once.
    board=owned_board(snapshot,data)
    from .capacity import CapacityModel
    from .capacity_fields import evidence_from_snapshot
    capacity=evidence_from_snapshot(snapshot,data)
    CapacityModel(data).check(board,read(snapshot,data,'level'),capacity,check_observed=True)
    from .lobby import alive_lobby
    ids=tuple(alive_lobby(snapshot,data))
    opponents=tuple(opponent for opponent in opponents_from_history(history,snapshot.round_id,data,opponent_ids=ids) if opponent.opponent_id in ids)
    context=EngineContext(snapshot,history,data,previous,{}, {},board,snapshot_seed(snapshot,data) if seed is None else seed,opponents,effects=explicit_effects,_simulation=_simulation)
    left=rounds_left_to_live(snapshot,data,opponents)
    terms={id:domain_fit(hooks,id,context) for id in data.guides}
    fits={id:screen_comp(snapshot,data,guide,context,terms[id],opponents=opponents,rounds_left=left) for id,guide in data.guides.items()}
    order=sorted(fits,key=lambda id:(fits[id].score,id))
    if previous.status=='open':
        selected=order[:int(tunable(data,'open_candidate_count'))]
    else:
        selected=list(dict.fromkeys([id for id in (previous.target,previous.backup) if id in fits]+order[:int(tunable(data,'challengers_simulated'))]))
    if read(snapshot,data,'roll_down') and previous.target in fits:
        selected=[previous.target]
    lock=read(snapshot,data,'comp_lock')
    if lock in fits and lock not in selected:
        selected.append(lock)
    trigger=_commit_trigger(snapshot,data,order,fits) if previous.status=='open' else None
    if trigger and trigger not in selected:
        selected.append(trigger)
    results={}
    backups={}
    count=int(rollouts if rollouts is not None else tunable(data,'rollouts_reroll' if read(snapshot,data,'roll_down') else 'rollouts_full'))
    workload={'simulation_passes':0,'simulated_concrete_lines':0,'reason_counterfactual_lines':0,'rollouts_per_line':count}
    def score(id,backup):
        lines=list(candidate_lines(snapshot,data,data.guides[id],rounds_left=left))
        pin=read(snapshot,data,'pinned_line')
        if isinstance(pin,Mapping):
            lines.append(Line.from_dict(pin))
        if previous.target==id and previous.line:
            lines.append(previous.line)
        unique={l.id:l for l in concrete_lines(lines)}
        scored=(_simulation or simulate_lines)(snapshot,history,data,id,tuple(unique.values()),rollouts=count,opponents=opponents,seed=context.seed,backup_id=backup,effects=effects)
        results[id]=scored; backups[id]=backup
        best=min(scored,key=lambda r:r.expected_placement)
        ideal=(_simulation or simulate_lines)(snapshot,history,data,id,(best.line,),rollouts=count,opponents=opponents,seed=context.seed,backup_id=backup,assume_keys_on_time=True,effects=effects)[0]
        workload['simulation_passes']+=1
        workload['simulated_concrete_lines']+=len(scored)
        workload['reason_counterfactual_lines']+=1
        domain=dict(terms[id])
        domain['simulation']=FitTerm(best.expected_placement,'line_simulated_placement',{'hit_probability':best.hit_probability,'death_probability':best.death_probability,'standard_error':best.standard_error,'hit_placement_cost':best.expected_placement-ideal.expected_placement,'death_placement_cost':best.death_placement_cost,'key_arrival_counterfactual':'keys_at_main_roll_down_without_shop_uncertainty'},best.confidence)
        fits[id]=CompFit(id,sum(t.delta for t in domain.values()),True,domain,min([best.confidence]+[t.confidence for t in terms[id].values()]),best.hit_probability,best.death_probability)
    for id in selected:
        backup=previous.backup if id==previous.target and previous.backup in fits else next((other for other in order if other!=id),None)
        score(id,backup)
    guards={}
    plan=_choose_plan(snapshot,data,previous,fits,guards)
    # The current Backup changes sale gold. Reconcile its target simulation and
    # rerank until the plan is consistent; repeated pairs are explicit unavailable
    # states rather than an arbitrary iteration or timing-dependent cutoff.
    seen=set()
    while plan.target not in results or backups[plan.target]!=plan.backup:
        pair=(plan.target,plan.backup)
        if pair in seen:
            raise DataError('Comp and Backup sale priorities did not converge')
        seen.add(pair)
        score(plan.target,plan.backup)
        plan=_choose_plan(snapshot,data,previous,fits,guards)
    guards['simulation_backups']=dict(backups)
    plan=_line_choice(snapshot,data,previous,plan,results.get(plan.target,()))
    recommended=strongest_owned_board(board,int(read(snapshot,data,'level')),data,target=plan.target if plan.status=='committed' else None,round_id=snapshot.round_id,capacity=capacity)
    context=EngineContext(snapshot,history,data,plan,fits,results,recommended,context.seed,opponents,workload,explicit_effects,_simulation,guards)
    return context


def _econ_advice(context):
    snapshot,data,plan=context.snapshot,context.data,context.plan
    results=context.line_results.get(plan.target,())
    chosen=next((r for r in results if r.line.id==plan.line.id),None)
    if chosen is None:
        return (paused('Line is unavailable',domain='econ'),)
    owned=owned_copies(owned_board(snapshot,data),data); rules=data.value('rules_flags')
    slots=read(snapshot,data,'slot_count')
    slots=float(slots if slots is not None else rules['unknown_wisp_slots'])
    floor=chosen.line.rolls.get(snapshot.round_id)
    analytic=[]
    contested={}
    for opponent in context.opponents:
        for id,copies in opponent.expected_copies.items():
            contested[id]=contested.get(id,0)+copies
    for id,goal in key_goals(data.guides[plan.target],data).items():
        shops=int(max(0,(float(read(snapshot,data,'gold'))-(floor if floor is not None else float(read(snapshot,data,'gold'))))//float(rules['roll_cost'])))
        analytic.append(hit_probability(id,max(0,goal-owned.get(id,0)),shops,slots,int(read(snapshot,data,'level')),data,owned=owned,contested=contested))
    hit=min(analytic,default=1.0)
    action=f'Roll to {floor:g} gold' if floor is not None and hit<1 else 'Stop rolling, hold' if floor is not None else 'Hold econ'
    from .lines import current_level_target
    if current_level_target(chosen.line,snapshot.round_id,data,int(read(snapshot,data,'level')))>int(read(snapshot,data,'level')):
        action='Level now'
    projections={r.line.id:tuple(p.to_dict() for p in r.projections) for r in results}
    options=tuple(ScoredOption(r.line.id,'line',r.line.to_dict() | {'after': {'seed': r.seed, 'rollout_placements': r.rollout_placements}},r.expected_placement,r.standard_error,'line_expected_placement') for r in results)
    best=min(results,key=lambda r:r.expected_placement)
    gap=chosen.expected_placement-best.expected_placement
    from .bench import roll_sale_indices
    selling=tuple(owned_board(snapshot,data).bench[i].unit_id for i in roll_sale_indices(owned_board(snapshot,data),data,target=plan.target,backup=plan.backup)) if floor is not None else ()
    workload=dict(context.workload)|{'schedule_families':len({r.line.family_id or r.line.id for r in results}),'concrete_lines':len(results),'simulated_comps':len(context.line_results),'total_concrete_lines':sum(len(v) for v in context.line_results.values())}
    payload={'game_plan':plan.to_dict(),'workload':workload,'planned_gold':chosen.projections[0].planned_gold,'gold_floor':floor,'sell_before_roll':selling,'line_id':chosen.line.id,'line':chosen.line.to_dict(),'projections':projections,'pinned':bool(read(snapshot,data,'pinned_line')),'pin_alternative':best.line.id if gap>stage_tunable(data,'line_margin',snapshot.round_id) else None,'pin_gap':gap}
    return (Advice('econ',action,'act_this_phase',chosen.confidence,'line_selected',{'expected_placement':chosen.expected_placement,'analytic_hit':hit,'death_probability':chosen.death_probability},('gold','shop','round','board'),decision_id=f'{snapshot.snapshot_id}:econ',option_id=chosen.line.id,payload=payload,options=options,validity_state={'round':snapshot.round_id,'gold':read(snapshot,data,'gold'),'board':read(snapshot,data,'board').to_dict()}),)


def _pivot_advice(context):
    plan=context.plan
    if not plan.pivot_to or not plan.pivot_from:
        return ()
    old,new=context.comp_fits[plan.pivot_from],context.comp_fits[plan.pivot_to]
    keys=set(old.terms)|set(new.terms)
    differences=sorted(((name,old.terms.get(name,FitTerm(0,'')).delta-new.terms.get(name,FitTerm(0,'')).delta) for name in keys),key=lambda v:(-abs(v[1]),v[0]))[:2]
    return (Advice('pivot',f'Pivot to {plan.pivot_to}','act_this_phase',min(old.confidence,new.confidence),'pivot_fit_margin',{'placement_gain':old.score-new.score},('board','augments','items','round'),old.score-new.score,decision_id=f'{context.snapshot.snapshot_id}:pivot',option_id=plan.pivot_to,payload={'target':plan.pivot_to,'from':plan.pivot_from,'locked':bool(read(context.snapshot,context.data,'comp_lock')),'fit_differences':differences},options=tuple(ScoredOption(id,'comp',{'comp_id':id},fit.score,None,'comp_fit') for id,fit in sorted(context.comp_fits.items())),validity_state={'round':context.snapshot.round_id}),)


def _hook_advice(hooks,context):
    items=[]
    for hook in hooks:
        if hook.advice is None:
            continue
        if hook.activation_field and hook.activation_field not in context.snapshot.fields:
            continue
        try:
            missing=required(context.snapshot,context.data,hook.required_fields)
        except (DataError,KeyError) as error:
            items.append(paused(str(error),domain=hook.name)); continue
        if missing:
            items.append(paused('Required fields missing or stale',missing=missing,domain=hook.name))
            continue
        try:
            advice=tuple(hook.advice(context))
            phase=observed_phase(context.snapshot,context.data)
            allowed=phase in ('planning','roll_down','augment','carousel') and phase in hook.advice_phases
            names=tuple(dict.fromkeys(hook.required_fields+hook.dependency_fields+('phase','planning_phase')))
            items.extend(decision_evidence(a,context,names) for a in advice if allowed or a.urgency=='information')
            if not allowed and any(a.urgency!='information' for a in advice):
                items.append(paused('Actions unavailable in the observed phase',missing=('phase','planning_phase'),domain=hook.name))
        except (DataError,KeyError,TypeError,ValueError) as error:
            items.append(paused(str(error),domain=hook.name))
    return tuple(items)


@patch_calculation
def _model_hash(data):
    from hashlib import sha256
    import json
    return sha256(json.dumps(_encode(data.tunables),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def decision_evidence(advice,context,names):
    from hashlib import sha256
    import json
    fields={name:_encode(context.snapshot.fields.get(name)) for name in names}
    model_hash=_model_hash(context.data)
    fingerprint={'round':context.snapshot.round_id,'fields':fields,'history':history_evidence(context),
        'data_snapshot_id':context.data.snapshot_id,'model_hash':model_hash}
    semantic={'round':context.snapshot.round_id,'values':{name:_encode(read(context.snapshot,context.data,name)) for name in names},'data':context.data.snapshot_id,'model':model_hash}
    token=sha256(json.dumps(semantic,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:16]
    return replace(advice,validity=tuple(dict.fromkeys(advice.validity+names)),validity_state=dict(advice.validity_state)|fingerprint,
        decision_id=f'{context.snapshot.game_id}:{context.snapshot.round_id}:{advice.decision}:{token}')


def history_evidence(context):
    """Inline standalone histories; bind replay histories to exact source evidence."""
    from hashlib import sha256
    import json

    if '_history_evidence' not in context.__dict__:
        from .models import frozen_history, history_json
        if context.history.source_reference is None:
            value=frozen_history(context.history)
        else:
            source=dict(context.history.source_reference) | {'round_id': context.snapshot.round_id}
            encoded=history_json(context.history)
            value=freeze({'source': source,'sha256': sha256(encoded.encode()).hexdigest()})
        object.__setattr__(context,'_history_evidence',value)
    return context.__dict__['_history_evidence']


def causal_history(snapshot, history, data):
    """The Engine's canonical causal ordering, shared with replay reconstruction."""
    previous=[state for state in history.snapshots if state.game_id==snapshot.game_id
        and state.captured_at<=snapshot.captured_at and state!=snapshot
        and round_index(state.round_id,data)<=round_index(snapshot.round_id,data)]
    previous.sort(key=lambda state:(state.captured_at,round_index(state.round_id,data)))
    sightings=tuple(sighting for sighting in history.sightings if (
        sighting.read_at<=snapshot.captured_at if sighting.read_at else
        round_index(sighting.round_id,data)<=round_index(snapshot.round_id,data)))
    source_reference=(dict(history.source_reference) | {'projection': 'engine_causal_v1'}
        if history.source_reference is not None else None)
    return replace(history,snapshots=tuple(previous),sightings=sightings,source_reference=source_reference)


def core_evidence(items,context):
    from .registry import CORE_DEPENDENCY_FIELDS
    names=CORE_DEPENDENCY_FIELDS
    return tuple(decision_evidence(a,context,names) if a.decision in ('econ','pivot','plan','transition') else a for a in items)


class PlanningHistory:
    """Caller-owned memo of exact causal planning prefixes.

    Entries are reused only while equal immutable snapshots and
    sightings occur in the same order with the same data and hook registry.
    A changed prefix discards the suffix. This is an optimization of the
    historical fold, never a substitute for evaluating the current decision.
    """
    def __init__(self):
        self.data = None
        self.hooks = None
        self.entries = []

    def bind(self, data, hooks):
        if self.data is not data or self.hooks != hooks:
            self.data, self.hooks, self.entries = data, hooks, []
        return self.entries


@evaluation_scope
def evaluate(snapshot,history,data,mode,*,hooks=None,seed=None,effects=None,rollouts=None,reuse_simulations=True,_simulation=None,history_fold=None):
    if mode in ('baseline','silent'):
        return EngineEvaluation(GamePlan())
    if mode not in ('live','review'):
        raise ValueError(f'Unknown Engine mode: {mode}')
    if data is None:
        return EngineEvaluation(GamePlan(),advice=(paused('Patch data unavailable'),))
    if hooks is None:
        from .registry import default_hooks
        hooks=default_hooks()
    data=comp_universe(snapshot,data)
    if _simulation is None and reuse_simulations:
        _simulation=_simulation_reuse()
    plan=GamePlan(); context=None
    entries=history_fold.bind(data,tuple(hooks)) if history_fold is not None else None
    fold_simulation=_simulation_reuse() if history_fold is not None and reuse_simulations else _simulation
    try:
        if not data.guides:
            raise DataError('No validated Guides available')
        # Replay actual observed history. Future and other-game snapshots cannot influence this game.
        causal=causal_history(snapshot,history,data)
        previous=causal.snapshots
        for index,state in enumerate(previous):
            sightings=tuple(s for s in history.sightings if (s.read_at<=state.captured_at if s.read_at else round_index(s.round_id,data)<=round_index(state.round_id,data)))
            if entries is not None and index<len(entries):
                old_state,old_sightings,old_plan=entries[index]
                if old_state==state and old_sightings==sightings:
                    plan=old_plan
                    continue
                del entries[index:]
            if observed_phase(state,data) in ('planning','roll_down') and not required(state,data,('board','bench','gold','hp','level','xp','streak','lobby')):
                prefix=replace(history,snapshots=tuple(previous[:index]),sightings=sightings)
                context=_step(state,prefix,data,plan,hooks,_simulation=fold_simulation)
                plan=context.plan
            if entries is not None:
                entries.append((state,sightings,plan))
        if entries is not None:
            del entries[len(previous):]
        missing=required(snapshot,data,('board','bench','gold','hp','level','xp','streak','lobby'))
        if missing:
            lock=read(snapshot,data,'comp_lock')
            if plan.target is None and lock in data.guides:
                plan=GamePlan('committed',lock,candidates=(lock,))
            # Earlier fits and a freshly read ownership subset cannot describe
            # this current state. Preserve only the descriptive observed plan.
            context=EngineContext(snapshot,causal,data,plan,{}, {},None,snapshot_seed(snapshot,data) if seed is None else seed,effects=effects,_simulation=_simulation)
            items=(paused('Required fields missing or stale',missing=missing,domain='econ'),)+_hook_advice(hooks,context)
            if 'inventory_complete' in missing:
                items+=(paused('Complete own ownership unavailable',missing=('inventory_complete',),domain='plan'),
                        paused('Complete own ownership unavailable',missing=('inventory_complete',),domain='transition'))
            return EngineEvaluation(plan,advice=rank_advice(core_evidence(items,context)),simulation_diagnostics=_simulation.workload() if _simulation else {})
        if observed_phase(snapshot,data) not in ('planning','roll_down'):
            context=EngineContext(snapshot,causal,data,plan,{}, {},None,snapshot_seed(snapshot,data) if seed is None else seed,effects=effects,_simulation=_simulation)
            items=tuple(paused('Fresh positive planning evidence unavailable',missing=('phase','planning_phase'),domain=domain) for domain in ('econ','plan','transition'))+_hook_advice(hooks,context)
            return EngineEvaluation(plan,advice=rank_advice(core_evidence(items,context)),simulation_diagnostics=_simulation.workload() if _simulation else {})
        else:
            prefix=replace(causal,snapshots=tuple(previous),sightings=tuple(s for s in history.sightings if (s.read_at<=snapshot.captured_at if s.read_at else round_index(s.round_id,data)<=round_index(snapshot.round_id,data))))
            context=_step(snapshot,prefix,data,plan,hooks,seed=seed,effects=effects,rollouts=rollouts,_simulation=_simulation)
            if entries is not None and effects is None and rollouts is None and (seed is None or seed==snapshot_seed(snapshot,data)):
                entries.append((snapshot,prefix.sightings,context.plan))
        items=_pivot_advice(context)+_econ_advice(context)+transition_advice(snapshot,context.recommended_board,context.plan,data)+_hook_advice(hooks,context)
        ranked=rank_advice(core_evidence(items,context))
        guide=data.guides[context.plan.target]
        if guide.source=='metatft' and guide.tier=='unrated':
            ranked=tuple(replace(a,confidence=min(a.confidence,float(tunable(data,'confidence_medium_min')))) for a in ranked)
        # A pivot is the first call for the new plan even if another action estimates greater gain.
        ranked=tuple(a for a in ranked if a.decision=='pivot')+tuple(a for a in ranked if a.decision!='pivot')
        guards=dict(context.guards)
        # Offline evidence survives layout/activation suppression. These shares
        # are evaluated from the same causal history and never change advice.
        try:
            from datetime import datetime
            from .positioning import adjustments
            settled=read(snapshot,data,'board_settled_since')
            since=datetime.fromisoformat(settled) if settled else None
            if since is not None and since.tzinfo is not None and (snapshot.captured_at-since).total_seconds()>=float(tunable(data,'board_settle_seconds')):
                _,shares=adjustments(snapshot,context.history,data)
                guards['threat_shares']=shares
        except (DataError,KeyError,TypeError,ValueError):
            pass
        return EngineEvaluation(context.plan,context.comp_fits,context.line_results,context.recommended_board,ranked,context.workload,_simulation.workload() if _simulation else {},guards)
    except (DataError,KeyError,ValueError,TypeError) as error:
        context=EngineContext(snapshot,history,data,plan,{}, {},owned_board(snapshot,data),snapshot_seed(snapshot,data) if seed is None else seed,_simulation=_simulation)
        return EngineEvaluation(plan,advice=rank_advice((paused(str(error),domain='econ'),)+_hook_advice(hooks,context)))


def advise(snapshot,history,data,mode,*,hooks=None):
    return evaluate(snapshot,history,data,mode,hooks=hooks).advice


def best_choice_fit(context,changes,*,hooks=None,effects=None,rollouts=None):
    """Score a changed choice state on the original snapshot's random tape."""
    from .models import FieldValue
    missing=required(context.snapshot,context.data,('inventory_complete','lobby','lobby_complete'))
    if missing:
        return None,EngineEvaluation(context.plan,advice=(paused('Complete own ownership and lobby unavailable',missing=missing,domain='econ'),))
    phase=observed_phase(context.snapshot,context.data)
    if phase not in ('planning','roll_down','augment','carousel'):
        return None,EngineEvaluation(context.plan,advice=(paused('Choice projection unavailable in the observed phase',missing=('phase','planning_phase'),domain='econ'),))
    fields=dict(context.snapshot.fields)
    fields.update({name:FieldValue(value,context.snapshot.captured_at,'choice',1) for name,value in changes.items()})
    if phase in ('augment','carousel'):
        # Project an option into planning without promoting the original evidence
        # or adding the observed choice snapshot to the actual planning fold.
        fields.update({name:FieldValue(value,context.snapshot.captured_at,'choice',1)
            for name,value in (('phase','planning'),('planning_phase',True))})
    changed=replace(context.snapshot,fields=fields)
    if set(changes)&{'board','bench','held_augments','item_bench'} or (effects is not None and (effects.item_state is not None or effects.item_bench_state is not None)):
        # The captured budget certifies the observed board, not a changed option.
        # Its hypothetical budget comes only from the same sourced model.
        fields.pop('team_slot_budget',None)
        changed=replace(changed,fields=fields)
    if hooks is None:
        from .registry import default_hooks
        hooks=default_hooks()
    fit_hooks=tuple(replace(hook,advice=None) for hook in hooks)
    from .effects import combine
    result=evaluate(changed,context.history,context.data,'review',hooks=fit_hooks,seed=context.seed,effects=combine(context.effects,effects),rollouts=rollouts,reuse_simulations=False,_simulation=context._simulation)
    available=bool(result.line_results) and not any(a.decision=='econ' and a.payload.get('paused') for a in result.advice)
    if not available:
        # Preserved history fits describe an earlier state, not this choice.
        result=replace(result,comp_fits={},line_results={})
    return min((fit.score for fit in result.comp_fits.values() if fit.simulated),default=None),result
