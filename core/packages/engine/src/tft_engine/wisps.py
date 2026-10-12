"""Set-specific sourced offers; unknown effects and purchase counts stay unavailable."""
from .planning import read
from .planning import required, paused
from .power import static, tunable, stage_tunable
from .models import Advice, ScoredOption
from .effects import simulation, combine
from .lines import SimulationEffects
from .choices import pair, evidence, selected, hold_option, expected
from tft_data.models import DataError


def advice(context):
    snapshot,data=context.snapshot,context.data
    if data.set_number!=18:
        return ()
    if read(snapshot,data,'wisp') is None:
        return ()
    missing=required(snapshot,data,('wisp','wisp_complete','gold','board','bench','slot_count','wisp_purchases_this_round','wisp_purchase_count_complete'))
    if missing or read(snapshot,data,'wisp_complete') is not True or read(snapshot,data,'wisp_purchase_count_complete') is not True:
        return (paused('Positive Wisp offer and per-round purchase count required',missing=missing,domain='wisp'),)
    offer=read(snapshot,data,'wisp'); id=offer['wisp_id']; cost=float(offer['cost'])
    try:
        from math import isfinite
        if not isfinite(cost):
            raise DataError('Wisp cost must be finite')
        cap=static(data,'wisp_round_cap'); allowed=int(cap['default'])
        board=read(snapshot,data,'board')
        for trait,value in cap['trait_overrides'].items():
            if board.trait_counts is None:
                raise DataError('Authoritative trait counts required for Wisp cap overrides')
            entity=data.entities.get(trait)
            tagged=entity.values.get('wisp_cap_breakpoint') if entity else None
            threshold,maximum=(tagged.value if tagged else None),value
            if threshold is None:
                raise DataError(f'Wisp cap breakpoint unavailable: {trait}')
            if board.trait_counts.get(trait,0)>=threshold:
                allowed=max(allowed,int(maximum))
        count=read(snapshot,data,'wisp_purchases_this_round')
        if not isinstance(count,int) or isinstance(count,bool) or count<0 or cost<0:
            raise DataError('Wisp count and cost must be nonnegative observed values')
        if count>=allowed:
            return (Advice('wisp','Wisp round cap reached','information',float(tunable(data,'confidence_medium_min')),'wisp_round_cap',payload={'operation':'cap','wisp_id':id}),)
        if cost>float(read(snapshot,data,'gold')):
            return (Advice('wisp','Wisp unaffordable','information',float(tunable(data,'confidence_medium_min')),'wisp_unaffordable',payload={'operation':'skip','wisp_id':id,'cost':cost,'cost_units':'gold'}),)
        effect=static(data,'wisps').get(id)
        if effect is None:
            raise DataError(f'Wisp effect unavailable: {id}')
        refill=static(data,'rules_flags').get('wisp_purchase_shop_slots_delta')
        if not isinstance(refill,int) or isinstance(refill,bool) or refill<0:
            raise DataError('Sourced Wisp purchase slot refill unavailable')
        after_slots=float(read(snapshot,data,'slot_count'))+refill
        if after_slots>int(static(data,'rules_flags')['champion_slots_max']):
            raise DataError('Wisp purchase slot count exceeds sourced champion maximum')
        if effect['effect_kind'] in ('unit_grant','item_grant','polymorph','duplicator','risky'):
            from .grants import distribution
            import numpy as np
            rows=tuple((p,changes|{'slot_count':after_slots},value,label) for p,changes,value,label in distribution(effect,context,offer))
            if effect['effect_kind']=='risky':
                rows=tuple((p,changes,combine(effect_value,SimulationEffects(gold_reduction=cost)),label) for p,changes,effect_value,label in rows)
            gain,error,value,outcomes,base,grant_vector=expected(context,rows)
            baseline=selected(base[1])[1]; changed=baseline
            if effect['effect_kind']=='risky':
                payload={'outcomes':outcomes,'pairing':'conditional_outcomes_with_price_on_shared_tape'}
            else:
                # Choice-rule grants price gold on the smaller paired tape.
                price,price_error,price_before,price_after,price_baseline,price_changed=pair(context,{},effects=SimulationEffects(gold_reduction=cost),rollouts=int(tunable(data,'rollouts_reroll')))
                price_vector=np.asarray(price_baseline.rollout_placements)-np.asarray(price_changed.rollout_placements)
                overlap=min(len(grant_vector),len(price_vector))
                covariance=float(np.cov(grant_vector[:overlap],price_vector[:overlap],ddof=1)[0,1]) if overlap>1 else 0.0
                variance=error**2+price_error**2+2*covariance*overlap/(len(grant_vector)*len(price_vector))
                error=float(np.sqrt(max(0,variance))); gain+=price; value-=price
                payload={'outcomes':outcomes,'grant_value':gain-price,'gold_price':-price,'gold_pair':evidence(price_before,price_after,price_baseline,price_changed),
                    'pairing':'conditional_outcomes_integrated_on_shared_tape_with_overlapping_gold_pair_covariance'}
            before=base[1]
        else:
            effects=combine(simulation(effect,data,snapshot),SimulationEffects(gold_reduction=cost,shop_slots_delta=refill))
            gain,error,before,after,baseline,changed=pair(context,{},effects=effects)
            value=selected(after)[0].score
            payload=evidence(before,after,baseline,changed)
        payload={'wisp_id':id,'slot':offer['slot'],'cost':cost,'champion_slots_after':after_slots,'cost_units':'gold','placement_gain':gain,**payload}
        option=ScoredOption(f'wisp:{offer["slot"]}:{id}','buy',payload,value,error,'sourced_effect_pair')
        skip=hold_option(before,domain='wisp',operation='skip')
        buy=gain>stage_tunable(data,'wisp_buy_margin',snapshot.round_id)
        return (Advice('wisp','Buy Wisp' if buy else 'Skip Wisp','act_this_phase',min(baseline.confidence,changed.confidence),'sourced_effect_pair',
            {'placement_gain':gain,'paired_standard_error':error},('wisp','gold','board','round'),max(0,gain),
            decision_id=f'{snapshot.snapshot_id}:wisp',option_id=option.option_id if buy else skip.option_id,payload=payload|{'operation':'buy' if buy else 'skip'},options=(option,skip)),)
    except (DataError,KeyError,ValueError,TypeError) as error:
        return (paused(str(error),domain='wisp'),)+static_information(context,str(error))


def fit(comp,context):
    """Wisp/encounter effects enter Lines; no second additive curated value."""
    from .registry import FitTerm
    return FitTerm(0,'wisp_effects_in_line_simulation') if context.data.set_number==18 else None


def static_information(context,reason):
    offer=read(context.snapshot,context.data,'wisp')
    table=context.data.static.get('wisp_worth_table')
    stage=context.snapshot.round_id.split('-')[0]
    row=table.value.get(offer['wisp_id'],{}).get(stage) if table and offer else None
    if not row:
        return ()
    return (Advice('wisp','Static Wisp worth','information',float(tunable(context.data,'confidence_show_min')),
        'qualified_static_worth',payload={'operation':'worth','wisp_id':offer['wisp_id'],'stage':stage,
            'label':row['label'],'model_unavailable':reason,'worth_source':row.get('source')}),)


def compute_wisp_worth(data,standard_states):
    """Compute patch references from caller-supplied, explicitly qualified states.

    The caller supplies the Guide comp, median HP and stage-average ownership;
    the Engine never manufactures those source statistics. Owner labels win.
    """
    from dataclasses import replace
    from tft_data.models import freeze
    from .models import FieldValue, GameHistory
    from .planning import evaluate, EngineContext
    from .lines import guide_line, paired_value, snapshot_seed
    from .registry import default_hooks
    if data.set_number!=18:
        raise DataError('Wisp plug-in is available only for Set 18')
    result={}; overrides=data.static.get('wisp_worth_overrides')
    for id,effect in static(data,'wisps').items():
        stages={}
        for stage in effect['offer_stages']:
            stage=str(stage); override=overrides.value.get(id,{}).get(stage) if overrides else None
            if override is not None:
                if override not in ('worth_it','situational','skip'):
                    raise DataError('Invalid owner Wisp worth label')
                stages[stage]={'label':override,'source':'owner'}
                continue
            state=standard_states.get(stage)
            if state is None:
                stages[stage]={'label':'unavailable','source':'missing_standard_state'}
                continue
            try:
                if state.round_id.split('-')[0]!=stage or read(state,data,'comp_lock') not in data.guides:
                    raise DataError('Standard Wisp state requires matching stage and a pinned Guide comp')
                comp=read(state,data,'comp_lock'); line=guide_line(data.guides[comp],data)
                price=float(effect['cost'])
                margin=stage_tunable(data,'wisp_buy_margin',state.round_id)
                kind=effect['effect_kind']
                if kind in ('gold','xp','rolls','shop','combat_buff','sale_modifier'):
                    refill=static(data,'rules_flags').get('wisp_purchase_shop_slots_delta')
                    if not isinstance(refill,int) or isinstance(refill,bool) or refill<0:
                        raise DataError('Sourced Wisp purchase slot refill unavailable')
                    modeled=combine(simulation(effect,data,state),SimulationEffects(gold_reduction=price,shop_slots_delta=refill))
                    gain,error,before,after=paired_value(state,GameHistory(),data,comp,(line,),modeled)
                    proof={'before':before[0].to_dict(),'after':after[0].to_dict()}
                else:
                    fields=dict(state.fields)|{name:FieldValue(value,state.captured_at,'offline_standard',1) for name,value in (
                        ('wisp',{'wisp_id':id,'slot':4,'cost':price}),('wisp_complete',True),('wisp_purchases_this_round',0),('wisp_purchase_count_complete',True))}
                    projection=replace(state,fields=fields)
                    evaluation=evaluate(projection,GameHistory(),data,'review',hooks=tuple(replace(hook,advice=None) for hook in default_hooks()))
                    context=EngineContext(projection,GameHistory(),data,evaluation.plan,evaluation.comp_fits,evaluation.line_results,evaluation.recommended_board,seed=snapshot_seed(projection,data))
                    valued=next((row for row in advice(context) if row.options),None)
                    if valued is None:
                        raise DataError('Wisp effect unavailable for standard-state valuation')
                    gain=valued.numbers['placement_gain']; error=valued.numbers['paired_standard_error']; proof=dict(valued.options[0].payload)
                label='situational' if abs(gain-margin)<=2*error else 'worth_it' if gain>margin else 'skip'
                stages[stage]={'label':label,'placement_gain':gain,'paired_standard_error':error,'source':'engine_standard_state',
                    'standard_snapshot_id':state.snapshot_id,'guide_comp':comp,'cost_units':'placement',**proof}
            except (DataError,KeyError,ValueError,TypeError) as error:
                stages[stage]={'label':'unavailable','source':'unmodelled','reason':str(error)}
        result[id]=stages
    return freeze(result)
