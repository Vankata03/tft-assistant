"""Fresh snapshot evidence for the static capacity boundary."""
from tft_data.models import DataError
from .capacity import CapacityModel, CapacityEvidence, integral

def evidence_from_snapshot(snapshot,data,*,item_bench=None):
    from .planning import read
    model=CapacityModel(data)
    held=read(snapshot,data,'held_augments')
    if model.augments and (held is None or read(snapshot,data,'held_augments_complete') is not True):
        raise DataError('Fresh complete held augments required for capacity')
    inventory=read(snapshot,data,'item_bench') if item_bench is None else item_bench
    if model.items and (inventory is None or read(snapshot,data,'item_inventory_complete') is not True):
        raise DataError('Fresh complete item inventory required for capacity')
    observed=read(snapshot,data,'team_slot_budget')
    if 'team_slot_budget' in snapshot.fields:
        if observed is None:
            raise DataError('Observed team slot budget is stale')
        integral(observed,'observed team slot budget',1)
    return CapacityEvidence(held,inventory,observed)
