"""Background review runs through the real process, stores and Engine."""
import json
import os
import subprocess
import sys

from tests.test_replay_contracts import ROOT, logged_game


def test_review_worker_publishes_private_evidence_but_only_a_locked_receipt(tmp_path):
    from tft_review import ReviewService

    sessions,store,data,_ = logged_game(tmp_path)
    job = ReviewService(sessions,store,repository=ROOT).job_identity('901')
    command = [sys.executable,'-m','tft_core.review_worker','901',
        '--log-root',str(sessions.root),'--config-root',str(sessions.config_root),
        '--snapshots',str(store.root),'--repository',str(ROOT),'--expected-job-id',job['job_id']]
    result = subprocess.run(command,capture_output=True,text=True,timeout=20)
    assert result.returncode == 0,result.stderr
    receipt = json.loads(result.stdout)
    assert receipt['status'] == 'review_ready'
    assert receipt['job_id'] == job['job_id']
    assert receipt['data_snapshot_id'] == data.snapshot_id
    assert receipt['locked'] is True
    assert receipt['report_id'] is receipt['evidence_id'] is None
    assert 'top5' not in receipt and 'evidence_graph' not in receipt
    if os.name != 'nt':
        assert receipt['priority']['nice'] >= 10
    rejected = subprocess.run(command[:-1]+['0'*64],capture_output=True,text=True,timeout=20)
    assert rejected.returncode == 2
    unavailable = json.loads(rejected.stdout)
    assert unavailable['status'] == 'review_unavailable'
    assert unavailable['reason'] == 'job_identity_changed'


def test_installed_worker_cli_keeps_original_pin_and_exposes_unlocked_report_identity(tmp_path):
    from pathlib import Path
    from tft_review import ReviewService

    sessions,store,data,_ = logged_game(tmp_path,mode='baseline')
    job = ReviewService(sessions,store,repository=ROOT).job_identity('901')
    entry = Path(sys.executable).parent/('tft-review-worker.exe' if os.name == 'nt' else 'tft-review-worker')
    command = [str(entry),'901','--log-root',str(sessions.root),
        '--config-root',str(sessions.config_root),'--snapshots',str(store.root),
        '--repository',str(ROOT),'--expected-job-id',job['job_id']]
    result = subprocess.run(command,capture_output=True,text=True,timeout=20)
    assert result.returncode == 0,result.stderr
    receipt = json.loads(result.stdout)
    assert receipt['locked'] is False
    assert receipt['report_id'] == receipt['evidence_id']
    assert receipt['report_id']
    saved = sessions.read_review('901')
    assert saved['data_snapshot_id'] == data.snapshot_id
    assert saved['engine_version'] == job['engine_version']
    # A missing historical pin must remain unavailable, without fetching fresh data.
    absent = tmp_path/'missing-snapshots'
    command[command.index('--snapshots')+1] = str(absent)
    result = subprocess.run(command,capture_output=True,text=True,timeout=20)
    assert result.returncode == 2
    assert json.loads(result.stdout)['reason'] == 'review_inputs_or_evaluation_unavailable'
    assert not absent.exists()
