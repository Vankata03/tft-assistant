"""A preview receipt cannot create a replay decision or follow-rate entry."""
from datetime import timedelta
from tests.test_replay_contracts import NOW, ROOT, logged_game, log_snapshot


def test_preview_receipts_do_not_change_semantic_decisions_or_follow_denominator(tmp_path):
    from tft_review import ReplayProducer, ReviewPolicy

    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    sessions.append_event('preview_shown', {'schema_version':1,'mode':'live','surface':'overlay',
        'delivery_revision':'sha256:'+'a'*64,'preview':{'line_id':'fixed','round_id':'4-1'}},
        timestamp=(NOW+timedelta(seconds=.25)).isoformat())
    sessions.append_event('snapshot',log_snapshot(data,at=NOW+timedelta(seconds=.5),snapshot_id='poll'),
        timestamp=(NOW+timedelta(seconds=.5)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=1)).isoformat())
    batch=ReplayProducer(sessions,store,repository=ROOT,decision_segmentation='semantic').produce('901')
    assert len(batch.contexts)==2
    assert sum(context.evaluation is not None for context in batch.contexts)==1
    assert batch.contexts[1].unavailable==('semantic_duplicate',)
    report=ReviewPolicy(min_cost=.05).build(batch)
    assert report.summary['follow_rate']=={'value':None,'reason':'no_shown_advice_with_known_choice','eligible':0,'followed':0}
