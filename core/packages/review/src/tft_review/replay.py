"""Causal historical log evaluation using the shared review Engine."""
from pathlib import Path
from datetime import datetime

from tft_engine import GameSnapshot, TraitSighting, evaluate, snapshot_seed
from tft_engine.planning import PlanningHistory

from .contracts import ReplayBatch, ReplayContext, ReplayRecord, frozen_json, history_prefix, json_value
from .identity import replay_identity
from .segmentation import semantic_fingerprint
from .controls import SessionControlLog


def aware_timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Replay timestamps require a timezone')
    return parsed


def validate_events(events, game_id):
    """Fail visibly on committed malformed evidence; torn lines are storage-owned."""
    try:
        if not events or events[0]['kind'] != 'game_start':
            raise ValueError('missing game_start')
        metadata = events[0]['payload']
        if str(metadata['game_id']) != str(game_id):
            raise ValueError('game_start belongs to another game')
        for index, event in enumerate(events):
            frozen_json(event)
            if type(event['v']) is not int or event['v'] != 1 or type(event['seq']) is not int or event['seq'] != index:
                raise ValueError('invalid event version or sequence')
            if not isinstance(event['kind'], str) or not isinstance(event['payload'], dict):
                raise ValueError('invalid kind or payload')
            at = aware_timestamp(event['timestamp'])
            payload = event['payload']
            if event['kind'] == 'snapshot':
                snapshot = GameSnapshot.from_dict(payload)
                if snapshot.game_id != str(game_id) or not snapshot.snapshot_id or not snapshot.round_id:
                    raise ValueError('invalid snapshot identity')
                if snapshot.captured_at > at:
                    raise ValueError('snapshot capture occurs after its logged availability')
                if payload.get('data_snapshot_id', metadata['data_snapshot_id']) != metadata['data_snapshot_id']:
                    raise ValueError('snapshot changed the historical data pin')
                if any(field.read_at > snapshot.captured_at for field in snapshot.fields.values()):
                    raise ValueError('field read occurs after its capture')
            elif event['kind'] == 'sighting':
                TraitSighting.from_dict(payload | {'read_at': event['timestamp']})
            elif event['kind'] == 'capture_gap':
                end = aware_timestamp(payload['end'])
                if payload['start'] is None and payload.get('reason') != 'incomplete_first_event':
                    raise ValueError('unknown gap start without opening recovery evidence')
                if payload['start'] is not None and aware_timestamp(payload['start']) > end:
                    raise ValueError('reversed capture gap')
            elif event['kind'] == 'game_start' and index:
                raise ValueError('duplicate game_start')
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValueError(f'Invalid replay evidence: {error}') from error
    return events


class ReplayProducer:
    def __init__(self, sessions, data_store, *, repository, hooks=None, hook_version='default', decision_segmentation='every_snapshot'):
        self.sessions, self.data_store = sessions, data_store
        self.repository = Path(repository)
        self.hooks = None if hooks is None else tuple(hooks)
        if decision_segmentation not in {'every_snapshot', 'semantic'}:
            raise ValueError('Unknown replay decision segmentation policy')
        self.decision_segmentation = decision_segmentation
        self.hook_version = hook_version if decision_segmentation == 'every_snapshot' else hook_version + ':semantic-v1'

    def produce(self, game_id):
        events = validate_events(self.sessions.read_events(game_id), game_id)
        events = [row for row in events if row['kind'] != 'replay_cache']
        metadata = events[0]['payload']
        data = self.data_store.get(metadata['data_snapshot_id'])
        identity = replay_identity(self.repository, events, data, self.hooks, self.hook_version)
        cacheable = not identity['dirty'] and identity['finished'] and identity['hooks_cacheable']
        key = dict(engine_version=identity['commit'], tunables_hash=identity['tunables_hash'],
            data_snapshot_id=data.snapshot_id, cache_identity=identity)
        if cacheable:
            cached = self.sessions.read_replay_cache(game_id, **key)
            if cached is not None:
                batch = ReplayBatch.from_dict(cached[0])
                if batch.identity != frozen_json(identity):
                    raise ValueError('Replay cache identity mismatch')
                self._check_unchanged(game_id, data, identity)
                return batch
        contexts, records = [], []
        previous_fingerprint, evaluation_log_seq = None, None
        controls = SessionControlLog(events)
        history_fold = PlanningHistory() if identity['hooks_cacheable'] else None
        gap_intervals = [(row,
            aware_timestamp(row['payload']['start']) if row['payload']['start'] is not None else None,
            aware_timestamp(row['payload']['end'])) for row in events if row['kind'] == 'capture_gap']
        for event in events:
            if event['kind'] != 'snapshot':
                continue
            projection = controls.frame(event)
            snapshot = projection.snapshot
            seed = snapshot_seed(snapshot, data)
            # Later crash annotations may invalidate capture evidence. They never
            # become causal Engine information or reset an earlier history prefix.
            gaps = [row for row, start, end in gap_intervals
                if (start is None or start <= snapshot.captured_at) and snapshot.captured_at < end]
            in_gap = bool(gaps)
            history = history_prefix(events, through_seq=event['seq']-1,
                captured_at=event['payload']['captured_at'], controls=controls)
            fingerprint = (semantic_fingerprint(snapshot, data, events, event['seq']-1, hooks=self.hooks)
                if self.decision_segmentation == 'semantic' else None)
            duplicate = (not in_gap and self.decision_segmentation == 'semantic'
                and fingerprint == previous_fingerprint)
            result = None if in_gap or duplicate else evaluate(snapshot, history, data,
                'review', hooks=self.hooks, seed=seed, history_fold=history_fold)
            context = ReplayContext(str(game_id), event['seq'], event['timestamp'], event['payload'],
                metadata, data.snapshot_id, identity, seed, event['seq']-1, json_value(result),
                unavailable=(('capture_gap',) if in_gap else ('semantic_duplicate',) if duplicate else ()) + tuple(
                    f'stale_field:{name}' for name in event['payload'].get('stale_fields', ())),
                validity_annotations=((frozen_json({'kind': 'semantic_duplicate',
                    'evaluation_log_seq': evaluation_log_seq, 'fingerprint': fingerprint}),) if duplicate else ()) + tuple({'kind': 'capture_gap', 'log_seq': row['seq'],
                    'timestamp': row['timestamp'], 'payload': row['payload'],
                    'retrospective': row['seq'] >= event['seq'] or aware_timestamp(row['timestamp']) > snapshot.captured_at}
                    for row in gaps),
                evaluation_overlay=projection.to_dict(through_seq=event['seq']-1))
            contexts.append(context)
            if not duplicate:
                previous_fingerprint = None if in_gap else fingerprint
                evaluation_log_seq = event['seq']
            for index, advice in enumerate(result.advice if result else ()):
                selected = next((option for option in advice.options if option.option_id == advice.option_id), None)
                records.append(ReplayRecord(str(game_id), event['seq'],
                    advice.decision_id or f'{game_id}:{event["seq"]}:{advice.decision}:{index}',
                    advice.decision, advice.to_dict(), tuple(option.to_dict() for option in advice.options),
                    seed, data.snapshot_id, identity, unavailable={'observed_choice': 'not_reconstructed',
                        'cost': 'player_choice_unavailable', 'paired_uncertainty': 'not_valued',
                        'shown': 'display_attribution_unavailable',
                        **({'expected_placement': 'domain_does_not_value_placement'}
                            if selected is None or selected.expected_placement is None else {})},
                    expected_placement=selected.expected_placement if selected else None))
        batch = ReplayBatch(str(game_id), tuple(contexts), tuple(records), tuple(events), identity)
        self._check_unchanged(game_id, data, identity)
        if cacheable:
            self.sessions.write_replay_cache(game_id, [batch.to_dict()], **key)
        return batch

    def _check_unchanged(self, game_id, data, identity):
        # Verify the immutable pin still exists and has its checked content hash.
        self.data_store.get(data.snapshot_id)
        events = validate_events(self.sessions.read_events(game_id), game_id)
        events = [row for row in events if row['kind'] != 'replay_cache']
        current = replay_identity(self.repository, events, data, self.hooks, self.hook_version)
        if current != identity:
            raise ValueError('Replay inputs changed during evaluation or cache access; retry')
