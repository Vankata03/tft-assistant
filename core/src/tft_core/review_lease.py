"""Durable review-child ownership without trusting a bare PID.

A lease identifies the launched command, nonce and OS creation times. Restart may
signal only a matching child whose original core owner has demonstrably gone.
PID reuse, changed commands and inaccessible process metadata remain visible
blocked states. The OS adopter reaps orphaned children; a restarted core can
confirm disappearance but cannot recover their original wait status.
"""

import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import secrets

import psutil


def atomic_record(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        temporary.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def process_identity(process):
    return {'pid': process.pid, 'created_at': process.create_time(), 'command': process.cmdline()}


class JobMutex:
    """One actual review evaluator per durable job, held by the child process."""

    def __init__(self, root, job_id):
        if not re.fullmatch(r'(?:schedule-)?[0-9a-f]{64}', job_id):
            raise ValueError('Job mutex requires a validated identity')
        self.path = Path(root) / 'locks' / f'{job_id}.lock'
        self.stream = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a+b')
        if os.name == 'nt':
            import msvcrt
            if self.path.stat().st_size == 0:
                self.stream.write(b'0')
                self.stream.flush()
            self.stream.seek(0)
            try:
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.stream.close()
                self.stream = None
                return False
        else:
            import fcntl
            try:
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.stream.close()
                self.stream = None
                return False
        return True

    def close(self):
        if self.stream:
            if os.name == 'nt':
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close()
            self.stream = None


class OwnedReviewChildren:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.owner_nonce = secrets.token_hex(16)
        self.owner = process_identity(psutil.Process())
        self._owner_path = self.root / 'owners' / f'{self.owner_nonce}.json'

    def register_owner(self):
        atomic_record(self._owner_path, {'schema_version': 1, 'kind': 'tft-review-owner',
            'owner_nonce': self.owner_nonce, **self.owner, 'state': 'running'})

    def close_owner(self):
        atomic_record(self._owner_path, {'schema_version': 1, 'kind': 'tft-review-owner',
            'owner_nonce': self.owner_nonce, **self.owner, 'state': 'closed'})

    def record_path(self, job_id):
        if not re.fullmatch('[0-9a-f]{64}', job_id):
            raise ValueError('Review child requires a qualified job identity')
        return self.root / 'children' / f'{job_id}.json'

    def command(self, worker, game_id, job_id):
        nonce = secrets.token_hex(16)
        return [worker[0], '-m', 'tft_core.review_child',
            '--lease-root', str(self.root), '--job-id', job_id,
            '--game-id', game_id, '--launch-nonce', nonce,
            '--owner-nonce', self.owner_nonce, '--owner-pid', str(self.owner['pid']),
            '--owner-created', str(self.owner['created_at']), '--', *worker[1:]]

    def reaped(self, job_id, command, exit_code):
        path = self.record_path(job_id)
        if not path.exists():
            return
        record = json.loads(path.read_text())
        if record.get('owner_nonce') != self.owner_nonce or record.get('command') != command:
            raise ValueError('Reaped child lease does not match this core launch')
        record.update(state='reaped', wait_status=exit_code, reaped_at=datetime.now(UTC).isoformat())
        atomic_record(path, record)
        atomic_record(self.root / 'history' / f"{job_id}.{record['launch_nonce']}.json", record)

    def _child(self, record):
        try:
            if (record.get('schema_version') != 1 or record.get('kind') != 'tft-review-child'
                or not re.fullmatch('[0-9a-f]{64}', record.get('job_id', ''))
                or not re.fullmatch('[0-9a-f]{32}', record.get('launch_nonce', ''))
                or not re.fullmatch('[0-9a-f]{32}', record.get('owner_nonce', ''))):
                return None, 'child lease identity is malformed'
            process = psutil.Process(record['pid'])
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return None, None
            if process.create_time() != record['created_at']:
                return None, 'child PID identity changed; original process is unavailable'
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return None, None
            command = process.cmdline()
            expected = record['command']
            if command != expected or command[1:3] != ['-m', 'tft_core.review_child']:
                return None, 'child command identity does not match the owned wrapper'
            checks = {'--lease-root': str(self.root), '--job-id': record['job_id'],
                '--game-id': record['game_id'], '--launch-nonce': record['launch_nonce'],
                '--owner-nonce': record['owner_nonce'], '--owner-pid': str(record['owner']['pid']),
                '--owner-created': str(record['owner']['created_at'])}
            for key, value in checks.items():
                if command.count(key) != 1 or command[command.index(key)+1] != value:
                    return None, f'child launch identity does not match {key}'
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return None, None
            return process, None
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return None, None
        except (psutil.AccessDenied, KeyError, TypeError, ValueError, IndexError) as error:
            return None, f'child identity cannot be verified: {type(error).__name__}'

    def _owner_alive(self, record):
        try:
            path = self.root / 'owners' / f'{record["owner_nonce"]}.json'
            stored = json.loads(path.read_text())
            owner = record['owner']
            if any(stored.get(name) != owner[name] for name in ('pid', 'created_at', 'command')):
                return None
            if stored.get('owner_nonce') != record['owner_nonce'] or stored.get('kind') != 'tft-review-owner':
                return None
            process = psutil.Process(owner['pid'])
            if process.create_time() != owner['created_at']:
                return False
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return False
            if process.cmdline() != owner['command']:
                return None
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return False
        except (psutil.AccessDenied, OSError, ValueError, KeyError, TypeError):
            return None

    async def _gone(self, record, seconds):
        deadline = asyncio.get_running_loop().time() + seconds
        while asyncio.get_running_loop().time() < deadline:
            if not psutil.pid_exists(record['pid']):
                return True
            process, reason = self._child(record)
            if process is None:
                record['termination_identity_error'] = reason
                if reason is None:
                    return True
                # macOS can briefly deny metadata while a signalled process exits.
                # Wait for disappearance; never use that denial to authorize kill.
                if 'AccessDenied' not in reason:
                    return False
            else:
                record['termination_last_status'] = process.status()
            await asyncio.sleep(.005)
        return False

    async def reconcile(self):
        results = []
        for path in (self.root / 'children').glob('*.json'):
            try:
                record = json.loads(path.read_text())
                if record.get('state') not in {'running', 'finished', 'terminating', 'blocked'}:
                    continue
                if path.stem != record.get('job_id'):
                    raise ValueError('child lease filename identity mismatch')
                process, reason = self._child(record)
                if reason:
                    state = 'blocked'
                elif process is None:
                    state, reason = 'gone', 'Child no longer exists; original wait status is unavailable after restart'
                else:
                    owner_alive = self._owner_alive(record)
                    if owner_alive is not False:
                        state = 'blocked'
                        reason = 'Another live core owns this review child' if owner_alive else 'Original owner identity is unavailable'
                    else:
                        # psutil checks creation time again before sending a signal.
                        process.terminate()
                        gone = await self._gone(record, .15)
                        if not gone:
                            process, identity_error = self._child(record)
                            if process is not None and identity_error is None:
                                process.kill()
                                gone = await self._gone(record, .15)
                        state = 'interrupted' if gone else 'blocked'
                        reason = ('Original core died; owned child termination confirmed; OS adopter reaps it'
                            if gone else 'Owned child termination could not be confirmed')
                record.update(state=state, reason=reason, reconciled_at=datetime.now(UTC).isoformat())
                atomic_record(path, record)
                atomic_record(self.root / "history" / f"{record['job_id']}.{record['launch_nonce']}.json", record)
                results.append(record)
            except (OSError, ValueError, KeyError, TypeError, psutil.Error) as error:
                results.append({'job_id': path.stem, 'state': 'blocked',
                    'reason': f'Child lease identity could not be reconciled: {type(error).__name__}'})
        return results
