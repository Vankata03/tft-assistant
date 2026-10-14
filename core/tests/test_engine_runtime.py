"""Latest Engine delivery is bounded at the approved advice boundary."""

import asyncio
import threading
from datetime import UTC, datetime

from tft_engine import GameHistory, GameSnapshot, evaluate


def test_slow_engine_keeps_only_latest_pending_snapshot():
    from tft_core.engine_runtime import LatestEngineWorker

    async def scenario():
        entered, release = threading.Event(), threading.Event()
        delivered = []
        evaluated = []

        def engine(snapshot):
            result = evaluate(snapshot, GameHistory(), None, 'silent')
            evaluated.append(snapshot.snapshot_id)
            if snapshot.snapshot_id == 'first':
                entered.set()
                release.wait(2)
            return result

        worker = LatestEngineWorker(engine, lambda snapshot, result, error: delivered.append((snapshot.snapshot_id, error)))
        worker.start()
        snapshot = lambda name: GameSnapshot('123', '2-1', datetime.now(UTC), snapshot_id=name)
        worker.submit(snapshot('first'))
        while not entered.is_set():
            await asyncio.sleep(.005)
        for index in range(100):
            worker.submit(snapshot(str(index)))
        release.set()
        for _ in range(200):
            if delivered and delivered[-1][0] == '99':
                break
            await asyncio.sleep(.005)
        assert evaluated == ['first', '99']
        assert delivered[-1] == ('99', None)
        assert len(delivered) <= 2
        assert await worker.shutdown(timeout=.2)

    asyncio.run(scenario())


def test_shutdown_invalidates_slow_engine_result_without_waiting_for_python_exit():
    from tft_core.engine_runtime import LatestEngineWorker

    async def scenario():
        entered, release = threading.Event(), threading.Event()
        delivered = []

        def engine(snapshot):
            result = evaluate(snapshot, GameHistory(), None, 'silent')
            entered.set()
            release.wait(2)
            return result

        worker = LatestEngineWorker(engine, lambda *args: delivered.append(args))
        worker.start()
        worker.submit(GameSnapshot('123', '2-1', datetime.now(UTC)))
        while not entered.is_set():
            await asyncio.sleep(.005)
        assert not await worker.shutdown(timeout=.02)
        assert not worker.submit(GameSnapshot('123', '2-2', datetime.now(UTC)))
        release.set()
        await asyncio.sleep(.03)
        assert delivered == []
        assert await worker.shutdown(timeout=.1)

    asyncio.run(scenario())


def test_persistent_ui_pin_keeps_its_real_timestamp_beyond_hud_expiry():
    import runpy
    from dataclasses import replace
    from datetime import timedelta
    from pathlib import Path
    from tft_engine import FieldValue

    examples = runpy.run_path(str(Path(__file__).parents[1] / 'packages/engine/tests/test_planning.py'))
    state = examples['snapshot']('3-2', comp_lock='A')
    pin = FieldValue({'id': 'roll:pin', 'levels': {}, 'rolls': {'3-2': 10}},
                     state.captured_at - timedelta(minutes=5), 'ui_pin')
    state = replace(state, fields={**state.fields, 'pinned_line': pin})
    result = evaluate(state, GameHistory(), examples['patch'](), 'live')
    econ = next(row for row in result.advice if row.decision == 'econ')
    assert econ.payload['pinned'] is True
    assert econ.payload['line_id'] == 'roll:pin'
    assert state.fields['pinned_line'].read_at == state.captured_at - timedelta(minutes=5)


def test_future_pin_and_expired_hud_pin_do_not_override_current_engine_plan():
    import runpy
    from dataclasses import replace
    from datetime import timedelta
    from pathlib import Path
    from tft_engine import FieldValue

    examples = runpy.run_path(str(Path(__file__).parents[1] / 'packages/engine/tests/test_planning.py'))
    base = examples['snapshot']('3-2', comp_lock='A')
    for source, offset, value in [
        ('ui_pin', timedelta(seconds=1), {'id': 'roll:pin', 'levels': {}, 'rolls': {'3-2': 10}}),
        ('ocr', timedelta(minutes=-5), {'id': 'roll:pin', 'levels': {}, 'rolls': {'3-2': 10}}),
        ('ui_pin', timedelta(seconds=-1), None),
    ]:
        pin = FieldValue(value, base.captured_at + offset, source)
        state = replace(base, fields={**base.fields, 'pinned_line': pin})
        result = evaluate(state, GameHistory(), examples['patch'](), 'live')
        econ = next(row for row in result.advice if row.decision == 'econ')
        assert econ.payload['pinned'] is False
