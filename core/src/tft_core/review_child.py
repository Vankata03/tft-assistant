"""Own one actual review worker through a durable, process-bound lease."""

import argparse
from contextlib import redirect_stdout
from datetime import UTC, datetime
import io
import json
import os
import re
from pathlib import Path

import psutil

from tft_core.review_lease import JobMutex, atomic_record, process_identity


class ReceiptBuffer(io.StringIO):
    def write(self, value):
        if self.tell() + len(value) > 65536:
            raise ValueError('Review receipt exceeded its byte budget')
        return super().write(value)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='tft-review-child')
    parser.add_argument('--lease-root', type=Path, required=True)
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--game-id', required=True)
    parser.add_argument('--launch-nonce', required=True)
    parser.add_argument('--owner-nonce', required=True)
    parser.add_argument('--owner-pid', type=int, required=True)
    parser.add_argument('--owner-created', type=float, required=True)
    parser.add_argument('worker', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    unavailable = {'status': 'review_unavailable', 'game_id': args.game_id,
        'job_id': args.job_id, 'reason': 'review_child_ownership_unavailable'}
    if 'TFT_CORE_TOKEN' in os.environ:
        print(json.dumps(unavailable | {'reason': 'review_child_auth_environment_not_isolated'}))
        return 2
    if (not re.fullmatch('[0-9a-f]{64}', args.job_id)
        or not re.fullmatch('[0-9a-f]{32}', args.launch_nonce)
        or not re.fullmatch('[0-9a-f]{32}', args.owner_nonce)
        or not re.fullmatch('[1-9][0-9]*', args.game_id)):
        print(json.dumps(unavailable))
        return 2
    worker = args.worker[1:] if args.worker[:1] == ['--'] else args.worker
    if worker[:2] != ['-m', 'tft_core.review_worker']:
        print(json.dumps(unavailable))
        return 2
    root = args.lease_root.resolve()
    owner_path = root / 'owners' / f'{args.owner_nonce}.json'
    mutex = JobMutex(root, args.job_id)
    if not mutex.acquire():
        print(json.dumps(unavailable | {'reason': 'review_job_already_owned'}))
        return 2
    record, path = None, root / 'children' / f'{args.job_id}.json'
    try:
        owner = json.loads(owner_path.read_text())
        if (owner['owner_nonce'] != args.owner_nonce or owner['pid'] != args.owner_pid
            or owner['created_at'] != args.owner_created):
            raise ValueError('Review core owner identity changed')
        record = {'schema_version': 1, 'kind': 'tft-review-child',
            'game_id': args.game_id, 'job_id': args.job_id,
            'launch_nonce': args.launch_nonce, 'owner_nonce': args.owner_nonce,
            'owner': {name: owner[name] for name in ('pid', 'created_at', 'command')},
            **process_identity(psutil.Process()), 'state': 'running',
            'core_auth_present': False, 'started_at': datetime.now(UTC).isoformat()}
        atomic_record(path, record)
        from tft_core.review_worker import main as produce
        output = ReceiptBuffer()
        with redirect_stdout(output):
            exit_code = produce(worker[2:])
        receipt = json.loads(output.getvalue())
        if receipt.get('game_id') != args.game_id or receipt.get('job_id') != args.job_id:
            raise ValueError('Review child receipt identity changed')
        if receipt.get('status') not in {'review_ready', 'review_unavailable'}:
            raise ValueError('Review child has no completion receipt')
        record.update(state='finished', receipt=receipt, exit_code=exit_code,
                      finished_at=datetime.now(UTC).isoformat())
        atomic_record(path, record)
        print(json.dumps(receipt, allow_nan=False), flush=True)
        return exit_code
    except (OSError, ValueError, KeyError, RuntimeError):
        if record is not None:
            record.update(state='failed', reason='review_child_inputs_or_receipt_unavailable')
            atomic_record(path, record)
        print(json.dumps(unavailable), flush=True)
        return 2
    finally:
        mutex.close()


if __name__ == '__main__':
    raise SystemExit(main())
