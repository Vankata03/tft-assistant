"""Refresh-derived values; scientific model computations remain in the Engine."""

import json
from collections import Counter

from .models import TaggedValue, plain


def default_lines(guides, entities):
    result = {}
    for cost in range(1, 6):
        candidates = []
        for guide in guides.values():
            carry = next(
                (entities.get(id) for id in guide.carry_ids if id in entities), None
            )
            if carry and carry.cost == cost and guide.line:
                candidates.append(json.dumps(plain(guide.line), sort_keys=True))
        if candidates:
            winner = Counter(candidates).most_common(1)[0][0]
            result[str(cost)] = {"line": json.loads(winner)}
        else:
            result[str(cost)] = {"roll_level": cost + 4}
    return TaggedValue(
        result,
        "default",
        citation="Derived from the most common supplied Guide line per carry cost; fallback roll levels are specified in docs/spec/tunables.md.",
        family="computed",
    )
