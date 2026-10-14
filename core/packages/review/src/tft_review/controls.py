"""Causal accepted UI controls, kept separate from the raw capture ledger."""
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from math import isfinite
import re

from tft_data.models import freeze
from tft_engine import FieldValue, GameSnapshot


def _pin_schedule(payload):
    reference, schedule = payload.get('pin'), payload.get('schedule')
    if reference is None and schedule is None and 'pin' in payload and 'schedule' in payload:
        return None
    if not isinstance(reference, Mapping) or not isinstance(schedule, Mapping):
        raise ValueError('Session pin requires a reference and schedule')
    if any(not isinstance(reference.get(name), str) or not reference[name].strip()
        for name in ('comp_id', 'line_id', 'seed')):
        raise ValueError('Session pin reference is incomplete')
    if (not re.fullmatch(r'[0-9]{1,20}', reference['seed'])
        or int(reference['seed']) > 2**64-1
        or reference['line_id'] != schedule.get('id')):
        raise ValueError('Session pin reference does not match its schedule')
    if set(schedule)-{'id', 'levels', 'rolls', 'stabilize', 'floor_options', 'family_id'}:
        raise ValueError('Session pin schedule has unsupported fields')
    for name in ('levels', 'rolls'):
        table = schedule.get(name, {})
        if not isinstance(table, Mapping):
            raise ValueError('Session pin schedule requires round mappings')
        for round_id, value in table.items():
            if not isinstance(round_id, str) or not re.fullmatch(r'[1-9][0-9]*-[1-9][0-9]*', round_id):
                raise ValueError('Session pin schedule has an invalid round')
            if name == 'levels':
                valid = type(value) is int and value > 0
            else:
                valid = type(value) in (int, float) and isfinite(value) and value >= 0
            if not valid:
                raise ValueError('Session pin schedule has an invalid level or gold floor')
    floors = schedule.get('floor_options', ())
    if (type(schedule.get('stabilize', False)) is not bool
        or not isinstance(floors, (tuple, list))
        or any(type(value) not in (int, float) or not isfinite(value) or value < 0 for value in floors)
        or (schedule.get('family_id') is not None and not isinstance(schedule['family_id'], str))):
        raise ValueError('Session pin schedule metadata is invalid')
    return schedule


@dataclass(frozen=True)
class ControlProjection:
    snapshot: GameSnapshot
    provenance: Mapping

    def __post_init__(self):
        object.__setattr__(self, 'provenance', freeze(self.provenance))

    def to_dict(self, *, through_seq):
        """Small explicit overlay evidence, not a replacement raw snapshot."""
        return {'fields': {name: value for name, value in self.snapshot.to_dict()['fields'].items()
                if name == 'pinned_line' and value['source'] == 'ui_pin'},
            'provenance': dict(self.provenance), 'through_seq': through_seq}


def project_session_controls(snapshot, events, *, through_seq):
    """Apply only earlier durable controls available by this capture's time.

    The log must belong to this game and contain its original data pin. A pin's
    read time is its acceptance time, never a later capture time. Callers pass
    each historical frame's own earlier sequence, not the current frame's.
    """
    if not isinstance(snapshot, GameSnapshot):
        raise TypeError('Session controls require a GameSnapshot')
    if type(through_seq) is not int or through_seq < 0:
        raise ValueError('Session controls require a nonnegative sequence')
    events = tuple(events)
    if not events or events[0]['kind'] != 'game_start':
        raise ValueError('Session controls require a game_start')
    start = events[0]['payload']
    if str(start['game_id']) != snapshot.game_id:
        raise ValueError('Session controls belong to another game')
    pin, provenance, mode = None, {}, start.get('mode')
    for event in events:
        at = datetime.fromisoformat(event['timestamp'])
        if at.tzinfo is None:
            raise ValueError('Session control timestamps require a timezone')
        if event['seq'] > through_seq or at > snapshot.captured_at:
            continue
        if event['kind'] == 'mode_change':
            mode = event['payload']['mode']
        if event['kind'] in {'mode_change', 'session_detached', 'capture_gap', 'game_end',
            'session_controls_reset'}:
            if event['kind'] == 'session_controls_reset' and (
                event['payload'].get('game_id') != snapshot.game_id
                or event['payload'].get('data_snapshot_id') != start.get('data_snapshot_id')):
                raise ValueError('Session pin reset does not match the original game/data pin')
            pin = None
            provenance['reset'] = {'log_seq': event['seq'], 'timestamp': event['timestamp'],
                'kind': event['kind'], 'reason': event['payload'].get('reason', 'mode_changed')}
        if event['kind'] == 'line_pin':
            payload = event['payload']
            if mode != 'live':
                raise ValueError('Session pin was not accepted in Live mode')
            if (not isinstance(start.get('data_snapshot_id'), str) or not start['data_snapshot_id']
                or payload.get('game_id') != snapshot.game_id
                or payload.get('data_snapshot_id') != start.get('data_snapshot_id')):
                raise ValueError('Session pin does not match the original game/data pin')
            if not isinstance(payload.get('delivery_revision'), str) or not re.fullmatch(
                r'sha256:[0-9a-f]{64}', payload['delivery_revision']):
                raise ValueError('Session pin requires a delivery revision')
            schedule = _pin_schedule(payload)
            reference = payload['pin']
            if schedule is None:
                pin = None
                provenance['reset'] = {'log_seq': event['seq'], 'timestamp': event['timestamp'],
                    'kind': event['kind'], 'reason': 'unpin'}
            else:
                pin = FieldValue(schedule, at, 'ui_pin')
            provenance['line_pin'] = {'log_seq': event['seq'], 'timestamp': event['timestamp'],
                'delivery_revision': payload.get('delivery_revision'), 'pin': reference}
    fields = dict(snapshot.fields)
    if fields.get('pinned_line') and fields['pinned_line'].source == 'ui_pin':
        del fields['pinned_line']
    if pin is not None:
        fields['pinned_line'] = pin
    return ControlProjection(replace(snapshot, fields=fields), provenance)
