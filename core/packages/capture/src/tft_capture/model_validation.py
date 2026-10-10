"""Deterministic game-held-out datasets and paired model qualification."""

import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path

from tft_capture.reader_assets import atomic_json


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def split_dataset(dataset, output, *, seed=38, heldout_fraction=0.2):
    dataset, output = Path(dataset), Path(output)
    rows = [
        dict(row)
        for row in json.loads(dataset.read_text())["crops"]
        if row.get("label") and row.get("unit_id")
    ]
    if len({row["game_id"] for row in rows}) < 2:
        raise ValueError(
            "Training needs labelled crops from at least two separate games"
        )
    # Duplicate pixels connect their games: keeping that component together prevents image leakage.
    groups = {row["game_id"]: row["game_id"] for row in rows}

    def find(group):
        while groups[group] != group:
            group = groups[group]
        return group

    by_hash = {}
    for row in rows:
        path = (dataset.parent / row["file"]).resolve()
        if not path.is_relative_to(dataset.parent.resolve()):
            raise ValueError("Crop path escapes its dataset")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if row.get("sha256") != digest:
            raise ValueError("Crop changed after labelling; regenerate the manifest")
        other = by_hash.setdefault(digest, row["game_id"])
        groups[find(row["game_id"])] = find(other)
        row["file"] = Path(os.path.relpath(path, output.parent)).as_posix()
    components = sorted(
        {find(group) for group in groups},
        key=lambda group: hashlib.sha256(f"{seed}:{group}".encode()).hexdigest(),
    )
    if len(components) < 2:
        raise ValueError("Duplicate imagery leaves no independent held-out game group")
    count = min(len(components) - 1, max(1, round(len(components) * heldout_fraction)))
    heldout = set(components[:count])
    result = {"v": 1, "seed": seed, "train": [], "heldout": []}
    for row in sorted(rows, key=lambda row: row["id"]):
        result["heldout" if find(row["game_id"]) in heldout else "train"].append(row)
    result["dataset_fingerprint"] = fingerprint(
        {key: result[key] for key in ("train", "heldout")}
    )
    atomic_json(output, result)
    return result


def load_split(path):
    path = Path(path)
    result = json.loads(path.read_text())
    if result.get("dataset_fingerprint") != fingerprint(
        {key: result[key] for key in ("train", "heldout")}
    ):
        raise ValueError("Held-out split fingerprint changed")
    train = result["train"]
    heldout = result["heldout"]
    if {row["game_id"] for row in train} & {row["game_id"] for row in heldout}:
        raise ValueError("Training and held-out games overlap")
    if {row["sha256"] for row in train} & {row["sha256"] for row in heldout}:
        raise ValueError("Training and held-out pixels overlap")
    if not train or not heldout:
        raise ValueError("The split needs both training and held-out crops")
    for row in train + heldout:
        actual = (path.parent / row["file"]).resolve()
        if hashlib.sha256(actual.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Crop content changed after splitting")
        if not row.get("game_id") or not row.get("keyframe"):
            raise ValueError(
                "Held-out comparison requires game and keyframe provenance"
            )
    return result


def model_files(directory):
    directory = Path(directory)
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.glob("*classifier*"))
        if path.is_file() and path.suffix in {".onnx", ".data", ".json"}
    }


def compare_models(current, candidate, split_path, report_path):
    import cv2

    from tft_capture.board_reader import CPUClassifier

    split_path = Path(split_path)
    split = load_split(split_path)
    current_files = model_files(current)
    candidate_files = model_files(candidate)
    current_meta = json.loads((Path(current) / "unit_classifier.json").read_text())
    existing = CPUClassifier(
        current, "unit_classifier", set_number=current_meta["set_number"]
    )
    proposed = CPUClassifier(
        candidate, "unit_classifier", set_number=current_meta["set_number"]
    )
    labels = existing.labels
    missing_labels = sorted(set(labels) - set(proposed.labels))
    rows = []
    pixel_labels = {}
    for row in split["heldout"]:
        previous = pixel_labels.setdefault(row["sha256"], row["label"])
        if previous != row["label"]:
            raise ValueError("Identical held-out pixels have conflicting labels")
        if not any(existing_row["sha256"] == row["sha256"] for existing_row in rows):
            rows.append(row)
    label_sources = {
        "ownership_confirmed_classifier",
        "unique_remaining_ownership",
        "owner_reviewed",
    }
    unverified_labels = [
        row["id"] for row in rows if row.get("label_source") not in label_sources
    ]
    predictions = []
    # Identical bytes, identical split, preprocessing specific to each model.
    for offset in range(0, len(rows), 16):
        batch = rows[offset : offset + 16]
        images = [
            cv2.imread(str(split_path.parent / row["file"]), cv2.IMREAD_COLOR)
            for row in batch
        ]
        if any(image is None for image in images):
            raise ValueError("Held-out crop cannot be decoded")
        for row, old, new in zip(
            batch, existing.predict(images), proposed.predict(images)
        ):
            label = row["label"]
            if label not in labels:
                matches = [
                    name
                    for name in labels
                    if "".join(c for c in name.casefold() if c.isalnum())
                    == "".join(c for c in label.casefold() if c.isalnum())
                ]
                if len(matches) != 1:
                    raise ValueError(
                        f"Training label {label} has no unambiguous current model class"
                    )
                label = matches[0]
            predictions.append(
                {
                    "id": row["id"],
                    "game_id": row["game_id"],
                    "label": label,
                    "sha256": row["sha256"],
                    "current": old[0],
                    "candidate": new[0],
                    "current_confidence": old[1],
                    "candidate_confidence": new[1],
                }
            )
    per_class = {}
    unqualified = []
    regressions = []
    for label in labels:
        samples = [row for row in predictions if row["label"] == label]
        grouped = defaultdict(list)
        for row in samples:
            grouped[row["game_id"]].append(
                int(row["candidate"] == label) - int(row["current"] == label)
            )
        losses = sum(sum(values) < 0 for values in grouped.values())
        wins = sum(sum(values) > 0 for values in grouped.values())
        discordant = losses + wins
        probability = (
            sum(math.comb(discordant, k) for k in range(losses, discordant + 1))
            / 2**discordant
            if discordant
            else 1.0
        )
        old_correct = sum(row["current"] == label for row in samples)
        new_correct = sum(row["candidate"] == label for row in samples)
        qualified = len(samples) >= 20 and len(grouped) >= 5
        regressed = new_correct < old_correct and probability < 0.05
        if not qualified:
            unqualified.append(label)
        if regressed:
            regressions.append(label)

        # Wilson intervals describe crop counts; the regression gate uses paired whole-game signs.
        def interval(correct, count):
            if not count:
                return None
            z = 1.95996398454
            p = correct / count
            center = (p + z * z / (2 * count)) / (1 + z * z / count)
            half = (
                z
                * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count))
                / (1 + z * z / count)
            )
            return [max(0, center - half), min(1, center + half)]

        per_class[label] = {
            "count": len(samples),
            "games": len(grouped),
            "current_correct": old_correct,
            "candidate_correct": new_correct,
            "current_interval": interval(old_correct, len(samples)),
            "candidate_interval": interval(new_correct, len(samples)),
            "paired_game_losses": losses,
            "paired_game_wins": wins,
            "regression_p": probability,
            "qualified": qualified,
            "regressed": regressed,
        }
    old_correct = sum(row["current"] == row["label"] for row in predictions)
    new_correct = sum(row["candidate"] == row["label"] for row in predictions)
    if current_files != model_files(current) or candidate_files != model_files(
        candidate
    ):
        raise ValueError(
            "Model bundle changed during held-out comparison; repeat qualification"
        )
    star_names = {
        "star_level_classifier" + suffix for suffix in (".json", ".onnx", ".onnx.data")
    }
    star_bundle_changed = any(
        current_files.get(name) is None
        or current_files.get(name) != candidate_files.get(name)
        for name in star_names
    )
    report = {
        "v": 1,
        "accepted": not missing_labels
        and not unqualified
        and not unverified_labels
        and not regressions
        and not star_bundle_changed
        and new_correct >= old_correct,
        "qualified": not missing_labels and not unqualified,
        "unverified_labels": unverified_labels,
        "missing_candidate_labels": missing_labels,
        "unqualified_classes": unqualified,
        "regressed_classes": regressions,
        "count": len(predictions),
        "current_correct": old_correct,
        "candidate_correct": new_correct,
        "dataset_fingerprint": split["dataset_fingerprint"],
        "current_files": current_files,
        "candidate_files": candidate_files,
        "star_bundle_changed": star_bundle_changed,
        "per_class": per_class,
        "predictions": predictions,
        "policy": {
            "qualified_scope": "unit_classifier; unchanged current star bundle required",
            "minimum_class_crops": 20,
            "minimum_class_games": 5,
            "paired_regression_alpha": 0.05,
            "uncertainty": "Wilson crop-count intervals are descriptive; paired game signs gate class regression.",
        },
    }
    atomic_json(report_path, report)
    return report


def promote(current, candidate, split, report, pointer, cache):
    import shutil
    import tempfile

    result = compare_models(current, candidate, split, report)
    if not result["accepted"]:
        return result

    def verify_compared_bytes():
        if (
            model_files(current) != result["current_files"]
            or model_files(candidate) != result["candidate_files"]
        ):
            raise ValueError(
                "Model bundle changed after held-out comparison; repeat qualification"
            )

    verify_compared_bytes()
    files = result["candidate_files"]
    required = {
        stem + suffix
        for stem in ("unit_classifier", "star_level_classifier")
        for suffix in (".json", ".onnx", ".onnx.data")
    }
    if not required <= files.keys():
        raise ValueError("Promotion requires the complete unit and star model bundle")
    version = "reader-" + fingerprint(files)[:16]
    cache = Path(cache)
    destination = cache / version
    cache.mkdir(parents=True, exist_ok=True)
    created_destination = False
    try:
        if not destination.exists():
            with tempfile.TemporaryDirectory(
                prefix=".reader-promote-", dir=cache
            ) as temporary:
                staging = Path(temporary) / version
                staging.mkdir()
                for name in files:
                    shutil.copy2(Path(candidate) / name, staging / name)
                verify_compared_bytes()
                if model_files(staging) != files:
                    raise ValueError("Candidate changed during promotion")
                staging.replace(destination)
                created_destination = True
        if model_files(destination) != files:
            raise ValueError("Existing model version cache is corrupt")
        verify_compared_bytes()
        atomic_json(
            pointer,
            {
                "v": 1,
                "version": version,
                "files": files,
                "dataset_fingerprint": result["dataset_fingerprint"],
                "acceptance_policy": result["policy"],
            },
        )
    except (ValueError, OSError):
        if created_destination:
            shutil.rmtree(destination)
        raise
    return result
