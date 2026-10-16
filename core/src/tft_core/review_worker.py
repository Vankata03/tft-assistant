"""One bounded background review job; the application supervises this process."""
import argparse
import json
import os
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(prog='tft-review-worker')
    parser.add_argument('game_id')
    parser.add_argument('--log-root',type=Path,required=True)
    parser.add_argument('--config-root',type=Path,required=True)
    parser.add_argument('--snapshots',type=Path,required=True)
    parser.add_argument('--repository',type=Path,required=True)
    parser.add_argument('--expected-job-id')
    parser.add_argument('--collect-outcome', action='store_true')
    args = parser.parse_args(argv)
    receipt = {'status':'review_unavailable','game_id':args.game_id,'job_id':None,
        'engine_version':None,'data_snapshot_id':None,'report_id':None,
        'evidence_id':None,'locked':None,'reason':None}
    try:
        # Do this in the child, before heavy imports. preexec_fn is unsafe in
        # the multithreaded application; Windows priority is parent-owned.
        priority = {'policy':'parent_windows_below_normal'}
        if os.name != 'nt':
            try:
                priority = {'policy':'posix_nice','nice':os.nice(10)}
            except OSError:
                receipt['reason'] = 'background_priority_unavailable'
                print(json.dumps(receipt,allow_nan=False))
                return 2
        from tft_data import DataStore
        from tft_review import ReviewService
        from tft_core.storage import SessionStore

        sessions = SessionStore(args.log_root,args.config_root)
        if args.collect_outcome:
            from tft_core.outcomes import OutcomeCollector
            result = OutcomeCollector(sessions).collect(args.game_id)
            receipt.update(status='outcome_collected', job_id=args.expected_job_id,
                           outcome_state=result['state'], priority=priority)
            print(json.dumps(receipt, allow_nan=False))
            return 0
        service = ReviewService(sessions,
            DataStore(args.snapshots),repository=args.repository)
        job = service.job_identity(args.game_id)
        receipt.update({name:job[name] for name in ('job_id','engine_version','data_snapshot_id')})
        receipt['priority'] = priority
        if args.expected_job_id is not None and args.expected_job_id != job['job_id']:
            receipt['reason'] = 'job_identity_changed'
            print(json.dumps(receipt,allow_nan=False))
            return 2
        summary = service.produce(args.game_id,expected_job_id=job['job_id'])
        if service.job_identity(args.game_id) != job:
            raise ValueError('Review job identity changed after publication')
        receipt.update(status='review_ready',locked=summary['locked'],
            report_id=summary['report_id'],evidence_id=summary['evidence_id'])
        print(json.dumps(receipt,allow_nan=False))
        return 0
    except (OSError,ValueError,KeyError,RuntimeError) as error:
        # stdout is a receipt, never private review content or a filesystem path.
        receipt['reason'] = ('job_identity_changed' if 'identity changed' in str(error)
            else 'review_inputs_or_evaluation_unavailable')
        print(json.dumps(receipt,allow_nan=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
