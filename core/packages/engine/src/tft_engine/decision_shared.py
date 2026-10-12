"""Shared choice transformations; no hidden inventory or random state."""
from dataclasses import replace
from .models import Board, Unit
from .shop_math import canonical_id
from .power import static
from tft_data.models import DataError


def add_copy(board,unit_id,data):
    units=list(board.units); bench=list(board.bench)
    bench.append(Unit(unit_id))
    pool=canonical_id(unit_id,data)
    for stars in (1,2):
        all_units=units+bench
        matches=[i for i,u in enumerate(all_units) if canonical_id(u.unit_id,data)==pool and u.stars==stars]
        while len(matches)>=3:
            merge=matches[:3]; first=all_units[merge[0]]
            upgraded=replace(first,stars=stars+1,items=tuple(item for i in merge for item in all_units[i].items))
            if upgraded.items:
                capacity=static(data,'rules_flags').get('item_slots_max')
                if capacity is None or len(upgraded.items)>capacity:
                    raise DataError('Star-merge item overflow requires a positively modelled inventory return')
            board_count=len(units)
            units=[upgraded if i==merge[0] else u for i,u in enumerate(all_units[:board_count]) if i not in merge[1:]]
            bench=[upgraded if i==merge[0] else u for i,u in enumerate(all_units[board_count:],board_count) if i not in merge[1:]]
            all_units=units+bench
            matches=[i for i,u in enumerate(all_units) if canonical_id(u.unit_id,data)==pool and u.stars==stars]
    return Board(tuple(units),tuple(bench))
