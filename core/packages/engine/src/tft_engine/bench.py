"""Fixed bench priorities shared by transitions, roll gold and shop advice."""
from .shop_math import canonical_id, owned_copies, key_goals
from .power import static, keyed


def bench_priority(board,data,*,target=None,backup=None,recommended=None):
    target_keys=key_goals(data.guides[target],data) if target in data.guides else {}
    backup_keys=key_goals(data.guides[backup],data) if backup in data.guides else {}
    present=owned_copies(board,data)
    recommended_pools={canonical_id(u.unit_id,data) for u in (recommended or board).units}
    priorities=[]
    for index,unit in enumerate(board.bench):
        pool=canonical_id(unit.unit_id,data)
        copies=present.get(pool,0)
        threshold=9 if copies>=3 else 3
        progress=copies%threshold
        category=0 if pool in target_keys else 1 if pool in backup_keys else 2 if pool in recommended_pools and progress>=2 else 3 if unit.items else 4
        priorities.append((category,-progress,index))
    return tuple(sorted(priorities))


def roll_sale_indices(board,data,*,target=None,backup=None):
    return tuple(index for category,_,index in bench_priority(board,data,target=target,backup=backup) if category>1)


def sale_value(unit,data):
    return float(keyed(keyed(static(data,'sell_values'),data.entities[unit.unit_id].cost),unit.stars))
