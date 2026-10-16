"""Owner workflows for the evaluation harness, using the durable session seam."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from tft_data.models import DataError
from tft_data.riot import RiotClient
from tft_harness import qualify_baseline

from .storage import SessionStore


def _private_location(path):
    path = Path(path).resolve()
    if any((ancestor/'.git').exists() for ancestor in (path, *path.parents)):
        raise ValueError('Owner baseline and game logs must stay outside Git repositories')
    return path


def _cache_matches(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix='baseline-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump(value, output, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _offline(args):
    from tft_data import DataStore
    from tft_harness import EvaluationHarness
    from tft_harness.overlay import TunableOverlay
    from tft_harness.tunables_io import latest_committed_tunables, write_candidate, producer_identity, runtime_repository
    from tft_harness.markdown import write_markdown
    from tft_harness.fitting import fit
    from tft_harness.priors import fit_priors
    from tft_harness.margins import fit_margins

    try:
        if not 20 <= args.bootstrap_draws <= 10000:
            raise ValueError('Bootstrap draws must be between 20 and 10000')
        root, config = (_private_location(path) for path in SessionStore.default_locations())
        output = _private_location(args.output or root/'harness')
        snapshots = _private_location(args.snapshots or root/'snapshots')
        reference = latest_committed_tunables(args.repository, path=args.accepted)
        producer = producer_identity()
        sessions, store = SessionStore(root, config), DataStore(snapshots)
        accepted = TunableOverlay(store, {}, tagged_fields=reference.fields)
        harness = EvaluationHarness(sessions, accepted, repository=runtime_repository(),
            current_set=reference.set_number)
        fitted = priors = margins = None
        updates = {}
        if args.command == 'fit':
            if not 3 <= args.max_evaluations <= 256 or not 2 <= args.model_draws <= 128:
                raise ValueError('Use 3–256 evaluations and 2–128 model bootstrap draws')
            if sessions.run and args.priors:
                raise ValueError('Public priors cannot change during the Live run')
            if args.priors:
                if args.search or args.fixed:
                    raise ValueError('Public priors do not fit owner-game search parameters')
                if store.current is None or store.current.patch != reference.patch:
                    raise ValueError('Public-prior fitting requires a current immutable data snapshot matching accepted patch')
                evidence = _read_json(args.prior_evidence) if args.prior_evidence else None
                priors = fit_priors(accepted.get(store.current.snapshot_id), evidence=evidence)
                updates = priors.fields
            else:
                if args.prior_evidence:
                    raise ValueError('Public prior evidence requires --priors')
                search = _read_json(args.search) if args.search else {'fight_scale': {'low': .01, 'high': 20.0}}
                parameters = _search_parameters(search)
                fixed = _read_json(args.fixed) if args.fixed else {}
                fitted = fit(harness, parameters, metric=args.metric, bootstrap_seed=args.seed,
                    bootstrap_draws=args.bootstrap_draws, max_evaluations=args.max_evaluations, fixed=fixed)
                updates = dict(fitted.solver['fixed']) | dict(fitted.parameters)
                margins = fit_margins(harness, parameters, metric=args.metric, draws=args.model_draws,
                    seed=args.seed, max_evaluations=args.max_evaluations, fixed=fixed)
                updates.update(margins['fields'])
        report = harness.evaluate(candidate=updates, bootstrap_seed=args.seed,
            bootstrap_draws=args.bootstrap_draws)
        diff = dict(harness.advice_diff(updates, limit=0)) | {
            'reference': 'latest committed accepted tunables; immutable static and source pins; original log points and seeds'}
        try:
            checks = harness.hand_set_checks(limit=0)
        except (DataError, ValueError, KeyError, OSError):
            checks = {'widened_candidates': {'status': 'unavailable', 'reason': 'missing_or_invalid_replay_source'}}
        write_markdown(output, reference, report, advice_diff=diff, fit=fitted, priors=priors, margins=margins,
            checks=checks, producer=producer)
        if updates:
            runtime = producer
            sources = {name: 'public-statistics' for name in updates} if priors else None
            write_candidate(reference, updates, output, citation='Offline harness candidate; qualification and gates in private report',
                sources=sources, provenance=({'method': 'qualified public empirical Bayes and temporal holdout',
                    'cohorts': priors.diagnostics.get('public_cohorts', []), 'runtime_code': runtime} if priors else
                    {'method': fitted.solver['method'], 'metric': args.metric,
                     'family2_method': 'actual paired Engine tapes and training-game bootstrap refits',
                     'model_draws': args.model_draws, 'seed': args.seed, 'runtime_code': runtime}))
        print('Wrote private aggregate report'+(' and unaccepted candidate TOML.' if updates else '.'))
        if args.command == 'fit' and not updates:
            print('No qualified estimable priors; committed values carried unchanged.')
        return 0
    except (DataError, ValueError, TypeError, KeyError, OSError, RuntimeError):
        print('tft-harness: Offline evaluation failed; check committed tunables, private snapshots, qualified inputs and declared search bounds.')
        return 2


def _search_parameters(search):
    from tft_harness.fitting import ContinuousRange, SimplexRange
    def node(value):
        if isinstance(value, dict):
            if 'simplex' in value:
                if set(value) != {'simplex'} or not isinstance(value['simplex'], dict):
                    raise ValueError('Simplex search requires a simplex parameter object')
                return SimplexRange(**value['simplex'])
            if {'low', 'high'} <= value.keys():
                return ContinuousRange(**value)
            return {key: node(item) for key, item in value.items()}
        return value
    return {name: node(value) for name, value in search.items()}


def _read_json(path):
    if Path(path).stat().st_size > 4_000_000:
        raise ValueError('Offline input exceeds the bounded input size')
    with Path(path).open(encoding='utf-8') as source:
        value = json.load(source, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    if not isinstance(value, dict):
        raise ValueError('Offline input must be a JSON object')
    return value


def main(argv=None, *, riot_client=None):
    parser = argparse.ArgumentParser(prog='tft-harness')
    commands = parser.add_subparsers(dest='command', required=True)
    start = commands.add_parser('start-run', help='Refresh and freeze the latest 50 eligible no-coach ranked games')
    start.add_argument('--game-name', required=True, help='Owner Riot ID game name')
    start.add_argument('--tag-line', required=True, help='Owner Riot ID tag')
    start.add_argument('--set', type=int, required=True, help='Owner-declared current set number; no automatic set discovery')
    start.add_argument('--platform', default='eun1', help='Riot platform for rank and numeric match-ID joins (default: eun1)')
    start.add_argument('--region', default='europe', help='Riot account/match routing region (default: europe)')
    start.add_argument('--max-matches', type=int, default=200, help='Owner matches to search (50–1000; default: 200)')
    for command in ('eval', 'fit'):
        offline = commands.add_parser(command, help='Replay private logs against committed accepted tunables')
        offline.add_argument('--repository', type=Path, default=Path.cwd())
        offline.add_argument('--accepted', help='Tracked data/<patch>/tunables.toml; defaults to newest committed patch')
        offline.add_argument('--snapshots', type=Path, help='Private immutable snapshot store; defaults to logs/snapshots')
        offline.add_argument('--output', type=Path, help='Private output directory; defaults to logs/harness')
        offline.add_argument('--bootstrap-draws', type=int, default=2000)
        offline.add_argument('--seed', type=int, default=0)
        if command == 'fit':
            offline.add_argument('--priors', action='store_true')
            offline.add_argument('--prior-evidence', type=Path, help='Qualified public aggregate cohort JSON')
            offline.add_argument('--fixed', type=Path, help='JSON family-1 normalization constants')
            offline.add_argument('--search', type=Path, help='JSON mapping family-1 names to grids or {low,high,start} ranges')
            offline.add_argument('--metric', default='fight_log_loss')
            offline.add_argument('--max-evaluations', type=int, default=64)
            offline.add_argument('--model-draws', type=int, default=8, help='2–128 training-game bootstrap refits for margin model uncertainty')
    args = parser.parse_args(argv)
    if args.command != 'start-run':
        return _offline(args)
    try:
        if args.set < 1 or not 50 <= args.max_matches <= 1000:
            raise ValueError('Use a positive declared set and a match search limit between 50 and 1000')
        if not args.game_name.strip() or not args.tag_line.strip():
            raise ValueError('Owner Riot ID name and tag must be nonempty')
        root, config = (_private_location(path) for path in SessionStore.default_locations())
        sessions = SessionStore(root, config)
        if sessions.run:
            raise ValueError('Live-mode run already started')
        if not sessions.live_installed:
            raise ValueError('Live advisor is not installed; install the Live build before starting a run')
        if any(not game['finished'] for game in sessions.list_games()):
            raise ValueError('Cannot start a run while a logged game is unfinished; finish or reconcile capture first')
        # Construct the real boundary even for injection so routing is validated
        # before requesting owner data. The fixture never reads its key path.
        configured = RiotClient(key_path=config/'riot-api-key', region=args.region, platform=args.platform)
        client = riot_client or configured
        account = client.account(args.game_name, args.tag_line)
        rank = client.rank()
        matches = client.own_matches(set_number=args.set, max_matches=args.max_matches)
        refreshed_at = datetime.now(timezone.utc).isoformat()
        baseline = qualify_baseline(matches, owner_puuid=account['puuid'], set_number=args.set,
            rank=rank, logged_games=sessions.list_games(), refreshed_at=refreshed_at,
            platform=args.platform)
        _cache_matches(config/'baseline-matches.json', {
            'owner_puuid': account['puuid'], 'rank': rank, 'matches': matches,
            'set_number': args.set, 'platform': args.platform, 'refreshed_at': refreshed_at})
        run = sessions.start_run(baseline, set_id=str(args.set))
        frozen = run['baseline']
        print(f"Started Live-mode run for declared set {args.set} at {run['started_at']}; "
            f"froze {frozen['game_count']} games, average placement {frozen['average_placement']:.2f}, "
            f"rank {frozen['rank']['tier']} {frozen['rank']['rank']}.")
        print('Silent-game reviews are unlocked. This command does not qualify production fits, calibration or Windows live capture.')
        return 0
    except (DataError, ValueError) as error:
        print(f'tft-harness: {error}')
        return 2
    except (OSError, RuntimeError):
        print('tft-harness: Local storage or API unavailable; check connectivity, local key and writable private roots, then retry.')
        return 2
    except (KeyError, TypeError, AttributeError):
        print('tft-harness: Owner API response is invalid; no run was started.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
