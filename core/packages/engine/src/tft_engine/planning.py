"""Pure Game plan/history fold and per-domain advice orchestration."""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Mapping
from tft_data.models import DataError, Guide, freeze
from .models import Advice, ScoredOption, Board, Unit, rank_advice, _encode
from .power import tunable, estimate_strength
from .lines import Line, guide_line, simulate_lines, candidate_lines, concrete_lines, snapshot_seed
from .opponents import opponents_from_history, round_index
from .classifier import classify
from .registry import FitTerm, DomainHook
from .comp_fit import CompFit, screen_comp, rounds_left_to_live
from .transition import strongest_owned_board, transition_advice
from .shop_math import hit_probability, owned_copies, key_goals, canonical_id

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
    def __post_init__(self):
        object.__setattr__(self,'comp_fits',freeze(self.comp_fits))
        object.__setattr__(self,'line_results',freeze(self.line_results))
        object.__setattr__(self,'workload',freeze(self.workload))

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
    def __post_init__(self):
        object.__setattr__(self,'comp_fits',freeze(self.comp_fits))
        object.__setattr__(self,'line_results',freeze(self.line_results))
        object.__setattr__(self,'workload',freeze(self.workload))


def paused(reason, *, missing=(), domain='status'):
    return Advice(domain,'Advice paused','information',0.0,'advice_paused',payload={'paused':True,'reason':reason,'missing':tuple(missing)},validity=('fields','data'))


def field_age(data,name,snapshot):
    table=tunable(data,'field_max_age_seconds')
    if isinstance(table,Mapping):
        if name=='shop' and snapshot.field('roll_down'):
            return float(table.get('shop_roll_down',table.get('shop',table['default'])))
        return float(table.get(name,table['default']))
    return float(table)


def required(snapshot,data,names):
    names=tuple(names)
    if {'board','bench','owned_copies','slot_inventory'}.intersection(names) and 'inventory_complete' not in names:
        names+=('inventory_complete',)
    missing=[]
    for name in names:
        value=snapshot.field(name,max_age_seconds=field_age(data,name,snapshot))
        if value is None or (name=='inventory_complete' and value is not True):
            missing.append(name)
    return tuple(missing)


def comp_universe(snapshot,data):
    if not snapshot.field('include_unguided'):
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


def owned_board(snapshot):
    board=snapshot.field('board')
    bench=snapshot.field('bench')
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


def pivot_margin(snapshot,data,guide):
    values=tunable(data,'pivot_margin_by_stage')
    stage=snapshot.round_id.split('-')[0]
    if not isinstance(values,Mapping):
        return float(values)
    margin=float(values.get(stage,values.get('default',0)))
    from .transition import main_roll_down
    deadline=main_roll_down(guide,data)
    if deadline and round_index(snapshot.round_id,data)>=round_index(deadline,data):
        margin=max(margin,float(values.get('post_roll_down',margin)))
    return margin


def _commit_trigger(snapshot,data,ordered,fits):
    board=owned_board(snapshot)
    for id in ordered:
        guide=data.guides[id]
        keys={canonical_id(id,data) for id in set(guide.carry_ids)|set(getattr(guide,'key_ids',()))}
        if any(canonical_id(u.unit_id,data) in keys and u.stars>=2 for u in board.units+board.bench):
            return id
        for unit in board.units:
            if canonical_id(unit.unit_id,data) not in {canonical_id(id,data) for id in guide.carry_ids}:
                continue
            if any(not data.entities[item].values['component'].value for item in unit.items):
                return id
    if len(ordered)>1:
        top,second=fits[ordered[0]],fits[ordered[1]]
        lead=second.score-top.score
        augment=(second.terms.get('augment',FitTerm(0,'')).delta-top.terms.get('augment',FitTerm(0,'')).delta)
        if lead>=float(tunable(data,'comp_defining_margin')) and augment>lead/2:
            return ordered[0]
    if round_index(snapshot.round_id,data)>=round_index(str(tunable(data,'commit_latest_round')),data):
        return ordered[0]
    return None


def _choose_plan(snapshot,data,previous,fits):
    eligible=[id for id,fit in fits.items() if fit.simulated]
    ordered=tuple(sorted(eligible or fits,key=lambda id:(fits[id].score,id)))
    cap=int(tunable(data,'open_candidate_count'))
    labels=classify(owned_board(snapshot),data)
    label=labels[0].label if labels and labels[0].label!='no comp' else None
    similarities={v.comp_id:v.similarity for v in labels}
    lock=snapshot.field('comp_lock')
    if lock is not None and lock not in data.guides:
        raise DataError(f'Unknown locked comp: {lock}')
    target=previous.target if previous.target in fits else ordered[0]
    status=previous.status
    rejected=previous.rejected_target
    pivot_from=pivot_to=None
    divergence=previous.divergence_round
    pivot_round=previous.pivot_round
    adopt=False
    new_phase=snapshot.round_id!=previous.planning_round
    if status=='open':
        trigger=_commit_trigger(snapshot,data,ordered,fits)
        status='committed' if trigger or lock else 'open'
        target=trigger or lock or ordered[0]
    elif label and label!=target and not lock:
        moving=similarities.get(target,0)>previous.target_similarity
        if previous.pivot_to==target and previous.pivot_round and new_phase and not moving:
            rejected=target; target=label; divergence=None; adopt=True
        elif previous.player_label==label and divergence and new_phase:
            rejected=target; target=label; divergence=None; adopt=True
        elif not moving:
            divergence=divergence or snapshot.round_id
        else:
            divergence=None
    else:
        divergence=None
    if status=='committed' and not adopt:
        challenger=next((id for id in ordered if id!=target),None)
        if challenger:
            margin=pivot_margin(snapshot,data,data.guides[target])
            if challenger==rejected:
                margin+=float(tunable(data,'pivot_reraise_extra'))
            if fits[target].score-fits[challenger].score>margin:
                pivot_from=target; pivot_to=challenger; pivot_round=snapshot.round_id
                if not lock:
                    target=challenger
    if lock:
        target=lock; status='committed'
    backup=next((id for id in ordered if id!=target),None) if status=='committed' else None
    candidates=ordered[:cap] if status=='open' else tuple(id for id in (target,backup) if id)
    return GamePlan(status,target,backup,candidates,previous.line,pivot_from,pivot_to,rejected,label,divergence,snapshot.round_id,similarities.get(target,0),pivot_round)


def _line_choice(snapshot,data,previous,plan,results):
    if not results:
        return plan
    best=min(results,key=lambda r:(r.expected_placement,r.line.id))
    old=next((r for r in results if previous.line and r.line.id==previous.line.id),None) if previous.target==plan.target else None
    chosen=old if old and old.expected_placement-best.expected_placement<=float(tunable(data,'line_margin')) else best
    pin=snapshot.field('pinned_line')
    if pin:
        id=pin.get('id') if isinstance(pin,Mapping) else str(pin)
        chosen=next((r for r in results if r.line.id==id),None)
        if chosen is None:
            raise DataError(f'Pinned Line {id} has no validated schedule')
    return replace(plan,line=chosen.line)


def _step(snapshot,history,data,previous,hooks,*,seed=None):
    board=owned_board(snapshot)
    from .lobby import alive_lobby
    ids=tuple(alive_lobby(snapshot))
    opponents=opponents_from_history(history,snapshot.round_id,data,opponent_ids=ids)
    context=EngineContext(snapshot,history,data,previous,{}, {},board,snapshot_seed(snapshot) if seed is None else seed,opponents)
    left=rounds_left_to_live(snapshot,data,opponents)
    terms={id:domain_fit(hooks,id,context) for id in data.guides}
    fits={id:screen_comp(snapshot,data,guide,context,terms[id],opponents=opponents,rounds_left=left) for id,guide in data.guides.items()}
    order=sorted(fits,key=lambda id:(fits[id].score,id))
    if previous.status=='open':
        selected=order[:int(tunable(data,'open_candidate_count'))]
    else:
        selected=list(dict.fromkeys([id for id in (previous.target,previous.backup) if id in fits]+order[:int(tunable(data,'challengers_simulated'))]))
    if snapshot.field('roll_down') and previous.target in fits:
        selected=[previous.target]
    lock=snapshot.field('comp_lock')
    if lock in fits and lock not in selected:
        selected.append(lock)
    trigger=_commit_trigger(snapshot,data,order,fits) if previous.status=='open' else None
    if trigger and trigger not in selected:
        selected.append(trigger)
    results={}
    backups={}
    count=int(tunable(data,'rollouts_reroll' if snapshot.field('roll_down') else 'rollouts_full'))
    workload={'simulation_passes':0,'simulated_concrete_lines':0,'reason_counterfactual_lines':0,'rollouts_per_line':count}
    def score(id,backup):
        lines=list(candidate_lines(snapshot,data,data.guides[id],rounds_left=left))
        pin=snapshot.field('pinned_line')
        if isinstance(pin,Mapping):
            lines.append(Line.from_dict(pin))
        if previous.target==id and previous.line:
            lines.append(previous.line)
        unique={l.id:l for l in concrete_lines(lines)}
        scored=simulate_lines(snapshot,history,data,id,tuple(unique.values()),rollouts=count,opponents=opponents,seed=context.seed,backup_id=backup)
        results[id]=scored; backups[id]=backup
        best=min(scored,key=lambda r:r.expected_placement)
        ideal=simulate_lines(snapshot,history,data,id,(best.line,),rollouts=count,opponents=opponents,seed=context.seed,backup_id=backup,assume_keys_on_time=True)[0]
        workload['simulation_passes']+=1
        workload['simulated_concrete_lines']+=len(scored)
        workload['reason_counterfactual_lines']+=1
        domain=dict(terms[id])
        domain['simulation']=FitTerm(best.expected_placement,'line_simulated_placement',{'hit_probability':best.hit_probability,'death_probability':best.death_probability,'standard_error':best.standard_error,'hit_placement_cost':best.expected_placement-ideal.expected_placement,'death_placement_cost':best.death_placement_cost,'key_arrival_counterfactual':'keys_at_main_roll_down_without_shop_uncertainty'},best.confidence)
        fits[id]=CompFit(id,sum(t.delta for t in domain.values()),True,domain,min([best.confidence]+[t.confidence for t in terms[id].values()]),best.hit_probability,best.death_probability)
    for id in selected:
        backup=previous.backup if id==previous.target and previous.backup in fits else next((other for other in order if other!=id),None)
        score(id,backup)
    plan=_choose_plan(snapshot,data,previous,fits)
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
        plan=_choose_plan(snapshot,data,previous,fits)
    plan=_line_choice(snapshot,data,previous,plan,results.get(plan.target,()))
    recommended=strongest_owned_board(board,int(snapshot.field('level')),data,target=plan.target if plan.status=='committed' else None,round_id=snapshot.round_id)
    context=EngineContext(snapshot,history,data,plan,fits,results,recommended,context.seed,opponents,workload)
    return context


def _econ_advice(context):
    snapshot,data,plan=context.snapshot,context.data,context.plan
    results=context.line_results.get(plan.target,())
    chosen=next((r for r in results if r.line.id==plan.line.id),None)
    if chosen is None:
        return (paused('Line is unavailable',domain='econ'),)
    owned=owned_copies(owned_board(snapshot),data); rules=data.value('rules_flags')
    slots=snapshot.field('slot_count')
    slots=float(slots if slots is not None else rules['unknown_wisp_slots'])
    floor=chosen.line.rolls.get(snapshot.round_id)
    analytic=[]
    contested={}
    for opponent in context.opponents:
        for id,copies in opponent.expected_copies.items():
            contested[id]=contested.get(id,0)+copies
    for id,goal in key_goals(data.guides[plan.target],data).items():
        shops=int(max(0,(float(snapshot.field('gold'))-(floor if floor is not None else float(snapshot.field('gold'))))//float(rules['roll_cost'])))
        analytic.append(hit_probability(id,max(0,goal-owned.get(id,0)),shops,slots,int(snapshot.field('level')),data,owned=owned,contested=contested))
    hit=min(analytic,default=1.0)
    action=f'Roll to {floor:g} gold' if floor is not None and hit<1 else 'Stop rolling, hold' if floor is not None else 'Hold econ'
    from .lines import current_level_target
    if current_level_target(chosen.line,snapshot.round_id,data,int(snapshot.field('level')))>int(snapshot.field('level')):
        action='Level now'
    projections={r.line.id:tuple(p.to_dict() for p in r.projections) for r in results}
    options=tuple(ScoredOption(r.line.id,'line',r.line.to_dict(),r.expected_placement,r.standard_error,'line_expected_placement') for r in results)
    best=min(results,key=lambda r:r.expected_placement)
    gap=chosen.expected_placement-best.expected_placement
    from .bench import roll_sale_indices
    selling=tuple(owned_board(snapshot).bench[i].unit_id for i in roll_sale_indices(owned_board(snapshot),data,target=plan.target,backup=plan.backup)) if floor is not None else ()
    workload=dict(context.workload)|{'schedule_families':len({r.line.family_id or r.line.id for r in results}),'concrete_lines':len(results),'simulated_comps':len(context.line_results),'total_concrete_lines':sum(len(v) for v in context.line_results.values())}
    payload={'game_plan':plan.to_dict(),'workload':workload,'planned_gold':chosen.projections[0].planned_gold,'gold_floor':floor,'sell_before_roll':selling,'line_id':chosen.line.id,'line':chosen.line.to_dict(),'projections':projections,'pinned':bool(snapshot.field('pinned_line')),'pin_alternative':best.line.id if gap>float(tunable(data,'line_margin')) else None,'pin_gap':gap}
    return (Advice('econ',action,'act_this_phase',chosen.confidence,'line_selected',{'expected_placement':chosen.expected_placement,'analytic_hit':hit,'death_probability':chosen.death_probability},('gold','shop','round','board'),decision_id=f'{snapshot.snapshot_id}:econ',option_id=chosen.line.id,payload=payload,options=options,validity_state={'round':snapshot.round_id,'gold':snapshot.field('gold'),'board':snapshot.field('board').to_dict()}),)


def _pivot_advice(context):
    plan=context.plan
    if not plan.pivot_to or not plan.pivot_from:
        return ()
    old,new=context.comp_fits[plan.pivot_from],context.comp_fits[plan.pivot_to]
    keys=set(old.terms)|set(new.terms)
    differences=sorted(((name,old.terms.get(name,FitTerm(0,'')).delta-new.terms.get(name,FitTerm(0,'')).delta) for name in keys),key=lambda v:(-abs(v[1]),v[0]))[:2]
    return (Advice('pivot',f'Pivot to {plan.pivot_to}','act_this_phase',min(old.confidence,new.confidence),'pivot_fit_margin',{'placement_gain':old.score-new.score},('board','augments','items','round'),old.score-new.score,decision_id=f'{context.snapshot.snapshot_id}:pivot',option_id=plan.pivot_to,payload={'target':plan.pivot_to,'from':plan.pivot_from,'locked':bool(context.snapshot.field('comp_lock')),'fit_differences':differences},options=tuple(ScoredOption(id,'comp',{'comp_id':id},fit.score,None,'comp_fit') for id,fit in sorted(context.comp_fits.items())),validity_state={'round':context.snapshot.round_id}),)


def _hook_advice(hooks,context):
    items=[]
    for hook in hooks:
        if hook.advice is None:
            continue
        try:
            missing=required(context.snapshot,context.data,hook.required_fields)
        except (DataError,KeyError) as error:
            items.append(paused(str(error),domain=hook.name)); continue
        if missing:
            items.append(paused('Required fields missing or stale',missing=missing,domain=hook.name))
            continue
        try:
            items.extend(hook.advice(context))
        except DataError as error:
            items.append(paused(str(error),domain=hook.name))
    return tuple(items)


def evaluate(snapshot,history,data,mode,*,hooks=None,seed=None):
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
    plan=GamePlan(); context=None
    try:
        if not data.guides:
            raise DataError('No validated Guides available')
        # Replay actual observed history. Future and other-game snapshots cannot influence this game.
        previous=[s for s in history.snapshots if s.game_id==snapshot.game_id and s.captured_at<=snapshot.captured_at and s!=snapshot and round_index(s.round_id,data)<=round_index(snapshot.round_id,data)]
        previous.sort(key=lambda s:(s.captured_at,round_index(s.round_id,data)))
        for index,state in enumerate(previous):
            if state.field('planning_phase') is False:
                continue
            if required(state,data,('board','bench','gold','hp','level','xp','streak','lobby')):
                continue
            prefix=replace(history,snapshots=tuple(previous[:index]),sightings=tuple(s for s in history.sightings if (s.read_at<=state.captured_at if s.read_at else round_index(s.round_id,data)<=round_index(state.round_id,data))))
            context=_step(state,prefix,data,plan,hooks)
            plan=context.plan
        missing=required(snapshot,data,('board','bench','gold','hp','level','xp','streak','lobby'))
        if missing:
            lock=snapshot.field('comp_lock')
            if plan.target is None and lock in data.guides:
                plan=GamePlan('committed',lock,candidates=(lock,))
            # Earlier fits and a freshly read ownership subset cannot describe
            # this current state. Preserve only the descriptive observed plan.
            context=EngineContext(snapshot,history,data,plan,{}, {},None,snapshot_seed(snapshot) if seed is None else seed)
            items=(paused('Required fields missing or stale',missing=missing,domain='econ'),)+_hook_advice(hooks,context)
            if 'inventory_complete' in missing:
                items+=(paused('Complete own ownership unavailable',missing=('inventory_complete',),domain='plan'),
                        paused('Complete own ownership unavailable',missing=('inventory_complete',),domain='transition'))
            return EngineEvaluation(plan,advice=rank_advice(items))
        if snapshot.field('planning_phase') is False:
            context=replace(context,snapshot=snapshot,history=history) if context else EngineContext(snapshot,history,data,plan,{}, {},owned_board(snapshot),snapshot_seed(snapshot) if seed is None else seed)
            items=(paused('Outside a planning phase',domain='econ'),)+_hook_advice(hooks,context)
            return EngineEvaluation(plan,context.comp_fits,context.line_results,context.recommended_board,rank_advice(items))
        else:
            prefix=replace(history,snapshots=tuple(previous),sightings=tuple(s for s in history.sightings if (s.read_at<=snapshot.captured_at if s.read_at else round_index(s.round_id,data)<=round_index(snapshot.round_id,data))))
            context=_step(snapshot,prefix,data,plan,hooks,seed=seed)
        items=_pivot_advice(context)+_econ_advice(context)+transition_advice(snapshot,context.recommended_board,context.plan,data)+_hook_advice(hooks,context)
        ranked=rank_advice(items)
        guide=data.guides[context.plan.target]
        if guide.source=='metatft' and guide.tier=='unrated':
            ranked=tuple(replace(a,confidence=min(a.confidence,float(tunable(data,'confidence_medium_min')))) for a in ranked)
        # A pivot is the first call for the new plan even if another action estimates greater gain.
        ranked=tuple(a for a in ranked if a.decision=='pivot')+tuple(a for a in ranked if a.decision!='pivot')
        return EngineEvaluation(context.plan,context.comp_fits,context.line_results,context.recommended_board,ranked,context.workload)
    except (DataError,KeyError,ValueError,TypeError) as error:
        context=EngineContext(snapshot,history,data,plan,{}, {},owned_board(snapshot),snapshot_seed(snapshot) if seed is None else seed)
        return EngineEvaluation(plan,advice=rank_advice((paused(str(error),domain='econ'),)+_hook_advice(hooks,context)))


def advise(snapshot,history,data,mode,*,hooks=None):
    return evaluate(snapshot,history,data,mode,hooks=hooks).advice


def best_choice_fit(context,changes,*,hooks=None):
    """Score a changed choice state on the original snapshot's random tape."""
    from .models import FieldValue
    if required(context.snapshot,context.data,('inventory_complete',)):
        return None,EngineEvaluation(context.plan,advice=(paused('Complete own ownership unavailable',missing=('inventory_complete',),domain='econ'),))
    fields=dict(context.snapshot.fields)
    fields.update({name:FieldValue(value,context.snapshot.captured_at,'choice',1) for name,value in changes.items()})
    changed=replace(context.snapshot,fields=fields)
    if hooks is None:
        from .registry import default_hooks
        hooks=default_hooks()
    fit_hooks=tuple(replace(hook,advice=None) for hook in hooks)
    result=evaluate(changed,context.history,context.data,'review',hooks=fit_hooks,seed=context.seed)
    available=bool(result.line_results) and not any(a.decision=='econ' and a.payload.get('paused') for a in result.advice)
    if not available:
        # Preserved history fits describe an earlier state, not this choice.
        result=replace(result,comp_fits={},line_results={})
    return min((fit.score for fit in result.comp_fits.values() if fit.simulated),default=None),result
