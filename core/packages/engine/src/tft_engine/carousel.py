"""Remaining carousel options use the shared choice valuation, without predicting picks."""
from .planning import read
from .planning import owned_board, paused, required, best_choice_fit
from .decision_shared import add_copy
from .choices import pair, evidence, selected, hold_option
from .items import available
from .models import Advice, ScoredOption
from tft_data.models import DataError


def advice(context):
    snapshot,data=context.snapshot,context.data
    if read(snapshot,data,'carousel') is None:
        return ()
    missing=required(snapshot,data,('carousel','carousel_complete','board','bench','item_bench','item_inventory_complete'))
    if missing or read(snapshot,data,'carousel_complete') is not True or not available(context):
        return (paused('Positive complete carousel and item inventory required',missing=missing,domain='carousel'),)
    try:
        base=best_choice_fit(context,{})
        options=[]
        for row in read(snapshot,data,'carousel'):
            board=add_copy(owned_board(snapshot,data),row['unit_id'],data)
            gain,error,before,after,baseline,changed=pair(context,{'board':board,'bench':board.bench,
                'item_bench':tuple(read(snapshot,data,'item_bench'))+(row['item_id'],)},baseline=base)
            fit=selected(after)[0]
            if 'item' not in fit.terms:
                raise DataError('Item model unavailable for carousel choice')
            payload={'operation':'pick',**row,'best_comp':fit.comp_id,'placement_gain':gain,'cost_units':'placement',**evidence(before,after,baseline,changed)}
            options.append(ScoredOption(f'carousel:{row["slot"]}:{row["unit_id"]}:{row["item_id"]}','pick',payload,fit.score,error,'unit_progress_and_item_fit'))
        if not options:
            return ()
        def rank(option):
            priority=data.guides[option.payload['best_comp']].carousel
            item=option.payload['item_id']
            return (option.expected_placement,priority.index(item) if item in priority else len(priority),option.option_id)
        options.sort(key=rank); best=options[0]
        return (Advice('carousel','Take first available carousel option','act_this_phase',min(best.payload['before']['confidence'],best.payload['after']['confidence']),
            'remaining_carousel_rank',{'placement_gain':best.payload['placement_gain']},('carousel','board','bench','item_bench','round'),max(0,best.payload['placement_gain']),
            decision_id=f'{snapshot.snapshot_id}:carousel',option_id=best.option_id,payload=best.payload|{'ranking':tuple(o.option_id for o in options)},
            options=tuple(options)+(hold_option(base[1],domain='carousel'),)),)
    except (DataError,KeyError,ValueError) as error:
        return (paused(str(error),domain='carousel'),)
