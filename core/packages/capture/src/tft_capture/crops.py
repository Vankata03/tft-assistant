"""Harvest own-keyframe crops with independent ownership labels and provenance."""

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from PIL import Image

from tft_capture.reader_assets import atomic_json


def read_log(path):
    events = []
    for line in Path(path).read_bytes().splitlines(keepends=True):
        if not line.endswith(b"\n"):
            break
        event = json.loads(line)
        if event.get("seq") != len(events):
            raise ValueError("Invalid committed game-log sequence")
        events.append(event)
    return events


def harvest(log_path, output, *, identity_min=0.55):
    log_path, output = Path(log_path), Path(output)
    events = read_log(log_path)
    reads = {
        event["timestamp"]: event["payload"]
        for event in events
        if event["kind"] == "board_read"
    }
    existing = (
        json.loads((output / "crops.json").read_text())
        if (output / "crops.json").exists()
        else {"v": 1, "crops": []}
    )
    rows = {row["id"]: row for row in existing["crops"]}
    for event in events:
        if event["kind"] != "keyframe" or event["payload"].get("reason") not in {
            "own_board",
            "reader_disagreement",
        }:
            continue
        read = reads.get(event["timestamp"])
        if not read:
            continue  # Never pair labels with a different captured frame.
        ownership = [
            other
            for other in events
            if other["kind"] == "ownership"
            and datetime.fromisoformat(other["timestamp"])
            <= datetime.fromisoformat(event["timestamp"])
            and other["seq"] <= event["seq"]
        ]
        owned = ownership[-1]["payload"] if ownership else {}
        counts = owned.get("copies", {})
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in counts.values()
        ):
            raise ValueError("Ownership labels need nonnegative copy counts")
        remaining = Counter(counts) if owned.get("complete") is True else Counter()
        observations = read.get("observations", [])
        known, unknown = {}, []
        for index, observation in enumerate(observations):
            identity = observation.get("unit_id")
            stars = observation.get("stars")
            copies = 3 ** (stars - 1) if stars in (1, 2, 3) else 0
            if (
                owned.get("complete") is True
                and identity
                and observation.get("identity_confidence", 0) >= identity_min
                and copies
                and remaining[identity] >= copies
            ):
                remaining[identity] -= copies
                known[index] = (identity, stars, "ownership_confirmed_classifier")
            else:
                unknown.append(index)
        leftovers = {
            identity: count for identity, count in remaining.items() if count > 0
        }
        labelled = {}
        if not unknown and not leftovers:
            labelled = known
        elif len(unknown) == 1 and len(leftovers) == 1:
            identity, copies = next(iter(leftovers.items()))
            if copies in (1, 3, 9):
                labelled = {
                    **known,
                    unknown[0]: (
                        identity,
                        {1: 1, 3: 2, 9: 3}[copies],
                        "unique_remaining_ownership",
                    ),
                }
        name = event["payload"]["path"]
        media = (log_path.parent / name).resolve()
        if not media.is_relative_to(log_path.parent.resolve()):
            raise ValueError("Keyframe path escapes its game directory")
        if not media.is_file():
            continue  # Media can be evicted independently of its permanent log.
        with Image.open(media) as image:
            for index, observation in enumerate(observations):
                left, top, right, bottom = observation["bounds"]
                if not (
                    0 <= left < right <= image.width
                    and 0 <= top < bottom <= image.height
                ):
                    continue
                identity, stars, source = labelled.get(
                    index, (None, None, "unlabelled")
                )
                crop = image.crop((left, top, right, bottom)).convert("RGB")
                crop_id = hashlib.sha256(
                    f"{log_path.parent.name}:{name}:{index}".encode()
                ).hexdigest()
                filename = f"{'labelled' if identity else 'unlabelled'}/{crop_id}.png"
                destination = output / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                crop.save(destination)
                label = (
                    read.get("label_map", {}).get(identity, identity)
                    if identity
                    else None
                )
                rows[crop_id] = {
                    "id": crop_id,
                    "file": filename,
                    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                    "game_id": log_path.parent.name,
                    "keyframe": name,
                    "timestamp": event["timestamp"],
                    "unit_id": identity,
                    "label": label,
                    "stars": stars,
                    "label_source": source,
                    "model_version": read.get("model_version"),
                    "bounds": observation["bounds"],
                }
    result = {"v": 1, "crops": sorted(rows.values(), key=lambda row: row["id"])}
    atomic_json(output / "crops.json", result)
    return {
        "labelled": sum(row["unit_id"] is not None for row in rows.values()),
        "unlabelled": sum(row["unit_id"] is None for row in rows.values()),
    }
