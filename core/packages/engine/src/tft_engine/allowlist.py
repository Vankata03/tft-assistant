"""The only Engine calls available to Baseline features during a game.

These functions consume static data and the player's own board only. They
have no access to history, sightings, opponent inference or live advice.
"""
from .power import strength as _strength, win_probability
from .growth import growth_curve_lookup
from .capacity import CapacityEvidence, CapacityModel


def strength(board,level,data,*,capacity=None):
    evidence=CapacityEvidence(**capacity) if isinstance(capacity,dict) else capacity
    CapacityModel(data).check(board,level,evidence,check_observed=True)
    return _strength(board,level,data,capacity=evidence)

__all__ = ['strength', 'win_probability', 'growth_curve_lookup']
