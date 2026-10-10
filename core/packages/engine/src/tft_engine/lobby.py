"""Align captured alive opponent HP with model estimates by stable player ID."""
from collections.abc import Mapping
from tft_data.models import DataError


def alive_lobby(snapshot):
    players=snapshot.field('lobby')
    if not isinstance(players,Mapping):
        raise DataError('Lobby requires an ID-to-HP mapping')
    own=snapshot.field('player_id') or snapshot.field('local_player_id')
    result={}
    for id,value in sorted(players.items()):
        if id==own or (isinstance(value,Mapping) and value.get('is_self')):
            continue
        hp=float(value['hp'] if isinstance(value,Mapping) else value)
        if hp>0:
            result[id]=hp
    if not result:
        raise DataError('No alive opponents in lobby')
    return result
