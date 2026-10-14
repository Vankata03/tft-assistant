"""Repository patch workflow; unavailable external assets remain explicit."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .models import DataError
from .patches import bootstrap_patch, new_patch, prepare_new_set
from .store import DataStore


def main(argv=None, *, riot_client=None):
    parser = argparse.ArgumentParser(prog="tft-data")
    commands = parser.add_subparsers(dest="command", required=True)
    patch = commands.add_parser("new-patch")
    patch.add_argument("patch")
    patch.add_argument("--data-dir", default="../data")
    patch.add_argument("--from-patch", required=True)
    patch.add_argument(
        "--live-at",
        required=True,
        help="Owner-confirmed EUNE live time, with timezone offset",
    )
    patch.add_argument("--dragon-version")
    patch.add_argument("--cdragon-file")
    patch.add_argument("--ddragon-file")
    patch.add_argument(
        "--offline",
        action="store_true",
        help="Carry only; explicitly skip automatic Dragon refresh",
    )
    validate = commands.add_parser("validate")
    validate.add_argument("patch_dir")
    validate.add_argument(
        "--snapshots", default=str(Path.home() / ".config/tft-assistant/data-snapshots")
    )
    riot = commands.add_parser("riot-matches")
    riot.add_argument("--game-name", required=True)
    riot.add_argument("--tag-line", required=True)
    riot.add_argument("--set", type=int, required=True)
    riot.add_argument("--max-matches", type=int, default=200)
    riot.add_argument(
        "--output",
        default=str(Path.home() / ".config/tft-assistant/baseline-matches.json"),
    )
    refresh = commands.add_parser("refresh")
    refresh.add_argument("patch_dir")
    refresh.add_argument(
        "--snapshots", default=str(Path.home() / ".config/tft-assistant/data-snapshots")
    )
    refresh.add_argument("--sources", default="../data/sources.toml")
    refresh.add_argument(
        "--overrides", default=str(Path.home() / ".config/tft-assistant/overrides.toml")
    )
    refresh.add_argument("--offline", action="store_true")
    refresh.add_argument("--engine-computed", action="store_true")
    review=commands.add_parser('prepare-review')
    review.add_argument('patch')
    review.add_argument('--set',dest='set_number',type=int,required=True)
    review.add_argument('--review-dir',required=True)
    review.add_argument('--cdragon-file',required=True)
    review.add_argument('--ddragon-file',required=True)
    review.add_argument('--entity-overlay-file')
    for command in ("bootstrap", "new-set"):
        bootstrap = commands.add_parser(command)
        bootstrap.add_argument("patch")
        bootstrap.add_argument("--data-dir", default="../data")
        bootstrap.add_argument("--static-file", required=True)
        bootstrap.add_argument("--tunables-file", required=True)
        bootstrap.add_argument("--cdragon-file")
        bootstrap.add_argument("--ddragon-file")
        bootstrap.add_argument("--dragon-version")
        bootstrap.add_argument("--entity-overlay-file")
        if command == "new-set":
            bootstrap.add_argument("--from-patch", required=True)
            bootstrap.add_argument("--live-at", required=True)
            bootstrap.add_argument(
                "--overrides",
                default=str(Path.home() / ".config/tft-assistant/overrides.toml"),
            )
    args = parser.parse_args(argv)
    try:
        if args.command=='prepare-review':
            from .candidate import prepare_review
            target=prepare_review(args.review_dir,args.patch,args.set_number,args.cdragon_file,args.ddragon_file,
                entity_overlay_file=args.entity_overlay_file)
            print(f'Prepared incomplete offline review inputs at {target}; no production patch or snapshot published.')
            return 0
        if args.command in {"bootstrap", "new-set"}:
            options = {
                "cdragon": json.loads(Path(args.cdragon_file).read_text())
                if args.cdragon_file
                else None,
                "ddragon": json.loads(Path(args.ddragon_file).read_text())
                if args.ddragon_file
                else None,
                "dragon_version": args.dragon_version,
                "entity_overlay_file": args.entity_overlay_file,
            }
            if args.command == "new-set":
                target = prepare_new_set(
                    args.data_dir,
                    args.patch,
                    args.from_patch,
                    args.static_file,
                    args.tunables_file,
                    args.live_at,
                    overrides=args.overrides,
                    **options,
                )
            else:
                target = bootstrap_patch(
                    args.data_dir,
                    args.patch,
                    args.static_file,
                    args.tunables_file,
                    **options,
                )
            print(
                f"Prepared candidate at {target}; review patch-diff.md and commit accepted files."
            )
            return 0
        if args.command == "new-patch":
            candidate = new_patch(
                args.data_dir,
                args.patch,
                args.from_patch,
                args.live_at,
                dragon_version=args.dragon_version,
                offline=args.offline,
                cdragon=json.loads(Path(args.cdragon_file).read_text())
                if args.cdragon_file
                else None,
                ddragon=json.loads(Path(args.ddragon_file).read_text())
                if args.ddragon_file
                else None,
            )
            print(
                f"Patch candidate prepared: {candidate}. Review patch-diff.md, validate, then commit accepted values."
            )
            return 0
        if args.command == "riot-matches":
            import os
            import tempfile

            from .riot import RiotClient

            client = riot_client or RiotClient()
            account = client.account(args.game_name, args.tag_line)
            rank = client.rank()
            matches = client.own_matches(
                set_number=args.set, max_matches=args.max_matches
            )
            output = Path(args.output).resolve()
            if any((ancestor / ".git").exists() for ancestor in output.parents):
                raise DataError(
                    "Raw owner match data must be stored outside every Git repository"
                )
            output.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_path = tempfile.mkstemp(dir=output.parent)
            try:
                with os.fdopen(descriptor, "w") as stream:
                    json.dump(
                        {
                            "owner_puuid": account["puuid"],
                            "rank": rank,
                            "matches": matches,
                        },
                        stream,
                    )
                os.replace(temp_path, output)
            finally:
                if Path(temp_path).exists():
                    Path(temp_path).unlink()
            print(f"Cached {len(matches)} own ranked matches in the local output file.")
            return 0
        options = {}
        if args.command == "refresh":
            from .source_config import SourceConfiguration

            if not args.offline:
                config = SourceConfiguration.load(args.sources)
                options.update(sources=config.sources, fallback=config.fallback)
            options["overrides"] = args.overrides
            if args.engine_computed:
                try:
                    from tft_engine import growth_curve
                except ImportError:
                    raise DataError(
                        "Engine package unavailable for computed growth curve"
                    ) from None
                options["computations"] = {"opponent_growth_curve": growth_curve}
        result = DataStore(args.snapshots).refresh(
            args.patch_dir, now=datetime.now(UTC), **options
        )
        for warning in result.warnings:
            print(warning)
        if result.snapshot is None or result.error:
            return 2
        print(
            f"Validated immutable snapshot {result.snapshot.snapshot_id}, patch {result.snapshot.patch}."
        )
        return 0
    except (DataError, OSError, ValueError) as exc:
        print(f"tft-data: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
