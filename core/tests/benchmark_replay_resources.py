"""Measure a synthetic default-Engine replay; this does not qualify live games.

Run from core with branch sources on PYTHONPATH:
    python -m tests.benchmark_replay_resources --decisions 300
"""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import platform
import sys
import tempfile
import time

import psutil
import tft_data
import tft_engine
import tft_review

from tests.test_replay_contracts import NOW, ROOT, logged_game, log_snapshot
from tft_review import ReplayProducer


def peak_rss():
    try:
        import resource
    except ImportError:
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == 'darwin' else value*1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decisions', type=int, default=300)
    arguments = parser.parse_args()
    if arguments.decisions < 1:
        parser.error('--decisions must be positive')
    with tempfile.TemporaryDirectory(prefix='tft-replay-benchmark-') as temporary:
        sessions, store, data, _ = logged_game(Path(temporary), finish=False)
        for index in range(1, arguments.decisions):
            at = NOW+timedelta(seconds=index)
            sessions.append_event('snapshot', log_snapshot(data, at=at,
                snapshot_id=f'decision-{index}', gold=18+index%7), timestamp=at.isoformat())
        sessions.end_game(timestamp=(NOW+timedelta(seconds=arguments.decisions+1)).isoformat())
        start = time.perf_counter()
        batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
        elapsed = time.perf_counter()-start
        producer_peak = peak_rss()
        producer_rss = psutil.Process().memory_info().rss
        start = time.perf_counter()
        document = batch.to_dict()
        serialized_bytes = sum(len(chunk.encode()) for chunk in
            json.JSONEncoder(separators=(',', ':')).iterencode(document))
        print(json.dumps({'platform': platform.platform(), 'python': platform.python_version(),
            'sources': {module.__name__: module.__file__ for module in (tft_data, tft_engine, tft_review)},
            'identity': {key: batch.identity[key] for key in ('commit', 'dirty', 'dirty_hash',
                'runtime_source_hash', 'runtime_mismatches')},
            'decisions': len(batch.contexts), 'records': len(batch.records), 'producer_seconds': elapsed,
            'producer_peak_rss_bytes': producer_peak, 'producer_retained_rss_bytes': producer_rss,
            'serialized_bytes': serialized_bytes, 'serialization_seconds': time.perf_counter()-start,
            'serialization_peak_rss_bytes': peak_rss()}, indent=2))


if __name__ == '__main__':
    main()
