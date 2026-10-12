"""Curated tiers and qualified statistics remain distinct valuation sources."""
from .planning import read
from datetime import datetime
from .registry import FitTerm
from .planning import required, paused, best_choice_fit
from .power import tunable, static
from .models import Advice, ScoredOption
from .choices import pair, evidence, selected, hold_option
from .effects import simulation
from tft_data.models import DataError
from tft_data.config import STATISTICS_MIN_SAMPLES


def tier(id,comp,data,offer_tier=None):
    guide=data.guides[comp]
    label=data.comp_augment_tiers.get(guide.cluster_id or comp,{}).get(id)
    global_label=data.augment_tiers.get(id)
    mapping=tunable(data,'augment_tier_delta')
    if label in mapping:
        return float(mapping[label]),'comp_tier',label
    if global_label in mapping:
        return float(mapping[global_label]),'global_tier',global_label
    entity=data.entities.get(id)
    tagged=entity.values.get('augment_tier') if entity else None
    fallback=offer_tier or (tagged.value if tagged else None)
    if fallback not in mapping:
        raise DataError(f'Augment prior unavailable: {id}/{comp}')
    return float(mapping[fallback]),'offer_tier_prior',fallback


def stale_tiers(data):
    for source in data.sources.values():
        if 'augment' not in source.kind:
            continue
        start=source.filters.get('patch_start_at')
        if source.patch!=data.patch or (start and source.updated_at<datetime.fromisoformat(start)):
            return True
    return False


def value(id,comp,context,*,offer_tier=None):
    data=context.data; prior,source,label=tier(id,comp,data,offer_tier)
    cap=float(tunable(data,'confidence_medium_min'))
    if source=='global_tier':
        cap=min(cap,float(tunable(data,'confidence_show_min')))
    rows=[s for s in data.statistics if s.kind=='augment' and s.entity_id==id]
    if not rows:
        return prior,cap,'stale_'+source if stale_tiers(data) else source,label
    entity=data.entities.get(id)
    baseline=entity.values.get('global_baseline_placement') if entity else None
    minimum=entity.values.get('statistics_min_samples') if entity else None
    if baseline is None or minimum is None:
        return prior,cap,'stat_metadata_unavailable_'+source,label
    if minimum.value!=STATISTICS_MIN_SAMPLES or isinstance(minimum.value,bool) or not 1<=float(baseline.value)<=8:
        return prior,cap,'stat_policy_unqualified_'+source,label
    stage=None
    rounds=data.static.get('augment_pick_rounds')
    if rounds:
        stage=rounds.value.get(context.snapshot.round_id)
    globals=[s for s in rows if s.comp_id is None and (s.pick_stage is None or s.pick_stage==stage)]
    global_row=max(globals,key=lambda s:(s.pick_stage==stage and stage is not None,s.sample_count),default=None)
    if global_row is None or global_row.sample_count<int(minimum.value):
        return prior,cap,'thin_statistics_'+source,label
    strength=float(tunable(data,'augment_prior_strength'))
    multiplier=float(tunable(data,'augment_flag_prior_multiplier'))
    global_prior= strength*(multiplier if global_row.stale or global_row.changed else 1)
    global_value=(global_row.sample_count*(global_row.average_placement-float(baseline.value))+global_prior*prior)/(global_row.sample_count+global_prior)
    guide=data.guides[comp]
    candidates=[s for s in rows if s.comp_id in (comp,guide.cluster_id) and s.comp_id is not None and (s.pick_stage is None or s.pick_stage==stage)]
    row=max(candidates,key=lambda s:(s.pick_stage==stage and stage is not None,s.sample_count),default=None)
    confidence=global_row.sample_count/(global_row.sample_count+global_prior)
    if row:
        base=max((s for s in data.statistics if s.kind=='comp' and s.entity_id in (comp,guide.cluster_id)),key=lambda s:s.sample_count,default=None)
        if base is None:
            return global_value,min(confidence,cap),'global_statistics_comp_baseline_unavailable',label
        weight=strength*(multiplier if row.stale or row.changed else 1)
        result=(row.sample_count*(row.average_placement-base.average_placement)+weight*global_value)/(row.sample_count+weight)
        confidence=min(confidence,row.sample_count/(row.sample_count+weight))
        if row.stale or row.changed or global_row.stale or global_row.changed or base.stale or base.changed:
            confidence=min(confidence,cap)
        return result,confidence,'comp_pick_statistics' if row.pick_stage else 'comp_statistics',label
    if global_row.stale or global_row.changed:
        confidence=min(confidence,cap)
    return global_value,confidence,'global_pick_statistics' if global_row.pick_stage else 'global_statistics',label


def fit(comp,context):
    held=read(context.snapshot,context.data,'held_augments')
    if held is None:
        return FitTerm(0,'held_augments_unread_no_fit')
    if read(context.snapshot,context.data,'held_augments_complete') is not True:
        return None
    result=0.0; confidence=1.0; sources=[]
    for id in held:
        econ=context.data.static.get('econ_augments')
        if econ and id in econ.value:
            sources.append((id,'economy_in_captured_state_and_remaining_effects'))
            continue # Never add curated value on top of simulated econ effects.
        try:
            projected=context.snapshot.fields.get('projected_augment_ids')
            icon=read(context.snapshot,context.data,'augment_tier') if projected is not None and projected.source=='choice' and id in projected.value else None
            delta,certainty,source,label=value(id,comp,context,offer_tier=icon)
        except (DataError,KeyError):
            return None
        result+=delta; confidence=min(confidence,certainty); sources.append((id,source))
    return FitTerm(result,'held_augment_values',{'sources':sources},confidence)


def advice(context):
    snapshot,data=context.snapshot,context.data
    if read(snapshot,data,'augments') is None:
        return ()
    missing=required(snapshot,data,('augments','augment_tier','augment_offers_complete'))
    if missing or read(snapshot,data,'augment_offers_complete') is not True:
        return (paused('Complete augment offer required',missing=missing,domain='augment'),)
    offers=read(snapshot,data,'augments')
    if len(offers)!=3 or any(not isinstance(row.get('reroll_available'),bool) for row in offers):
        return (paused('Three augment options and observed reroll flags required',domain='augment'),)
    held=read(snapshot,data,'held_augments')
    if held is None or read(snapshot,data,'held_augments_complete') is not True:
        return static_information(context,'Held augments unavailable for choice projection')
    try:
        options=[]; results={}; counterfactuals={}
        ids={row['augment_id'] for row in offers}
        pool=static(data,'augment_pools')[read(snapshot,data,'augment_tier')]
        base=best_choice_fit(context,{})
        def score(id):
            if id in counterfactuals:
                return counterfactuals[id]
            effect=static(data,'econ_augments').get(id)
            effects=simulation(effect,data,snapshot) if effect else None
            changes={'held_augments':tuple(held)+(id,),'projected_augment_ids':(id,)}
            if effect:
                changes['projected_effect_ids']=(id,)
            gain,error,before,after,baseline,changed=pair(context,changes,effects=effects,baseline=base)
            winning=selected(after)[0]
            if 'item' not in winning.terms:
                raise DataError('Item fit unavailable for augment comp choice')
            delta,confidence,source,label=(0,changed.confidence,'econ_pair',None) if effect else value(id,winning.comp_id,context,offer_tier=read(snapshot,data,'augment_tier'))
            result=(winning.score,error,gain,confidence,source,label,evidence(before,after,baseline,changed),winning.comp_id)
            counterfactuals[id]=result
            return result
        for row in offers:
            id=row['augment_id']; scored=score(id); results[id]=scored
            payload={'slot':row['slot'],'augment_id':id,'source':scored[4],'tier':scored[5],'placement_gain':scored[2],'cost_units':'placement','best_comp':scored[7],**scored[6]}
            options.append(ScoredOption(f'augment:{row["slot"]}:{id}','pick',payload,scored[0],scored[1],scored[4]))
        def tie_key(option):
            comp=option.payload['best_comp']; id=option.payload['augment_id']
            guide_tag=id in data.guides[comp].augment_tiers
            global_value=float(tunable(data,'augment_tier_delta').get(data.augment_tiers.get(id),float('inf')))
            return (not guide_tag,global_value,option.option_id)
        ordered=sorted(options,key=lambda option:(option.expected_placement,tie_key(option)))
        best=ordered[0]; close=[]
        for option in ordered:
            import numpy as np
            difference=np.asarray(option.payload['after']['rollout_placements'])-np.asarray(best.payload['after']['rollout_placements'])
            paired_error=float(np.std(difference,ddof=1)/np.sqrt(len(difference))) if len(difference)>1 else 0.0
            if option.expected_placement-best.expected_placement<=2*paired_error or (option.payload['tier']==best.payload['tier'] and option.expected_placement==best.expected_placement):
                close.append(option)
        if len(close)>1:
            best=min(close,key=tie_key)
        confidence=min(results[best.payload['augment_id']][3],float(tunable(data,'confidence_medium_min'))) if 'tier' in best.reason or 'prior' in best.reason else results[best.payload['augment_id']][3]
        items=[Advice('augment','Take augment','act_this_phase',confidence,'augment_options_close' if len(close)>1 else 'augment_best_fit',
            {'placement_gain':best.payload['placement_gain']},('augments','held_augments','round'),max(0,best.payload['placement_gain']),
            decision_id=f'{snapshot.snapshot_id}:augment',option_id=best.option_id,payload={'operation':'pick','augment_id':best.payload['augment_id'],'slot':best.payload['slot'],'close':tuple(o.payload['augment_id'] for o in close)},options=tuple(options)+(hold_option(base[1],domain='augment',operation='defer'),))]
        rerolls=[row['slot'] for row in offers if row['augment_id']!=best.payload['augment_id'] and row['reroll_available']]
        best_row=next(row for row in offers if row['augment_id']==best.payload['augment_id'])
        remaining=[id for id in pool if id not in ids]
        expected=None; pool_options=[]; decision_options=[]
        if best_row['reroll_available'] and remaining:
            import numpy as np
            alternatives=[option for option in options if option!=best]
            probability=1/len(remaining); expected=0.0; differences=None; outcomes=[]
            for id in remaining:
                scored=score(id)
                outcome=ScoredOption(f'augment:pool:{id}','reroll_outcome',{'augment_id':id,'probability':probability,'cost_units':'placement','placement_gain':scored[2],'best_comp':scored[7],**scored[6]},scored[0],scored[1],scored[4])
                pool_options.append(outcome)
                chosen=min([outcome]+alternatives,key=lambda o:(o.expected_placement,o.option_id))
                vector=np.asarray(best.payload['after']['rollout_placements'])-np.asarray(chosen.payload['after']['rollout_placements'])
                differences=probability*vector if differences is None else differences+probability*vector
                expected+=probability*chosen.expected_placement
                outcomes.append({'probability':probability,'new_option_id':outcome.option_id,'chosen_option_id':chosen.option_id})
            error=float(np.std(differences,ddof=1)/np.sqrt(len(differences))) if len(differences)>1 else 0.0
            keep=ScoredOption('augment:keep','keep',dict(best.payload)|{'baseline_option_id':'augment:keep','placement_gain':0.0},best.expected_placement,0.0,'keep_current_best')
            reroll=ScoredOption(f'augment:reroll:{best_row["slot"]}','reroll',{'slot':best_row['slot'],'baseline_option_id':'augment:keep','cost_units':'placement','placement_gain':best.expected_placement-expected,'outcomes':tuple(outcomes),'pool_weights':'uniform'},expected,error,'paired_reroll_best_expectation')
            decision_options=[keep,reroll]
            if expected<best.expected_placement:
                rerolls.append(best_row['slot'])
        # Every scored pool outcome remains visible even if its reroll is rejected.
        complete_options=tuple(options)+tuple(pool_options)+tuple(decision_options)+(hold_option(base[1],domain='augment',operation='defer'),)
        from dataclasses import replace
        items[0]=replace(items[0],options=complete_options)
        if rerolls:
            items.append(Advice('augment','Reroll augment options','act_this_phase',confidence,'augment_reroll_expectation',
                validity=('augments','round'),option_id='augment:reroll',payload={'operation':'reroll','slots':tuple(sorted(rerolls)),'expected_best':expected,'keep_best':best.expected_placement,'pool':tuple(remaining),'cost_units':'placement','pool_weights':'uniform'},options=complete_options))
        return tuple(items)
    except (DataError,KeyError) as error:
        return static_information(context,str(error))


def static_information(context,reason):
    options=[]; data=context.data
    for row in read(context.snapshot,context.data,'augments') or ():
        tiers={}
        for comp in data.guides:
            try:
                delta,source,label=tier(row['augment_id'],comp,data,read(context.snapshot,context.data,'augment_tier'))
                tiers[comp]={'tier':label,'delta':delta,'source':source,'guide_tag':row['augment_id'] in data.guides[comp].augment_tiers}
            except DataError:
                continue
        options.append(ScoredOption(f'augment:{row["slot"]}:{row["augment_id"]}','information',dict(row)|{'tiers':tiers,'qualified_static_only':True},reason='choice_projection_unavailable'))
    return (paused(reason,domain='augment'),Advice('augment','Augment tiers','information',float(tunable(data,'confidence_show_min')),'qualified_static_tiers',payload={'operation':'tiers','model_unavailable':reason},options=tuple(options)))
