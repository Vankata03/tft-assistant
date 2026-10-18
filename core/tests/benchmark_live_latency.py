"""Time the actual Live advisor with decoded synthetic history, without a game.

Run from core with the intended workspace source directories on PYTHONPATH.
This measures CPU evaluation and evidence construction, not capture-to-screen.
"""
import argparse
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import platform
import runpy
from statistics import median
from time import perf_counter

import tft_engine
import tft_live
from tft_engine import GameHistory, GameSnapshot
from tft_live.advisor import LiveAdvisor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', type=int, default=12)
    parser.add_argument('--repeats', type=int, default=7)
    args = parser.parse_args()
    if args.history < 0 or args.repeats < 1:
        parser.error('History must be nonnegative and repeats must be positive')
    fixture = runpy.run_path(str(Path(__file__).parents[1] / 'packages/engine/tests/test_planning.py'))
    data, initial = fixture['patch'](), fixture['snapshot']()
    states = tuple(replace(initial, snapshot_id=f'frame-{index}',
        captured_at=initial.captured_at + timedelta(seconds=index),
        fields={name: replace(value, read_at=value.read_at + timedelta(seconds=index))
                for name, value in initial.fields.items()}) for index in range(args.history + 1))
    advisor = LiveAdvisor()
    if args.history:
        advisor.evaluate(states[-2], GameHistory(states[:-2]), data, mode='live')
    elapsed = []
    for _ in range(args.repeats):
        history = GameHistory(tuple(GameSnapshot.from_dict(row.to_dict()) for row in states[:-1]))
        start = perf_counter()
        delivery = advisor.evaluate(states[-1], history, data, mode='live')
        elapsed.append(perf_counter() - start)
    evidence = delivery.evidence.resolve()
    evidence.pop('simulation_diagnostics')
    encoded = json.dumps(evidence, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    print(json.dumps({'qualification': 'Synthetic macOS CPU evaluation and evidence only; no capture/UI/game accuracy qualification',
        'platform': platform.platform(), 'python': platform.python_version(),
        'sources': {module.__name__: module.__file__ for module in (tft_engine, tft_live)},
        'historical_snapshots': args.history, 'evaluation_seconds': elapsed,
        'median_seconds': median(elapsed), 'decision_evidence_sha256': sha256(encoded).hexdigest(),
        'expanded_evidence_bytes': len(encoded), 'evidence_records': len(delivery.evidence.objects)}))


if __name__ == '__main__':
    main()
