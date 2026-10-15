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
    args = parser.parse_args(argv)
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
