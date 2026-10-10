"""Explicit preparation of versioned Riot icon assets before capture."""

import hashlib
import io
import json
import os
from pathlib import Path

from PIL import Image


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def asset_url(icon, patch):
    if icon.startswith("https://"):
        return icon
    name = icon.lower()
    if name.endswith((".tex", ".dds")):
        name = name.rsplit(".", 1)[0] + ".png"
    return f"https://raw.communitydragon.org/{patch}/game/" + name


def prepare_templates(payload, cache, *, patch, transport=None):
    import httpx

    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    by_icon = {}
    for entry in payload.get("items", []):
        identity = entry.get("apiName")
        icon = entry.get("icon")
        if (
            identity
            and icon
            and not identity.startswith(("TFTTutorial_", "TFT_Assist_"))
        ):
            by_icon.setdefault(asset_url(icon, patch), []).append(entry)
    manifest = {"patch": patch, "templates": {}, "aliases": {}}
    with httpx.Client(
        transport=transport,
        timeout=30,
        headers={"User-Agent": "tft-assistant/recognition-assets"},
    ) as client:
        for url, entries in sorted(by_icon.items()):
            # Same artwork is one identity. Prefer the live DA identifier to legacy aliases.
            entry = min(
                entries,
                key=lambda row: (not row["apiName"].startswith("DA_"), row["apiName"]),
            )
            identity = entry["apiName"]
            response = client.get(url)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
            image.verify()
            digest = hashlib.sha256(response.content).hexdigest()
            filename = digest + ".png"
            temporary = cache / (filename + ".tmp")
            temporary.write_bytes(response.content)
            temporary.replace(cache / filename)
            manifest["templates"][identity] = {
                "file": filename,
                "sha256": digest,
                "url": url,
                "name": entry.get("name", identity),
            }
            for alias in entries:
                manifest["aliases"][alias["apiName"]] = identity
    # A failed fetch cannot replace the previous accepted template catalog.
    atomic_json(cache / "templates.json", manifest)
    return manifest


class TemplateBank:
    def __init__(self, templates, *, aliases=None, minimum=0.78, margin=0.10):

        self.templates = templates
        self.aliases = aliases or {}
        self.minimum, self.margin = minimum, margin
        self._matrix = {}

    @classmethod
    def load(cls, directory):
        import cv2

        directory = Path(directory)
        manifest = json.loads((directory / "templates.json").read_text())
        templates = {}
        for identity, entry in manifest["templates"].items():
            path = directory / entry["file"]
            if (
                path.name != entry["file"]
                or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]
            ):
                raise ValueError(f"Recognition template integrity failed: {identity}")
            templates[identity] = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if templates[identity] is None:
                raise ValueError(f"Recognition template cannot be decoded: {identity}")
        return cls(templates, aliases=manifest["aliases"])

    def match(self, icon):
        import cv2
        import numpy as np

        if not self.templates or icon is None or not icon.size:
            return None

        def descriptor(image):
            values = (
                cv2.resize(image, (32, 32), interpolation=cv2.INTER_AREA)
                .astype(np.float32)
                .reshape(-1)
            )
            values -= values.mean()
            norm = np.linalg.norm(values)
            return values / max(float(norm), 1e-8)

        if not self._matrix:
            names = sorted(self.templates)
            self._matrix = {
                "names": names,
                "values": np.stack(
                    [descriptor(self.templates[name]) for name in names]
                ),
            }
        scores = self._matrix["values"] @ descriptor(icon)
        order = np.argsort(scores)[::-1]
        best = int(order[0])
        runner = float(scores[int(order[1])]) if len(order) > 1 else -1
        if scores[best] < self.minimum or scores[best] - runner < self.margin:
            return None
        identity = self._matrix["names"][best]
        return (None if identity == "_empty" else identity, float(scores[best]))

    def scan(self, image):
        """Return positive inventory icon sightings; no match does not prove empty."""
        import cv2
        import numpy as np

        if not image.size:
            return []
        result = []
        for identity, template in self.templates.items():
            if identity == "_empty":
                continue
            for size in (round(image.shape[1] * ratio) for ratio in (0.60, 0.72, 0.84)):
                if size < 8 or size > image.shape[0]:
                    continue
                scaled = cv2.resize(
                    template, (size, size), interpolation=cv2.INTER_AREA
                )
                matches = cv2.matchTemplate(image, scaled, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.where(matches >= 0.82)
                for x, y in zip(xs, ys):
                    result.append(
                        {
                            "item_id": identity,
                            "x": int(x),
                            "y": int(y),
                            "size": size,
                            "confidence": float(matches[y, x]),
                        }
                    )
        accepted = []
        for candidate in sorted(
            result, key=lambda item: item["confidence"], reverse=True
        ):
            x, y, size = candidate["x"], candidate["y"], candidate["size"]
            identity = self.match(image[y : y + size, x : x + size])
            if identity is None or identity[0] != candidate["item_id"]:
                continue
            if not any(
                abs(candidate["x"] - other["x"]) + abs(candidate["y"] - other["y"])
                < candidate["size"]
                for other in accepted
            ):
                accepted.append(candidate)
        return sorted(accepted, key=lambda item: (item["y"], item["x"]))


def prepare_models(pointer, cache, *, transport=None):
    """Fetch a reviewed pointer explicitly; capture itself performs no network access."""
    import tempfile

    import httpx

    pointer, cache = Path(pointer), Path(cache)
    manifest = json.loads(pointer.read_text())
    version = manifest["version"]
    if not version or Path(version).name != version or version in {".", ".."}:
        raise ValueError("Invalid portable model version")
    required = {
        stem + suffix
        for stem in ("unit_classifier", "star_level_classifier")
        for suffix in (".json", ".onnx", ".onnx.data")
    }
    if set(manifest["files"]) != required:
        raise ValueError("Model pointer must include all six classifier assets")

    def verified(directory):
        return all(
            (directory / name).is_file()
            and hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
            for name, digest in manifest["files"].items()
        )

    destination = cache / version
    if verified(destination):
        return {"version": version, "files": 6}
    if destination.exists():
        raise ValueError(
            "Model cache integrity failed; preserve it for inspection and use a new cache"
        )
    base = manifest.get("base_url")
    if not base or not base.startswith("https://"):
        raise ValueError(
            "Accepted local model version is absent; restore its external cache before capture"
        )
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reader-fetch-", dir=cache) as temporary:
        staging = Path(temporary) / version
        staging.mkdir()
        with httpx.Client(transport=transport, timeout=60) as client:
            for name, digest in manifest["files"].items():
                response = client.get(base.rstrip("/") + "/" + name)
                response.raise_for_status()
                if hashlib.sha256(response.content).hexdigest() != digest:
                    raise ValueError(f"Model download integrity failed: {name}")
                (staging / name).write_bytes(response.content)
        if not verified(staging):
            raise ValueError("Model bundle verification failed")
        staging.replace(destination)
    return {"version": version, "files": 6}
