"""Versioned frozen replay evidence; unavailable attribution stays unavailable."""
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
import json
import math
import re

from tft_data.models import freeze

REPLAY_SCHEMA_VERSION = 1


def history_prefix(observations, *, through_seq, captured_at, controls=None):
    """Rebuild only earlier committed information observable by this capture.

    Callers replaying many frames of one log pass its SessionControlLog so each
    earlier frame's control projection is computed once, not once per frame.
    """
    from tft_engine import GameHistory, TraitSighting
    from .controls import SessionControlLog

    available_at = datetime.fromisoformat(captured_at)
    resume_at = max((datetime.fromisoformat(event['payload']['end'])
        for event in observations if event['kind'] == 'capture_gap'
        and event['seq'] <= through_seq
        and datetime.fromisoformat(event['timestamp']) <= available_at
        and datetime.fromisoformat(event['payload']['end']) <= available_at), default=None)
    snapshots, sightings = [], []
    for event in observations:
        if event['seq'] > through_seq or datetime.fromisoformat(event['timestamp']) > available_at:
            continue
        if resume_at is not None and datetime.fromisoformat(event['timestamp']) < resume_at:
            continue
        if event['kind'] == 'snapshot':
            controls = controls or SessionControlLog(observations)
            snapshot = controls.frame(event).snapshot
            if snapshot.captured_at <= available_at:
                snapshots.append(snapshot)
        elif event['kind'] == 'sighting':
            sightings.append(TraitSighting.from_dict(dict(event['payload']) | {'read_at': event['timestamp']}))
    return GameHistory(tuple(snapshots), tuple(sightings))


def json_value(value):
    """Copy public dataclass contracts to finite JSON values."""
    if is_dataclass(value):
        return {field.name: json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def frozen_json(value):
    return freeze(json.loads(json.dumps(json_value(value), allow_nan=False)))


def validate_version(version):
    if type(version) is not int or version != REPLAY_SCHEMA_VERSION:
        raise ValueError('Unsupported replay contract version')


def validate_identity(game_id, log_seq, seed):
    if not isinstance(game_id, str) or not re.fullmatch(r'[0-9]+', game_id) or int(game_id) <= 0:
        raise ValueError('Invalid replay game identity')
    if type(log_seq) is not int or log_seq < 1 or type(seed) is not int or seed < 0:
        raise ValueError('Invalid replay sequence or seed')


def validate_optional_number(value):
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
        raise ValueError('Replay optional numeric evidence must be finite or unavailable')


@dataclass(frozen=True)
class ReplayContext:
    game_id: str
    log_seq: int
    timestamp: str
    snapshot: Mapping
    game_start: Mapping
    data_snapshot_id: str
    engine_identity: Mapping
    seed: int
    prefix_through_seq: int
    evaluation: Mapping | None
    unavailable: tuple[str, ...] = ()
    validity_annotations: tuple[Mapping, ...] = ()
    v: int = REPLAY_SCHEMA_VERSION
    evaluation_overlay: Mapping | None = None

    def __post_init__(self):
        validate_version(self.v)
        validate_identity(self.game_id, self.log_seq, self.seed)
        if type(self.prefix_through_seq) is not int or not 0 <= self.prefix_through_seq < self.log_seq:
            raise ValueError('Invalid replay information prefix')
        if datetime.fromisoformat(self.timestamp).tzinfo is None:
            raise ValueError('Replay timestamp requires a timezone')
        for name in ('snapshot', 'game_start', 'engine_identity', 'evaluation', 'evaluation_overlay'):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, frozen_json(value))
        object.__setattr__(self, 'unavailable', tuple(self.unavailable))
        object.__setattr__(self, 'validity_annotations', tuple(frozen_json(row) for row in self.validity_annotations))

    def to_dict(self):
        return json_value(self)

    @classmethod
    def from_dict(cls, value):
        return cls(**value)


@dataclass(frozen=True)
class ReplayRecord:
    game_id: str
    log_seq: int
    decision_id: str
    decision: str
    advice: Mapping
    options: tuple[Mapping, ...]
    seed: int
    data_snapshot_id: str
    engine_identity: Mapping
    observed_choice: Mapping | None = None
    cost: float | None = None
    paired_uncertainty: float | None = None
    shown: Mapping | None = None
    unavailable: Mapping | None = None
    expected_placement: float | None = None
    v: int = REPLAY_SCHEMA_VERSION

    def __post_init__(self):
        validate_version(self.v)
        validate_identity(self.game_id, self.log_seq, self.seed)
        if not isinstance(self.decision_id, str) or not self.decision_id or not self.decision:
            raise ValueError('Invalid replay decision identity')
        for value in (self.cost, self.paired_uncertainty, self.expected_placement):
            validate_optional_number(value)
        for name in ('advice', 'engine_identity', 'observed_choice', 'shown'):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, frozen_json(value))
        object.__setattr__(self, 'options', tuple(frozen_json(value) for value in self.options))
        object.__setattr__(self, 'unavailable', frozen_json(self.unavailable or {}))

    def to_dict(self):
        return json_value(self)

    @classmethod
    def from_dict(cls, value):
        return cls(**value)


@dataclass(frozen=True)
class ReplayBatch:
    game_id: str
    contexts: tuple[ReplayContext, ...]
    records: tuple[ReplayRecord, ...]
    observations: tuple[Mapping, ...]
    identity: Mapping
    v: int = REPLAY_SCHEMA_VERSION

    def __post_init__(self):
        validate_version(self.v)
        object.__setattr__(self, 'contexts', tuple(self.contexts))
        object.__setattr__(self, 'records', tuple(self.records))
        object.__setattr__(self, 'observations', tuple(frozen_json(value) for value in self.observations))
        object.__setattr__(self, 'identity', frozen_json(self.identity))
        contexts = {context.log_seq: context for context in self.contexts}
        if len(contexts) != len(self.contexts):
            raise ValueError('Replay contexts require unique log sequences')
        observations = {event['seq']: event for event in self.observations}
        if len(observations) != len(self.observations) or any(event['kind'] == 'replay_cache' for event in self.observations):
            raise ValueError('Replay observations require unique non-cache sequences')
        for context in self.contexts:
            event = observations.get(context.log_seq)
            if (context.game_id != self.game_id or context.engine_identity != self.identity
                or context.data_snapshot_id != self.identity['data_snapshot_id']
                or event is None or event['kind'] != 'snapshot'
                or context.snapshot != event['payload'] or context.timestamp != event['timestamp']):
                raise ValueError('Replay context does not match its historical observation')
            if context.evaluation_overlay is not None:
                projection = self._project(context)
                if frozen_json(projection.to_dict(through_seq=context.prefix_through_seq)) != context.evaluation_overlay:
                    raise ValueError('Replay control overlay does not match its causal prefix')
        for record in self.records:
            context = contexts.get(record.log_seq)
            if (context is None or record.game_id != self.game_id or record.seed != context.seed
                or record.data_snapshot_id != context.data_snapshot_id
                or record.engine_identity != context.engine_identity):
                raise ValueError('Replay record does not match its historical context')

    def to_dict(self):
        return json_value(self)

    def history_for(self, context):
        if context not in self.contexts:
            raise ValueError('Context does not belong to this replay batch')
        return history_prefix(self.observations, through_seq=context.prefix_through_seq,
            captured_at=context.snapshot['captured_at'], controls=self._controls())

    def snapshot_for(self, context):
        """Return the causal evaluation view while retaining the raw context."""
        if context not in self.contexts:
            raise ValueError('Context does not belong to this replay batch')
        return self._project(context).snapshot

    def _controls(self):
        # Derived from the frozen observations; not a field, so never serialized or compared.
        from .controls import SessionControlLog

        if '_control_log' not in self.__dict__:
            object.__setattr__(self, '_control_log', SessionControlLog(self.observations))
        return self.__dict__['_control_log']

    def _project(self, context):
        from tft_engine import GameSnapshot

        # Validation proved this payload is the logged snapshot at this sequence.
        controls = self._controls()
        if context.prefix_through_seq == context.log_seq-1:
            return controls.frame({'seq': context.log_seq, 'payload': context.snapshot})
        return controls.project(GameSnapshot.from_dict(json_value(context.snapshot)),
            through_seq=context.prefix_through_seq)

    @classmethod
    def from_dict(cls, value):
        value = dict(value)
        value['contexts'] = tuple(ReplayContext.from_dict(row) for row in value['contexts'])
        value['records'] = tuple(ReplayRecord.from_dict(row) for row in value['records'])
        return cls(**value)
