"""Own-board CPU inference; uncertain details remain partial observations."""

import hashlib
import json
import re
from pathlib import Path

from tft_capture.vision import VisionRead


class ReaderUnavailable(RuntimeError):
    pass


class CPUClassifier:
    def __init__(self, directory, stem, *, set_number):
        import onnxruntime as ort

        ort.disable_telemetry_events()

        directory = Path(directory)
        required = [
            directory / f"{stem}.json",
            directory / f"{stem}.onnx",
            directory / f"{stem}.onnx.data",
        ]
        if any(not path.is_file() for path in required):
            raise ReaderUnavailable(
                f"Reader assets missing in {directory}; prepare {stem}.onnx, its .onnx.data and metadata before capture"
            )
        self.metadata = json.loads(required[0].read_text())
        if (
            self.metadata.get("set_number") != set_number
            or self.metadata.get("engine") != "unreal"
        ):
            raise ReaderUnavailable(
                "Reader model targets a different set/client; prepare current recognition assets"
            )
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")
        self.session = ort.InferenceSession(
            str(required[1]), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.labels = self.metadata["labels"]
        self.providers = tuple(self.session.get_providers())

    def predict(self, images):
        import numpy as np

        from tft_capture._coach import preprocess

        if not images:
            return []
        batch = preprocess(images, self.metadata)
        logits = self.session.run(None, {self.session.get_inputs()[0].name: batch})[0]
        logits = logits - logits.max(axis=1, keepdims=True)
        probabilities = np.exp(logits)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        return [
            (self.labels[int(row.argmax())], float(row.max())) for row in probabilities
        ]


class BoardReader:
    def __init__(
        self,
        model_directory,
        *,
        set_number,
        unit_ids,
        templates=None,
        foot_offsets=None,
        identity_min=0.55,
    ):
        self.units = CPUClassifier(
            model_directory, "unit_classifier", set_number=set_number
        )
        self.stars = CPUClassifier(
            model_directory, "star_level_classifier", set_number=set_number
        )
        from tft_capture.model_validation import fingerprint, model_files

        self.model_version = "reader-" + fingerprint(model_files(model_directory))[:16]
        self.source = "tft-coach:" + self.model_version
        self.providers = self.units.providers
        self.unit_ids = {
            self._key(name): identity for name, identity in unit_ids.items()
        }
        self.label_map = {
            identity: label
            for label in self.units.labels
            for identity in [self.unit_ids.get(self._key(label))]
            if identity
        }
        self.templates = templates
        if isinstance(foot_offsets, (str, Path)):
            foot_offsets = json.loads(Path(foot_offsets).read_text())["foot_offsets"]
        self.foot_offsets = {"kayle": 2.62, **(foot_offsets or {})}
        self.identity_min = identity_min

    @classmethod
    def from_data(cls, model_directory, data, **kwargs):
        """Map base visual classes to canonical current-set IDs, independently of client locale."""
        metadata = json.loads(
            (Path(model_directory) / "unit_classifier.json").read_text()
        )
        identities = {}
        for label in metadata["labels"]:
            matches = []
            for entity in data.entities.values():
                if entity.kind != "unit":
                    continue
                stable = re.sub(r"^(?:DA_|TFT\d*_)", "", entity.id)
                stable = re.sub(r"\d+|_Base$", "", stable)
                if cls._key(label) in {cls._key(entity.name), cls._key(stable)}:
                    matches.append(entity.id)
            if len(set(matches)) == 1:
                identities[label] = matches[0]
        tunable = data.tunables.get("board_reader_identity_min")
        kwargs.setdefault("identity_min", tunable.value if tunable else 0.55)
        return cls(
            model_directory, set_number=data.set_number, unit_ids=identities, **kwargs
        )

    @classmethod
    def from_version(cls, cache, *, pointer=None, data=None, **kwargs):
        """Open verified local assets selected by a portable committed version pointer."""
        pointer = Path(pointer) if pointer else Path(__file__).with_name("models.json")
        manifest = json.loads(pointer.read_text())
        version = manifest["version"]
        if Path(version).name != version or version in {".", ".."}:
            raise ReaderUnavailable("Invalid model version pointer")
        directory = Path(cache) / version
        for name, digest in manifest["files"].items():
            path = directory / name
            if (
                path.name != name
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest
            ):
                raise ReaderUnavailable(
                    f"Reader cache missing or corrupt: {name}; run tft-train prepare-models --cache <directory> before capture"
                )
        return (
            cls.from_data(directory, data, **kwargs)
            if data is not None
            else cls(directory, **kwargs)
        )

    @staticmethod
    def _key(value):
        return re.sub(r"[^a-z0-9]", "", value.casefold())

    def read(self, image, *, regions, own_view):
        if own_view is not True or "board" not in regions:
            return VisionRead({}, self.source, 0)
        import numpy as np

        from tft_capture._coach import (
            UnitCrop,
            crops,
            extract_unit_detail_regions,
            hex_position,
        )

        frame = image.bgr_view() if hasattr(image, "bgr_view") else np.asarray(image.convert("RGB"))[:, :, ::-1].copy()
        samples = []
        for sample in crops(frame):
            allowed = (
                regions.get("bench", regions["board"])
                if sample.zone == "bench"
                else regions["board"]
            )
            x, y, w, h = sample.bar
            if not (
                allowed[0] <= x + w / 2 < allowed[2]
                and allowed[1] <= y + h / 2 < allowed[3]
            ):
                continue
            left, top, right, bottom = sample.bounds
            bounds = (
                max(left, allowed[0]),
                max(top, allowed[1]),
                min(right, allowed[2]),
                min(bottom, allowed[3]),
            )
            if bounds[0] < bounds[2] and bounds[1] < bounds[3]:
                left, top, right, bottom = bounds
                samples.append(
                    UnitCrop(
                        sample.zone,
                        sample.position,
                        bounds,
                        frame[top:bottom, left:right].copy(),
                        sample.bar,
                    )
                )
        identities = self.units.predict([sample.image for sample in samples])
        details = [extract_unit_detail_regions(sample.image) for sample in samples]
        valid = [
            index
            for index, detail in enumerate(details)
            if detail is not None and detail.star_badge.size
        ]
        star_results = dict(
            zip(
                valid,
                self.stars.predict([details[index].star_badge for index in valid]),
            )
        )
        observations = []
        for index, (sample, (label, confidence)) in enumerate(zip(samples, identities)):
            unit_id = (
                self.unit_ids.get(self._key(label))
                if not label.startswith("_")
                else None
            )
            star_label, star_confidence = star_results.get(index, (None, 0))
            stars = (
                int(star_label)
                if star_label in {"1", "2", "3"}
                and star_confidence >= self.stars.metadata.get("min_confidence", 0.7)
                else None
            )
            position = sample.position
            if sample.zone == "board" and self._key(label) in self.foot_offsets:
                position = hex_position(
                    sample.bar,
                    image.size,
                    foot_ratio=self.foot_offsets[self._key(label)],
                )
            if (
                sample.zone == "board"
                and self._key(label) == "maokai"
                and "maokai" not in self.foot_offsets
            ):
                position = None  # Tall Maokai needs a reviewed foot projection, never a guessed hex.
            items = None
            observed_items = []
            if self.templates is not None and details[index] is not None:
                matches = [
                    self.templates.match(icon) for icon in details[index].item_icons
                ]
                observed_items = [
                    match[0]
                    for match in matches
                    if match is not None and match[0] is not None
                ]
                if len(matches) == 3 and all(match is not None for match in matches):
                    items = [match[0] for match in matches if match[0] is not None]
            observations.append(
                {
                    "zone": sample.zone,
                    "position": position,
                    "bounds": list(sample.bounds),
                    "bar": list(sample.bar),
                    "label": label,
                    "unit_id": unit_id,
                    "identity_confidence": confidence,
                    "stars": stars,
                    "star_confidence": star_confidence,
                    "items": items,
                    "observed_items": observed_items,
                }
            )
        fields = {"board_observations": observations}
        if self.templates is not None and "item_bench" in regions:
            x0, y0, x1, y1 = regions["item_bench"]
            fields["item_bench_observations"] = {
                "items": self.templates.scan(frame[y0:y1, x0:x1]),
                "complete": False,
            }
        # Only complete details enter the typed Engine board. Partial observations are still logged.
        complete = bool(observations) and all(
            o["unit_id"]
            and o["identity_confidence"] >= self.identity_min
            and o["stars"]
            and o["items"] is not None
            for o in observations
        )
        if complete:
            units = [
                {
                    "unit_id": o["unit_id"],
                    "stars": o["stars"],
                    "items": o["items"],
                    "position": o["position"],
                }
                for o in observations
                if o["zone"] == "board"
            ]
            bench = [
                {
                    "unit_id": o["unit_id"],
                    "stars": o["stars"],
                    "items": o["items"],
                    "position": o["position"],
                }
                for o in observations
                if o["zone"] == "bench"
            ]
            fields.update(
                board={"units": units, "bench": bench, "trait_counts": None},
                bench=bench,
            )
        return VisionRead(
            fields,
            self.source,
            min((o["identity_confidence"] for o in observations), default=0),
            False,
        )
