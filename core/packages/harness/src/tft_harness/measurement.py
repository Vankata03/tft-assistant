"""Game-level weighting and comparative losses preserve independent sample units."""
from collections import defaultdict
from math import ceil
from random import Random


def mean_by_game(rows):
    """Average qualified rows within games, then give each game equal weight.

    None is the finite report representation of a mathematically infinite loss;
    it remains a hard miss rather than disappearing from the denominator.
    """
    grouped = defaultdict(list)
    for game_id, loss in rows:
        grouped[game_id].append(loss)
    if not grouped or any(loss is None for losses in grouped.values() for loss in losses):
        return None
    return sum(sum(losses)/len(losses) for losses in grouped.values())/len(grouped)


def paired_game_comparison(rows, *, seed, draws):
    """Paired loss differences resample whole games with equal game weights."""
    if type(seed) is not int or type(draws) is not int or draws < 2:
        raise ValueError('Bootstrap requires an integer seed and at least two draws')
    grouped = defaultdict(list)
    for game_id, candidate, reference in rows:
        grouped[game_id].append(None if candidate is None or reference is None else candidate-reference)
    unavailable = lambda reason: {'value': None, 'lower': None, 'upper': None, 'reason': reason}
    if any(value is None for values in grouped.values() for value in values):
        return unavailable('infinite_comparative_loss')
    differences = [sum(values)/len(values) for _, values in sorted(grouped.items())]
    point = sum(differences)/len(differences) if differences else None
    if len(differences) < 2:
        return unavailable('insufficient_holdout_games') | {'value': point}
    generator = Random(seed)
    samples = sorted(sum(generator.choice(differences) for _ in differences)/len(differences)
        for _ in range(draws))
    return {'value': point, 'lower': samples[max(0, ceil(draws*.025)-1)],
        'upper': samples[max(0, ceil(draws*.975)-1)], 'reason': None}
