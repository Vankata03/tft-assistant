"""Align captured alive opponent HP with model estimates by stable player ID."""
from collections.abc import Mapping
from tft_data.models import DataError
from math import isfinite


def lobby_certificate_qualified(snapshot, data):
    """Only fresh literal positive, sufficiently confident coverage is a roster."""
    from .planning import field_age
    if data is None:
        return False
    certificate = snapshot.fields.get('lobby_complete')
    if certificate is None or certificate.value is not True or certificate.read_at > snapshot.captured_at:
        return False
    minimum = float(data.tunable('confidence_show_min'))
    if not isfinite(minimum) or not 0 <= minimum <= 1:
        return False
    roster = snapshot.fields.get('lobby')
    return all(field is not None and field.read_at <= snapshot.captured_at
        and field.confidence > 0 and field.confidence >= minimum
        and field.age_seconds(snapshot.captured_at) <= field_age(data, name, snapshot)
        for name, field in (('lobby_complete', certificate), ('lobby', roster)))


def alive_lobby(snapshot,data=None):
    from .planning import read
    value=lambda name:read(snapshot,data,name) if data is not None else snapshot.field(name)
    if not lobby_certificate_qualified(snapshot, data):
        raise DataError('Fresh positive confident lobby_complete certificate required')
    players=value('lobby')
    if not isinstance(players,Mapping):
        raise DataError('Lobby requires an ID-to-HP mapping')
    own=value('player_id') or value('local_player_id')
    result={}
    for id,value in sorted(players.items()):
        if id==own or (isinstance(value,Mapping) and value.get('is_self')):
            continue
        raw = value['hp'] if isinstance(value,Mapping) else value
        if type(raw) not in (int, float) or not isfinite(raw) or raw < 0:
            raise DataError('Lobby HP is not a qualified finite observation')
        hp=float(raw)
        if hp>0:
            result[id]=hp
    if not result:
        raise DataError('No alive opponents in lobby')
    return result
