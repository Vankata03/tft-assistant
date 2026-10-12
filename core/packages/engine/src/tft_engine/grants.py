"""Finite sourced grant/target distributions; target rules never come from display categories."""
from .planning import read
from dataclasses import replace
from tft_data.models import DataError
from .planning import owned_board
from .models import Board, Unit
from .decision_shared import add_copy


def distribution(effect,context,offer=None):
    kind=effect['effect_kind']; values=effect['values']; data=context.data
    board=owned_board(context.snapshot,context.data); rows=[]
    if kind in ('unit_grant','item_grant','risky'):
        for outcome in values['outcomes']:
            probability=float(outcome['probability']); changed=board; effects=None; changes={}
            if kind=='unit_grant':
                for id in outcome['unit_ids']:
                    changed=add_copy(changed,id,data)
                changes={'board':changed,'bench':changed.bench}
            elif kind=='item_grant':
                if read(context.snapshot,context.data,'item_bench') is None or read(context.snapshot,context.data,'item_inventory_complete') is not True:
                    raise DataError('Complete item inventory required for item grant')
                changes={'item_bench':tuple(read(context.snapshot,context.data,'item_bench'))+tuple(outcome['item_ids'])}
            else:
                from .effects import simulation
                effects=simulation(outcome['effect'],data,context.snapshot)
            rows.append((probability,changes,effects,outcome))
        return tuple(rows)
    if kind not in ('polymorph','duplicator'):
        raise DataError(f'Grant model unavailable: {kind}')
    if kind=='polymorph' and any(not isinstance(values.get(name),bool) for name in ('preserve_stars','preserve_items')):
        raise DataError('Polymorph preservation requires explicit sourced booleans')
    units=board.units+board.bench
    eligible=[i for i,u in enumerate(units) if data.entities[u.unit_id].cost in values['eligible_costs']]
    if not eligible:
        raise DataError('No positively eligible grant target')
    target=values['target']
    if target=='highest_star':
        highest=max(units[i].stars for i in eligible); eligible=[i for i in eligible if units[i].stars==highest]
        if len(eligible)>1 and values.get('tie_policy')!='uniform':
            raise DataError('Highest-star target tie policy unavailable')
    elif target=='chosen':
        id=(offer or {}).get('target_unit_id')
        eligible=[i for i in eligible if units[i].unit_id==id]
        if len(eligible)!=1:
            raise DataError('Positive unambiguous chosen unit required')
    elif target!='uniform':
        raise DataError(f'Unknown grant target policy: {target}')
    for index in eligible:
        unit=units[index]
        if kind=='duplicator':
            if values['copy_star']!='one':
                raise DataError('Only sourced one-star duplicator copies are supported')
            changed=add_copy(board,unit.unit_id,data)
            rows.append((1/len(eligible),{'board':changed,'bench':changed.bench},None,{'target_index':index,'unit_id':unit.unit_id}))
            continue
        outcomes=values['outcomes'][str(data.entities[unit.unit_id].cost+int(values['cost_delta']))]
        for outcome in outcomes:
            id=outcome['unit_id']
            if data.entities[id].kind not in ('unit','unit_form') or data.entities[id].cost!=data.entities[unit.unit_id].cost+int(values['cost_delta']):
                raise DataError('Polymorph outcome does not match sourced target cost')
            transformed=Unit(id,unit.stars if values['preserve_stars'] else 1,unit.items if values['preserve_items'] else (),unit.position)
            updated=tuple(transformed if i==index else u for i,u in enumerate(units))
            changed=Board(updated[:len(board.units)],updated[len(board.units):],None)
            changes={'board':changed,'bench':changed.bench}
            if not values['preserve_items'] and unit.items:
                held=read(context.snapshot,context.data,'item_bench')
                if held is None or read(context.snapshot,context.data,'item_inventory_complete') is not True:
                    raise DataError('Polymorph item return requires complete item inventory')
                changes['item_bench']=tuple(held)+unit.items
            rows.append((float(outcome['probability'])/len(eligible),changes,None,{'target_index':index,'from':unit.unit_id,'to':id,'stars':transformed.stars}))
    return tuple(rows)
