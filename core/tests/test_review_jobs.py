"""Durable runtime jobs execute the actual historical review child process."""

import asyncio

from tests.test_replay_contracts import ROOT, logged_game


def test_completed_review_is_durable_deduplicated_and_keeps_silent_lock(tmp_path):
    from tft_core.review_jobs import ReviewJobs
    from tft_review import ReviewService

    async def scenario():
        sessions, store, data, _ = logged_game(tmp_path)
        service = ReviewService(sessions, store, repository=ROOT)
        jobs = ReviewJobs(sessions, store, service, ROOT)
        jobs.start()
        jobs.enqueue('901')
        jobs.enqueue('901')
        for _ in range(400):
            records = jobs.jobs()
            if records and records[0]['state'] in {'completed', 'failed', 'unavailable'}:
                break
            await asyncio.sleep(.01)
        assert len(records) == 1
        assert records[0]['state'] == 'completed', records
        assert records[0]['receipt']['locked'] is True
        assert records[0]['receipt']['report_id'] is None
        assert records[0]['data_snapshot_id'] == data.snapshot_id
        first = records[0]
        jobs.enqueue('901')
        await asyncio.sleep(.1)
        assert jobs.jobs() == [first]
        await jobs.shutdown()
        resumed = ReviewJobs(sessions, store, service, ROOT)
        resumed.start()
        resumed.enqueue('901')
        await asyncio.sleep(.1)
        assert resumed.jobs() == [first]
        await resumed.shutdown()

    asyncio.run(scenario())


def test_actual_review_child_timeout_is_durable_and_never_announced(tmp_path):
    from tft_core.review_jobs import ReviewJobs
    from tft_review import ReviewService

    async def scenario():
        sessions, store, data, _ = logged_game(tmp_path, mode='baseline')
        service = ReviewService(sessions, store, repository=ROOT)
        announced = []

        async def ready(game_id):
            announced.append(game_id)

        jobs = ReviewJobs(sessions, store, service, ROOT, ready=ready, hard_timeout=.0001)
        jobs.start()
        jobs.enqueue('901')
        for _ in range(400):
            records = jobs.jobs()
            if records and records[0]['state'] == 'failed':
                break
            await asyncio.sleep(.005)
        assert records[0]['state'] == 'failed'
        assert 'TimeoutError' in records[0]['reason']
        assert announced == []
        assert sessions.read_review('901') is None
        assert await jobs.shutdown()
        restored = ReviewJobs(sessions, store, service, ROOT)
        assert restored.jobs()[0]['state'] == 'failed'

    asyncio.run(scenario())


def test_late_review_child_completes_during_next_game_and_remains_available(tmp_path):
    from datetime import UTC, datetime
    from tft_core.review_jobs import ReviewJobs
    from tft_review import ReviewService

    async def scenario():
        sessions, store, _, _ = logged_game(tmp_path, mode='baseline', finish=False)
        sessions.end_game(timestamp=datetime.now(UTC).isoformat())
        service = ReviewService(sessions, store, repository=ROOT)
        announced = asyncio.Event()

        async def ready(game_id):
            assert game_id == '901'
            assert sessions.active_game_id == '902'
            announced.set()

        jobs = ReviewJobs(sessions, store, service, ROOT, ready=ready, latency_budget=.0001)
        jobs.start()
        try:
            jobs.enqueue('901')
            sessions.set_mode('baseline')
            sessions.start_game('902')
            await asyncio.wait_for(announced.wait(), 4)
            record, = jobs.jobs()
            assert record['state'] == 'completed'
            assert record['late'] is True
            assert record['latency_seconds'] > .0001
            assert record['receipt']['status'] == 'review_ready'
            assert service.summary('901')['report_id'] == record['receipt']['report_id']
        finally:
            assert await jobs.shutdown()

    asyncio.run(scenario())


def test_shutdown_after_stored_review_preserves_completion_and_prevents_revaluation(tmp_path):
    from tft_core.review_jobs import ReviewJobs
    from tft_review import ReviewService

    async def scenario():
        sessions, store, _, _ = logged_game(tmp_path)
        service = ReviewService(sessions, store, repository=ROOT)
        announcing = asyncio.Event()

        async def ready(game_id):
            announcing.set()
            await asyncio.Event().wait()

        jobs = ReviewJobs(sessions, store, service, ROOT, ready=ready)
        jobs.start()
        jobs.enqueue('901')
        try:
            await asyncio.wait_for(announcing.wait(), 4)
        finally:
            assert await jobs.shutdown()
        completed = jobs.jobs()
        assert len(completed) == 1
        assert completed[0]['state'] == 'completed'
        assert completed[0]['delivery_state'] == 'interrupted'
        assert completed[0]['receipt']['status'] == 'review_ready'
        resumed = ReviewJobs(sessions, store, service, ROOT)
        resumed.start()
        try:
            resumed.enqueue('901')
            await asyncio.sleep(.2)
        finally:
            assert await resumed.shutdown()
        assert resumed.jobs() == completed

    asyncio.run(scenario())
