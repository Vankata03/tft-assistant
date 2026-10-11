"""Review-facing access checks, separate from raw capture and training storage."""
from .contracts import ReplayBatch


class ReviewAccess:
    def __init__(self, sessions):
        self.sessions = sessions

    def publish(self, batch: ReplayBatch):
        """Internal producer publication does not unlock detailed owner access."""
        self.sessions.write_review(batch.game_id,
            {'replay': batch.to_dict(), 'decision_ids': sorted({record.decision_id for record in batch.records})},
            engine_version=batch.identity['commit'], data_snapshot_id=batch.identity['data_snapshot_id'],
            expected_log_hash=batch.identity['log_hash'])

    def read(self, game_id):
        return self.sessions.read_review(game_id)

    def read_batch(self, game_id):
        stored = self.read(game_id)
        return None if stored is None else ReplayBatch.from_dict(stored['review']['replay'])

    def tag(self, game_id, decision_id, tag):
        self.sessions.set_review_tag(game_id, decision_id, tag)

    def read_media(self, game_id, name):
        self.read(game_id)  # Stored mode/run lock is authoritative even without a review yet.
        if not any(row['kind'] in {'keyframe', 'video'} and row['payload'].get('path') == name
            for row in self.sessions.read_events(game_id)):
            raise ValueError('Review requires a logged media reference')
        return self.sessions.read_media(game_id, name)
