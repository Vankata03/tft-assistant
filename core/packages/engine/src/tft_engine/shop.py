"""Analytic champion shop calls consistent with the Line's gold boundary."""
from .planning import read
from .capacity_fields import evidence_from_snapshot
from collections.abc import Mapping
from .models import Advice, ScoredOption, Board, _encode
from .planning import required, owned_board
from .power import strength, tunable, static, stage_tunable
from .shop_math import canonical_id, owned_copies, key_goals
from .transition import strongest_owned_board
from .bench import bench_priority, current_sale_value
from .decision_shared import add_copy


def advice(context):
    snapshot,data,plan=context.snapshot,context.data,context.plan
    if required(snapshot,data,('shop','gold','board','bench')) or plan.target is None or context.recommended_board is None:
        return ()
    selected=next((r for r in context.line_results.get(plan.target,()) if plan.line and r.line.id==plan.line.id),None)
    if selected is None or not selected.projections:
        return ()
    floor=selected.projections[0].planned_gold
    if floor is None:
        return ()
    capacity=evidence_from_snapshot(snapshot,data)
    board=owned_board(snapshot,data); copies=owned_copies(board,data)
    target=key_goals(data.guides[plan.target],data)
    alternatives=plan.candidates if plan.status=='open' else (plan.backup,)
    other={pool:goal for id in alternatives if id in data.guides for pool,goal in key_goals(data.guides[id],data).items()}
    gold=float(read(snapshot,data,'gold')); allowance=max(0,gold-floor)
    rolling=bool(plan.line and snapshot.round_id in plan.line.rolls)
    current=strength(context.recommended_board,int(read(snapshot,data,'level')),data,capacity=capacity)
    options=[]; buys=[]
    for index,row in enumerate(read(snapshot,data,'shop')):
        if not isinstance(row,Mapping):
            row={'slot':index,'unit_id':row}
        id=row.get('unit_id')
        if id not in data.entities or data.entities[id].kind not in ('unit','unit_form'):
            continue
        pool=canonical_id(id,data); count=copies.get(pool,0)
        cost=float(row.get('cost',data.entities[id].cost)); slot=row.get('slot',index)
        preview=add_copy(board,id,data)
        strongest=strongest_owned_board(preview,int(read(snapshot,data,'level')),data,target=plan.target,round_id=snapshot.round_id,capacity=capacity)
        gain=strength(strongest,int(read(snapshot,data,'level')),data,capacity=capacity)-current
        reason='target_key' if pool in target and count<target[pool] else 'backup_key' if pool in other and count<other[pool] else 'pair' if count%3 in (1,2) and count<9 else 'power' if gain>=stage_tunable(data,'board_power_buy_min',snapshot.round_id) else None
        budget=max(0,gold-plan.line.rolls[snapshot.round_id]) if rolling else allowance
        allowed=bool(reason and cost<=gold and (reason=='target_key' and not rolling or cost<=budget))
        priorities=bench_priority(preview,data,target=plan.target,backup=plan.backup,recommended=strongest)
        overflow_indices=tuple(i for _,_,i in priorities[int(static(data,'bench_size')):])
        overflow=tuple(preview.bench[i].unit_id for i in overflow_indices)
        overflow_gold=sum(current_sale_value(preview.bench[i],context) for i in overflow_indices)
        after=Board(preview.units,tuple(u for i,u in enumerate(preview.bench) if i not in overflow_indices),preview.trait_counts)
        if preview.bench and preview.bench[-1].unit_id==id and len(preview.bench)-1 in overflow_indices:
            allowed=False
        payload={'slot':slot,'unit_id':id,'cost':cost,'cost_units':'gold','eligible_reason':reason,'allowed':allowed,'power_gain':gain,'overflow_sells':overflow,'overflow_gold':overflow_gold,'after_bench':_encode(after.bench),'overflow_items_returned':tuple(item for i in overflow_indices for item in preview.bench[i].items)}
        options.append(ScoredOption(f'shop:{slot}:{id}','buy',payload,reason=reason or 'no_improvement'))
        if allowed:
            buys.append({'slot':slot,'unit_id':id,'cost':cost,'reason':reason,**({'overflow_sells':overflow,'overflow_gold':overflow_gold} if overflow else {})})
            gold+=overflow_gold-cost; allowance=max(0,allowance+overflow_gold-cost); board=after; copies=owned_copies(board,data)
            current=strength(strongest,int(read(snapshot,data,'level')),data,capacity=capacity)
    items=[]
    if options:
        items.append(Advice('shop','Buy highlighted units' if buys else 'Hold shop','act_this_phase' if buys else 'information',float(tunable(data,'confidence_medium_min')),'analytic_shop',
            validity=('shop','gold','board','bench','round'),decision_id=f'{snapshot.snapshot_id}:shop',option_id='shop',
            payload={'buys':buys,'allowance':max(0,float(read(snapshot,data,'gold'))-floor),'cost_units':'gold'},options=tuple(options)+(ScoredOption('shop:hold','hold',{'operation':'hold','cost_units':'gold','gold_cost':0},reason='analytic_unchanged_baseline'),)))
    # Only the lowest priority inventory can be sold for interest.
    interest=static(data,'interest'); tick=float(interest['gold_per_tick'])
    if not rolling and gold<float(interest['cap'])*tick:
        next_tick=(int(gold//tick)+1)*tick
        bottom=[i for category,_,i in reversed(bench_priority(board,data,target=plan.target,backup=plan.backup,recommended=context.recommended_board)) if category==4]
        sell=[]; proceeds=0
        for index in bottom:
            sell.append(index); proceeds+=current_sale_value(board.bench[index],context)
            if gold+proceeds>=next_tick:
                items.append(Advice('shop','Sell low-priority units for interest','act_this_phase',float(tunable(data,'confidence_medium_min')),'interest_breakpoint',
                    validity=('gold','board','bench','round'),option_id='shop:interest',payload={'sell':tuple(board.bench[i].unit_id for i in sell),'gold_gain':proceeds,'gold_after':gold+proceeds,'cost_units':'gold'}))
                break
    return tuple(items)
