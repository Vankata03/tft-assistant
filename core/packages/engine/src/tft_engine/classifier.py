"""Weighted comp overlap; labels never feed absolute board power."""
from dataclasses import dataclass
from typing import Mapping
from .models import Board
from .power import tunable

@dataclass(frozen=True)
class CompSimilarity:
    comp_id: str
    similarity: float
    label: str


def classify(board: Board | Mapping[str, float], data, *, limit: int | None = None):
    if isinstance(board, Board):
        present = {u.unit_id: 1.0 for u in board.units}
        bench_weight = float(tunable(data, 'classifier_weights')['bench'])
        for unit in board.bench:
            present.setdefault(unit.unit_id, bench_weight)
    else:
        present = board
    weights = tunable(data, 'classifier_weights')
    threshold = float(tunable(data, 'classifier_threshold'))
    results = []
    for guide in data.guides.values():
        scores = {id: float(weights['carry'] if id in guide.carry_ids else weights['key'] if id in getattr(guide,'key_ids',()) else weights['other']) for id in set(guide.units)}
        total = sum(scores.values())
        similarity = sum(weight * min(1.0, max(0.0, present.get(id, 0.0))) for id,weight in scores.items()) / total if total else 0.0
        results.append(CompSimilarity(guide.id, similarity, guide.id if similarity >= threshold else 'no comp'))
    results.sort(key=lambda item: (-item.similarity, item.comp_id))
    return tuple(results if limit is None else results[:limit])
