"""The only Engine calls available to Baseline features during a game.

These functions consume static data and the player's own board only. They
have no access to history, sightings, opponent inference or live advice.
"""
from .power import strength, win_probability
from .growth import growth_curve_lookup

__all__ = ['strength', 'win_probability', 'growth_curve_lookup']
