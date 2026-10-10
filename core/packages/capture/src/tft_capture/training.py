"""Offline reader maintenance CLI. Heavy training imports are lazy."""

import argparse
import json
from pathlib import Path


def main(argv=None, *, transport=None):
    parser = argparse.ArgumentParser(prog="tft-train")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare-models")
    prepare.add_argument(
        "--pointer", type=Path, default=Path(__file__).with_name("models.json")
    )
    prepare.add_argument("--cache", type=Path, required=True)
    templates = commands.add_parser("templates")
    templates.add_argument("--source", type=Path, required=True)
    templates.add_argument("--patch", required=True)
    templates.add_argument("--cache", type=Path, required=True)
    calibration = commands.add_parser("calibrate")
    calibration.add_argument("--samples", type=Path, required=True)
    calibration.add_argument("--output", type=Path, required=True)
    crops = commands.add_parser("crops")
    crops.add_argument("--log", type=Path, required=True)
    crops.add_argument("--output", type=Path, required=True)
    split = commands.add_parser("split")
    split.add_argument("--dataset", type=Path, required=True)
    split.add_argument("--output", type=Path, required=True)
    split.add_argument("--seed", type=int, default=38)
    compare = commands.add_parser("compare")
    compare.add_argument("--current", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--split", type=Path, required=True)
    compare.add_argument("--report", type=Path, required=True)
    accept = commands.add_parser("accept")
    accept.add_argument("--current", type=Path, required=True)
    accept.add_argument("--candidate", type=Path, required=True)
    accept.add_argument("--split", type=Path, required=True)
    accept.add_argument("--report", type=Path, required=True)
    accept.add_argument("--pointer", type=Path, required=True)
    accept.add_argument("--cache", type=Path, required=True)
    train = commands.add_parser("train")
    train.add_argument("--current", type=Path, required=True)
    train.add_argument("--split", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--epochs", type=int, default=3)
    train.add_argument("--batch-size", type=int, default=8)
    train.add_argument("--learning-rate", type=float, default=0.0001)
    train.add_argument("--seed", type=int, default=38)
    args = parser.parse_args(argv)
    if args.command == "prepare-models":
        from tft_capture.reader_assets import prepare_models

        print(json.dumps(prepare_models(args.pointer, args.cache, transport=transport)))
    elif args.command == "templates":
        from tft_capture.reader_assets import prepare_templates

        result = prepare_templates(
            json.loads(args.source.read_text()),
            args.cache,
            patch=args.patch,
            transport=transport,
        )
        print(json.dumps({"templates": len(result["templates"]), "patch": args.patch}))
    elif args.command == "calibrate":
        import statistics

        from tft_capture.reader_assets import atomic_json

        grouped = {}
        sources = set()
        for sample in json.loads(args.samples.read_text()):
            if not sample.get("source") or not sample.get("game_id"):
                raise ValueError(
                    "Foot-offset calibration requires reviewed source and game provenance"
                )
            _, bar_y, bar_width, _ = sample["bar"]
            ratio = (sample["foot_y"] - bar_y) / bar_width
            if not 0.5 <= ratio <= 4:
                raise ValueError(
                    "Foot-offset sample is outside the supported projection range"
                )
            grouped.setdefault(sample["champion"].casefold(), []).append(ratio)
            sources.add(sample["source"])
        result = {
            "foot_offsets": {
                name: statistics.median(values) for name, values in grouped.items()
            },
            "counts": {name: len(values) for name, values in grouped.items()},
            "sources": sorted(sources),
        }
        atomic_json(args.output, result)
        print(json.dumps(result))
    elif args.command == "crops":
        from tft_capture.crops import harvest

        print(json.dumps(harvest(args.log, args.output)))
    elif args.command == "split":
        from tft_capture.model_validation import split_dataset

        result = split_dataset(args.dataset, args.output, seed=args.seed)
        print(
            json.dumps(
                {
                    "train": len(result["train"]),
                    "heldout": len(result["heldout"]),
                    "dataset_fingerprint": result["dataset_fingerprint"],
                }
            )
        )
    elif args.command == "compare":
        from tft_capture.model_validation import compare_models

        result = compare_models(args.current, args.candidate, args.split, args.report)
        print(
            json.dumps(
                {
                    "accepted": result["accepted"],
                    "qualified": result["qualified"],
                    "report": str(args.report),
                }
            )
        )
        return 0 if result["accepted"] else 2
    elif args.command == "accept":
        from tft_capture.model_validation import promote

        result = promote(
            args.current,
            args.candidate,
            args.split,
            args.report,
            args.pointer,
            args.cache,
        )
        print(
            json.dumps(
                {
                    "accepted": result["accepted"],
                    "qualified": result["qualified"],
                    "report": str(args.report),
                }
            )
        )
        return 0 if result["accepted"] else 2
    elif args.command == "train":
        from tft_capture.fine_tune import fine_tune

        print(
            json.dumps(
                fine_tune(
                    args.current,
                    args.split,
                    args.output,
                    epochs=args.epochs,
                    batch_size=args.batch_size,
                    learning_rate=args.learning_rate,
                    seed=args.seed,
                )
            )
        )
    return 0
