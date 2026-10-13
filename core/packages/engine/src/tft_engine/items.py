"""Exact current-inventory assignment with explicit future-component approximation."""
from .planning import read
from collections import Counter
from functools import lru_cache
from math import exp
from tft_data.models import DataError
from .planning import required, owned_board, paused
from .registry import FitTerm
from .power import tunable, static, keyed, item_category
from dataclasses import replace
from .models import Advice, Board, FieldValue, ScoredOption
from .lines import paired_value, SimulationEffects
from .effects import combine, captured


def category(id,data):
    return item_category(id,data)


def available(context):
    return not required(context.snapshot,context.data,('board','bench','item_bench','item_inventory_complete')) and read(context.snapshot,context.data,'item_inventory_complete') is True


def inventory(context):
    board=owned_board(context.snapshot,context.data)
    ids=tuple(item for unit in board.units+board.bench for item in unit.items)+tuple(read(context.snapshot,context.data,'item_bench'))
    return tuple(id for id in ids if category(id,context.data)=='finished'),tuple(id for id in ids if category(id,context.data)=='component'),tuple(id for id in ids if category(id,context.data)=='tool')


def holders(comp,data):
    guide=data.guides[comp]
    result=tuple(id for id,items in guide.items.items() if items)
    if not result:
        entity=data.entities.get(guide.cluster_id or comp)
        tagged=entity.values.get('item_holders') if entity else None
        if tagged:
            result=tuple(tagged.value)
    if not result or len(result)>3:
        raise DataError(f'Sourced item holders unavailable: {comp}')
    return result


def item_value(id,unit_id,data):
    unit=data.entities[unit_id]; item=data.entities[id]
    unit_class=unit.values.get('item_class'); item_class=item.values.get('item_class')
    if unit_class is None or item_class is None:
        raise DataError(f'Item class unavailable: {unit_id}/{id}')
    prior=float(tunable(data,'item_class_prior')[unit_class.value][item_class.value])
    strength=float(tunable(data,'item_prior_strength'))
    if strength<0:
        raise DataError('Item prior strength must be nonnegative')
    base=max((s for s in data.statistics if s.entity_id==unit_id and s.kind=='unit' and s.item_id is None),key=lambda s:s.sample_count,default=None)
    row=max((s for s in data.statistics if s.entity_id==unit_id and s.item_id==id),key=lambda s:s.sample_count,default=None)
    confidence=float(tunable(data,'confidence_medium_min'))
    if row and base:
        if row.sample_count+strength<=0:
            raise DataError(f'Unsampled item value unavailable: {unit_id}/{id}')
        value=(row.sample_count*(base.average_placement-row.average_placement)+strength*prior)/(row.sample_count+strength)
        confidence=row.sample_count/(row.sample_count+strength)
        if row.stale or row.changed or base.stale or base.changed:
            confidence=min(confidence,float(tunable(data,'confidence_medium_min')))
        return value,confidence
    return prior,confidence


def reference(unit_id,data):
    value=data.entities[unit_id].values.get('item_reference')
    if value is not None:
        return float(value.value)
    base=max((s for s in data.statistics if s.entity_id==unit_id and s.kind=='unit' and s.item_id is None),key=lambda s:s.sample_count,default=None)
    rows=[s for s in data.statistics if s.entity_id==unit_id and s.item_id]
    if base is None or not base.sample_count or not rows:
        raise DataError(f'Average item reference unavailable: {unit_id}')
    return sum(s.sample_count/base.sample_count*item_value(s.item_id,unit_id,data)[0] for s in rows)


def assignment(comp,context):
    data=context.data; units=holders(comp,data); finished,components,_=inventory(context)
    slots=int(static(data,'rules_flags')['item_slots_max'])
    recipes=static(data,'item_recipes')
    stage=context.snapshot.round_id.split('-')[0]
    future=keyed(tunable(data,'component_income_by_stage'),stage)
    tagged_discount=keyed(tunable(data,'component_discount_by_stage'),stage)
    if future is None or tagged_discount is None:
        raise DataError(f'Component future model unavailable for stage {stage}')
    discount=float(tagged_discount)
    from math import isfinite
    if not 0<=discount<=1 or any(not isfinite(float(count)) or count<0 for count in future.values()):
        raise DataError('Component future counts/discount invalid')
    confidence=[1.0]
    @lru_cache(None)
    def value(item,holder):
        benefit,certainty=item_value(item,holder,data); confidence.append(certainty)
        return benefit
    @lru_cache(None)
    def option(component,holder):
        outcomes=[]
        for item,recipe in recipes.items():
            if component not in recipe:
                continue
            partner=list(recipe); partner.remove(component); partner=partner[0]
            if partner not in future:
                raise DataError(f'Future component income unavailable: {partner}/{stage}')
            outcomes.append((max(0,value(item,holder)),1-exp(-float(future[partner])),item))
        # Marginal independent Poisson partner arrivals approximate future option
        # value; current shared component consumption is searched exactly below.
        remain=1.0; expected=0.0
        for benefit,chance,item in sorted(outcomes,reverse=True):
            expected+=remain*chance*benefit; remain*=1-chance
        return expected*discount
    def better(a,b):
        guide=data.guides[comp]
        preference=lambda pairs:sum(item in guide.items.get(holder,()) for item,holder in pairs)
        return max((a,b),key=lambda r:(r[0],preference(r[1]),tuple(reversed(r[1]))))
    @lru_cache(None)
    def solve(done,pending,capacity):
        if done:
            item=done[0]; best=solve(done[1:],pending,capacity)
            for index,holder in enumerate(units):
                if capacity[index] and value(item,holder)>0:
                    next_cap=tuple(n-(i==index) for i,n in enumerate(capacity))
                    rest=solve(done[1:],pending,next_cap)
                    best=better(best,(rest[0]+value(item,holder),((item,holder),)+rest[1]))
            return best
        if not pending:
            return 0.0,()
        first=pending[0]; rest=pending[1:]; best=solve((),rest,capacity)
        for index,holder in enumerate(units):
            if not capacity[index]:
                continue
            next_cap=tuple(n-(i==index) for i,n in enumerate(capacity))
            expected=option(first,holder)
            if expected>0:
                remainder=solve((),rest,next_cap)
                best=better(best,(remainder[0]+expected,((f'option:{first}',holder),)+remainder[1]))
            for item,recipe in recipes.items():
                partner=list(recipe)
                if first not in partner:
                    continue
                partner.remove(first)
                if partner[0] in rest and value(item,holder)>0:
                    remaining=list(rest); remaining.remove(partner[0])
                    remainder=solve((),tuple(remaining),next_cap)
                    best=better(best,(remainder[0]+value(item,holder),((item,holder),)+remainder[1]))
        return best
    benefit,pairs=solve(tuple(sorted(finished)),tuple(sorted(components)),(slots,)*len(units))
    base=sum(reference(id,data) for id in units)
    return FitTerm(base-benefit,'item_assignment',{'benefit':benefit,'reference':base,'assignment':pairs,'future_model':'independent_poisson_marginal'},min(confidence))


def fit(comp,context):
    if not available(context):
        return None
    try:
        term=assignment(comp,context)
        opportunity,records=tool_opportunity(comp,context,term)
        return replace(term,delta=term.delta-opportunity,numbers=dict(term.numbers)|{
            'tool_opportunity_gain':opportunity,'tool_opportunities':records})
    except (DataError,KeyError) as error:
        return None



def weights(context):
    if context.plan.status!='open':
        return ((context.plan.target,1.0),)
    ids=tuple(id for id in context.plan.candidates if id in context.comp_fits)
    if not ids:
        raise DataError('Open item candidates unavailable')
    temperature=float(tunable(context.data,'open_candidate_temperature'))
    if temperature<=0:
        raise DataError('Open item temperature must be positive')
    scores=[context.comp_fits[id].score for id in ids]; minimum=min(scores)
    values=[exp(-(score-minimum)/temperature) for score in scores]; total=sum(values)
    return tuple((id,value/total) for id,value in zip(ids,values))


def weighted_fit(context,distribution):
    return sum(weight*assignment(id,context).delta for id,weight in distribution)


def changed_context(context,board,bench):
    fields=dict(context.snapshot.fields)|{'board':FieldValue(board,context.snapshot.captured_at,'choice',1),
        'bench':FieldValue(board.bench,context.snapshot.captured_at,'choice',1),
        'item_bench':FieldValue(tuple(bench),context.snapshot.captured_at,'choice',1)}
    return replace(context,snapshot=replace(context.snapshot,fields=fields))


def realized(board,data):
    return sum(item_value(item,unit.unit_id,data)[0] for unit in board.units for item in unit.items if category(item,data)=='finished')


def transfer_items(board,donor,items,data,allowed):
    """Exact finite assignment of removed items to fielded holders with free capacity."""
    capacity=int(static(data,'rules_flags')['item_slots_max']); units=list(board.units)
    candidates=[i for i,u in enumerate(units) if i!=donor and u.unit_id in allowed]
    best=(0.0,(),tuple(items))
    def search(pending,assignment,remaining,benefit):
        nonlocal best
        if not pending:
            proposal=(benefit,tuple(assignment),tuple(remaining))
            if (proposal[0],tuple(reversed(proposal[1])))>(best[0],tuple(reversed(best[1]))):
                best=proposal
            return
        item=pending[0]
        search(pending[1:],assignment,remaining+[item],benefit)
        if category(item,data)!='finished':
            return
        for index in candidates:
            held=sum(i==index for _,i in assignment)+len(units[index].items)
            value=item_value(item,units[index].unit_id,data)[0]
            if held<capacity and value>0:
                search(pending[1:],assignment+[(item,index)],remaining,benefit+value)
    search(list(items),[],[],0.0)
    for item,index in best[1]:
        units[index]=replace(units[index],items=units[index].items+(item,))
    return Board(tuple(units),board.bench,None),best


def tool_opportunity(comp,context,term):
    """Value sourced physical tool uses beyond the abstract best assignment.

    Removers do not change inventory assignment; they unlock a realized holder
    correction. Reforgers change inventory, so that fit improvement is counted
    once and deducted from any overlapping realized correction.
    """
    data=context.data; board=owned_board(context.snapshot,context.data); bench=tuple(read(context.snapshot,context.data,'item_bench'))
    tools=[id for id in bench if category(id,data)=='tool']
    kinds=[]
    for id in tools:
        tagged=data.entities[id].values.get('tool_kind')
        if tagged is None or tagged.value not in ('remover','reforger'):
            raise DataError(f'Item tool model unavailable: {id}')
        kinds.append(tagged.value)
    allowed=set(holders(comp,data)); records=[]; current=realized(board,data)
    @lru_cache(None)
    def removed(units,bench_units,remaining):
        state=Board(units,bench_units,None)
        if not remaining:
            return 0.0,()
        best=(0.0,())
        for index,unit in enumerate(state.units+state.bench):
            if not unit.items:
                continue
            on_board=index<len(state.units)
            empty=Board(tuple(replace(u,items=()) if i==index else u for i,u in enumerate(state.units)),
                tuple(replace(u,items=()) if i+len(state.units)==index else u for i,u in enumerate(state.bench)),None)
            after,assignment_row=transfer_items(empty,index if on_board else None,unit.items,data,allowed)
            gain=realized(after,data)-realized(state,data)
            future,uses=removed(after.units,after.bench,remaining-1)
            proposal=(gain+future,({'holder_index':index,'transfers':assignment_row[1],'remaining_items':assignment_row[2],'after_item_state':after.to_dict()},)+uses)
            if proposal[0]>best[0]:
                best=proposal
        return best
    gain,uses=removed(board.units,board.bench,kinds.count('remover'))
    if gain>0:
        records.append({'operation':'remove','placement_gain':gain,'uses':uses})
    if 'reforger' in kinds:
        from math import isclose
        pools=data.static.get('reforge_pools')
        best_gain=0.0; best_record=None
        for index,unit in enumerate(board.units+board.bench):
            role=data.entities[unit.unit_id].values.get('item_class')
            if role is None:
                raise DataError('Reforger holder class unavailable')
            for item_index,item in enumerate(unit.items):
                if category(item,data)!='finished':
                    continue
                item_role=data.entities[item].values.get('item_class')
                if item_role is None:
                    raise DataError('Reforger item class unavailable')
                if item_role.value in (role.value,'utility'):
                    continue
                outcomes=pools.value.get(item) if pools else None
                if not outcomes:
                    raise DataError(f'Sourced reforge outcomes unavailable: {item}')
                if any(row['probability']<=0 for row in outcomes) or not isclose(sum(row['probability'] for row in outcomes),1):
                    raise DataError('Reforge probabilities must be positive and sum to one')
                total=0.0; conditional=[]
                for row in outcomes:
                    items=list(unit.items); items[item_index]=row['item_id']
                    after=Board(tuple(replace(u,items=tuple(items)) if i==index else u for i,u in enumerate(board.units)),
                        tuple(replace(u,items=tuple(items)) if i+len(board.units)==index else u for i,u in enumerate(board.bench)),None)
                    fit_gain=term.delta-assignment(comp,changed_context(context,after,bench)).delta
                    holder_gain=realized(after,data)-current
                    correction=holder_gain-max(0,min(holder_gain,fit_gain)) if holder_gain>0 else holder_gain
                    total+=row['probability']*(fit_gain+correction)
                    conditional.append(dict(row,item_fit_gain=fit_gain,realized_holder_correction=correction,after_item_state=after.to_dict()))
                if total>best_gain:
                    best_gain=total; best_record={'operation':'reforge','placement_gain':total,'holder_index':index,'item_index':item_index,'outcomes':tuple(conditional)}
        # One offered tool is valued by its best next use. Existing multiple
        # reforgers require subsequent observed inventories, never duplicate use.
        if best_gain>gain:
            gain=best_gain; records=[best_record]
    return gain,tuple(records)

def item_choices(context):
    from .choices import pair, evidence, selected, hold_option
    from .planning import best_choice_fit
    snapshot=context.snapshot; data=context.data
    if read(snapshot,data,'item_offers') is None:
        return ()
    if read(snapshot,data,'choice_kind')!='item' or read(snapshot,data,'item_offers_complete') is not True:
        return (paused('Complete positive item choice required',domain='item'),)
    base=best_choice_fit(context,{})
    options=[]
    for row in read(snapshot,data,'item_offers'):
        id=row['item_id']
        if category(id,data)=='tool':
            tool=data.entities[id].values.get('tool_kind')
            if tool is None or tool.value not in ('remover','reforger'):
                raise DataError(f'Item tool model unavailable: {id}')
        gain,error,before,after,baseline,changed=pair(context,{'item_bench':tuple(read(snapshot,data,'item_bench'))+(id,)},baseline=base)
        fit=selected(after)[0]
        if 'item' not in fit.terms:
            raise DataError('Item fit unavailable for choice')
        payload={'operation':'pick','slot':row['slot'],'item_id':id,'placement_gain':gain,'best_comp':fit.comp_id,'cost_units':'placement',**evidence(before,after,baseline,changed)}
        options.append(ScoredOption(f'item:pick:{row["slot"]}:{id}','pick',payload,fit.score,error,'best_comp_item_choice'))
    if not options:
        return ()
    options.sort(key=lambda o:(o.expected_placement,o.payload['item_id'] not in context.data.guides[o.payload['best_comp']].carousel,o.option_id))
    best=options[0]
    return (Advice('item','Take item','act_this_phase',min(best.payload['before']['confidence'],best.payload['after']['confidence']),'best_comp_item_choice',
        {'placement_gain':best.payload['placement_gain']},('item_offers','item_offers_complete','item_bench','round'),max(0,best.payload['placement_gain']),
        option_id=best.option_id,payload=best.payload,options=tuple(options)+(hold_option(base[1],domain='item'),)),)



def reforge_options(context,distribution,baseline_fit,baseline_realized,selected,board,bench):
    from math import isclose
    import numpy as np
    data=context.data; options=[]; information=[]
    reforgers=[id for id in bench if category(id,data)=='tool' and data.entities[id].values.get('tool_kind') and data.entities[id].values['tool_kind'].value=='reforger']
    if not reforgers:
        return (),()
    pools=data.static.get('reforge_pools')
    for index,unit in enumerate(board.units+board.bench):
        role=data.entities[unit.unit_id].values.get('item_class')
        if role is None:
            raise DataError('Reforger holder class unavailable')
        for item_index,item in enumerate(unit.items):
            if category(item,data)!='finished':
                continue
            item_role=data.entities[item].values.get('item_class')
            if item_role is None:
                raise DataError('Reforger item class unavailable')
            if item_role.value in (role.value,'utility'):
                continue
            outcomes=pools.value.get(item) if pools else None
            if not outcomes:
                information.append(paused(f'Sourced reforge outcomes unavailable: {item}',domain='item'))
                continue
            if any(row['probability']<=0 for row in outcomes) or not isclose(sum(row['probability'] for row in outcomes),1):
                raise DataError('Reforge probabilities must be positive and sum to one')
            records=[]; paired=None; fit_gain=correction=tempo=0.0; after_value=0.0; base_line=None
            for row in outcomes:
                probability=row['probability']; id=row['item_id']
                equipped=list(unit.items); equipped[item_index]=id
                changed=Board(tuple(replace(u,items=tuple(equipped)) if i==index else u for i,u in enumerate(board.units)),
                    tuple(replace(u,items=tuple(equipped)) if i+len(board.units)==index else u for i,u in enumerate(board.bench)),None)
                remaining=list(bench); remaining.remove(reforgers[0])
                fit_delta=baseline_fit-weighted_fit(changed_context(context,changed,remaining),distribution)
                holder_delta=realized(changed,data)-baseline_realized
                if fit_delta>0 and holder_delta>0:
                    holder_delta=max(0,holder_delta-fit_delta)
                gain,error,before,after=paired_value(context.snapshot,context.history,data,context.plan.target,(selected.line,),SimulationEffects(item_state=changed,item_bench_state=tuple(remaining)),
                    rollouts=int(tunable(data,'rollouts_reroll')),opponents=context.opponents,seed=context.seed,base_effects=context.effects,backup_id=context.plan.backup)
                vector=np.asarray(before[0].rollout_placements)-np.asarray(after[0].rollout_placements)
                paired=probability*vector if paired is None else paired+probability*vector
                fit_gain+=probability*fit_delta; correction+=probability*holder_delta; tempo+=probability*gain
                after_value+=probability*realized(changed,data); base_line=before[0]
                records.append({'probability':probability,'item_id':id,'item_fit_gain':fit_delta,'realized_holder_gain':holder_delta,'tempo_gain':gain,
                    'before':before[0].to_dict(),'after':after[0].to_dict(),'after_item_state':changed.to_dict(),'after_item_bench':tuple(remaining)})
            total=fit_gain+correction+tempo
            if total<=0:
                continue
            error=float(np.std(paired,ddof=1)/np.sqrt(len(paired))) if len(paired)>1 else 0.0
            payload={'operation':'reforge','item_id':item,'holder':unit.unit_id,'holder_index':index,'item_index':item_index,'consume_tool':reforgers[0],
                'item_fit_gain':fit_gain,'realized_holder_gain':correction,'tempo_gain':tempo,'placement_gain':total,'before_realized':baseline_realized,'after_realized':after_value,
                'before':base_line.to_dict(),'outcomes':tuple(records),'cost_units':'placement'}
            options.append(ScoredOption(f'item:reforge:{index}:{item_index}:{item}','reforge',payload,base_line.expected_placement+baseline_fit-total,error,'wrong_class_reforge_expectation'))
    return tuple(options),tuple(information)

def advice(context):
    if not available(context):
        return ()
    try:
        if read(context.snapshot,context.data,'item_offers') is not None:
            return item_choices(context)
        if context.plan.target is None or context.recommended_board is None:
            return ()
        board=owned_board(context.snapshot,context.data); data=context.data; bench=list(read(context.snapshot,context.data,'item_bench'))
        distribution=weights(context); baseline_fit=weighted_fit(context,distribution)
        baseline_realized=realized(board,data)
        target=data.guides[context.plan.target]
        desired={id for comp,_ in distribution for id in holders(comp,data)}
        retained={id for comp,_ in distribution for id in data.guides[comp].units}
        tools=[id for id in bench if category(id,data)=='tool']
        removers=[id for id in tools if data.entities[id].values.get('tool_kind') and data.entities[id].values['tool_kind'].value=='remover']
        capacity=int(static(data,'rules_flags')['item_slots_max'])
        selected=next((r for r in context.line_results.get(context.plan.target,()) if context.plan.line and r.line.id==context.plan.line.id),None)
        if selected is None:
            return ()
        candidates=[]
        def append(operation,changed,remaining,payload,*,holder_correction=False,gold_delta=0):
            fit_gain=baseline_fit-weighted_fit(changed_context(context,changed,remaining),distribution)
            before_realized=baseline_realized; after_realized=realized(changed,data)
            correction=after_realized-before_realized if holder_correction else 0.0
            # A single item benefit cannot enter both the abstract fit change and
            # its realized-holder correction. Component conversion uses fit only.
            if holder_correction and fit_gain>0 and correction>0:
                correction=max(0,correction-fit_gain)
            candidates.append((operation,changed,tuple(remaining),payload,fit_gain,correction,gold_delta,before_realized,after_realized))
        for index,unit in enumerate(board.units):
            interim=unit.unit_id not in desired
            if interim and unit.unit_id in retained and not removers:
                continue
            # Current exact recipes can consume a component already on this unit.
            for item,recipe in static(data,'item_recipes').items():
                remaining=list(bench); equipped=list(unit.items); consumed=[]
                for component in recipe:
                    if component in remaining:
                        remaining.remove(component); consumed.append(component)
                    elif component in equipped and category(component,data)=='component':
                        equipped.remove(component); consumed.append(component)
                    else:
                        break
                else:
                    if len(equipped)>=capacity:
                        continue
                    changed=Board(tuple(replace(u,items=tuple(equipped)+(item,)) if i==index else u for i,u in enumerate(board.units)),board.bench,None)
                    append('build',changed,remaining,{'item_id':item,'holder':unit.unit_id,'holder_index':index,'consume_components':tuple(consumed),'remover_reserved':bool(interim and unit.unit_id in retained)})
            for item in sorted(set(bench)):
                kind=category(item,data)
                if kind not in ('component','finished'):
                    continue
                equipped=list(unit.items); resulting=item; consumed=(item,)
                if kind=='component':
                    on_unit=[id for id in equipped if category(id,data)=='component']
                    if on_unit:
                        matches=[id for id,recipe in static(data,'item_recipes').items() if sorted(recipe)==sorted((item,on_unit[0]))]
                        if len(matches)!=1:
                            raise DataError('In-place component recipe unavailable or ambiguous')
                        resulting=matches[0]; equipped.remove(on_unit[0]); consumed=(item,on_unit[0]); kind='finished'
                if len(equipped)>=capacity:
                    continue
                remaining=list(bench); remaining.remove(item)
                changed=Board(tuple(replace(u,items=tuple(equipped)+(resulting,)) if i==index else u for i,u in enumerate(board.units)),board.bench,None)
                append('place_component' if category(item,data)=='component' and resulting==item else 'place_item',changed,remaining,
                    {'item_id':resulting,'holder':unit.unit_id,'holder_index':index,'consume_components':consumed if category(item,data)=='component' else (), 'remover_reserved':bool(interim and unit.unit_id in retained)},holder_correction=category(item,data)=='finished')
        # A sale or a remover explicitly frees every equipped item, not just the
        # desired finished item. Capacity and leftover inventory are retained.
        for index,unit in enumerate(board.units+board.bench):
            if not unit.items:
                continue
            on_board=index<len(board.units)
            leaving=unit.unit_id not in retained and unit not in context.recommended_board.units
            if not leaving and not removers:
                continue
            if leaving:
                units=tuple(u for i,u in enumerate(board.units) if i!=index)
                held=tuple(u for i,u in enumerate(board.bench) if i!=index-len(board.units))
                freed=Board(units,held,None); donor=None; operation='sell_and_transfer'
                from .bench import current_sale_value
                gold_delta=current_sale_value(unit,context)
                remaining=list(bench)
            else:
                units=tuple(replace(u,items=()) if on_board and i==index else u for i,u in enumerate(board.units))
                held=tuple(replace(u,items=()) if not on_board and i==index-len(board.units) else u for i,u in enumerate(board.bench))
                freed=Board(units,held,None); donor=index if on_board else None; operation='remove_and_transfer'; gold_delta=0
                remaining=list(bench); remaining.remove(removers[0])
            changed,allocation=transfer_items(freed,donor,unit.items,data,desired)
            if not allocation[1]:
                continue
            remaining.extend(allocation[2])
            transfers=tuple({'item_id':item,'holder_index':i,'holder':changed.units[i].unit_id} for item,i in allocation[1])
            payload={'from':unit.unit_id,'from_index':index,'item_ids':unit.items,'transfers':transfers,'holder':transfers[0]['holder'],
                'consume_tool':None if leaving else removers[0],'gold_gain':gold_delta}
            append(operation,changed,remaining,payload,holder_correction=True,gold_delta=gold_delta)
        # Only build/place-component simulations share the specified slam cap.
        cheap=lambda row:row[4]+row[5]
        slams=[row for row in candidates if row[0] in ('build','place_component')]
        slams.sort(key=lambda row:(-cheap(row),row[3].get('item_id') not in target.items.get(row[3].get('holder'),()),row[3].get('item_id',''),row[3].get('holder_index',0)))
        candidates=[row for row in candidates if row[0] not in ('build','place_component')]+slams[:int(tunable(data,'slam_candidate_cap'))]
        options=[]; baseline_result=None
        for operation,changed,remaining,payload,fit_gain,correction,gold_delta,before_realized,after_realized in candidates:
            gain,error,before,after=paired_value(context.snapshot,context.history,data,context.plan.target,(selected.line,),
                SimulationEffects(item_state=changed,item_bench_state=tuple(remaining),gold_delta=gold_delta),rollouts=int(tunable(data,'rollouts_reroll')),opponents=context.opponents,
                seed=context.seed,base_effects=context.effects,backup_id=context.plan.backup)
            total=gain+fit_gain+correction; baseline_result=before[0]
            payload={'operation':operation,**payload,'item_fit_gain':fit_gain,'realized_holder_gain':correction,'before_realized':before_realized,'after_realized':after_realized,
                'tempo_gain':gain,'placement_gain':total,'cost_units':'placement','before':before[0].to_dict(),'after':after[0].to_dict(),
                'before_item_state':board.to_dict(),'after_item_state':changed.to_dict(),'after_item_bench':remaining,'open_weights':distribution}
            token=f'item:{operation}:{payload.get("item_id",payload.get("from"))}:{payload.get("holder_index",payload.get("from_index"))}'
            options.append(ScoredOption(token,operation,payload,after[0].expected_placement+baseline_fit-fit_gain-correction,error,'item_tempo_fit_and_holder_correction'))
        reforges,information=reforge_options(context,distribution,baseline_fit,baseline_realized,selected,board,bench)
        options.extend(reforges)
        if reforges and baseline_result is None:
            baseline_result=paired_value(context.snapshot,context.history,data,context.plan.target,(selected.line,),SimulationEffects(),rollouts=int(tunable(data,'rollouts_reroll')),opponents=context.opponents,seed=context.seed,base_effects=context.effects,backup_id=context.plan.backup)[2][0]
        if baseline_result:
            hold=ScoredOption('item:hold','hold',{'operation':'hold','placement_gain':0.0,'cost_units':'placement','before':baseline_result.to_dict(),'after':baseline_result.to_dict()},baseline_result.expected_placement+baseline_fit,0.0,'unchanged_same_seed_baseline')
            options.append(hold)
        if not options:
            baseline=assignment(context.plan.target,context)
            return (Advice('item','Hold components','information',baseline.confidence,'item_option_value',payload={'operation':'hold','assignment':baseline.numbers['assignment']}),)+information
        best=max(options,key=lambda option:(option.payload['placement_gain'],option.option_id))
        if best.payload['placement_gain']<=0:
            return (Advice('item','Hold items','information',float(tunable(data,'confidence_medium_min')),'item_gain_not_positive',option_id='item:hold',payload={'operation':'hold'},options=tuple(options)),)+information
        return (Advice('item','Apply item operation','act_this_phase',float(tunable(data,'confidence_medium_min')),'item_tempo_fit_and_holder_correction',
            numbers={'placement_gain':best.payload['placement_gain'],'item_fit_gain':best.payload['item_fit_gain'],'realized_holder_gain':best.payload['realized_holder_gain'],'tempo_gain':best.payload['tempo_gain']},
            validity=('board','bench','item_bench','gold','round'),placement_impact=best.payload['placement_gain'],option_id=best.option_id,payload=best.payload,options=tuple(options)),)+information
    except (DataError,KeyError) as error:
        return (paused(str(error),domain='item'),)
