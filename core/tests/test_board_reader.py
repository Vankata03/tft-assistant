from pathlib import Path

from PIL import Image
from tft_capture.ocr import TextLine
from tft_capture.pipeline import CapturePipeline
from tft_core.storage import SessionStore


class LabelOCR:
    source = "recorded-owner-label"

    def read(self, image, *, region):
        return [TextLine("Vanko1 Level 4")] if region == "scouted" else []


def test_cpu_reader_observes_ninth_bench_slot_in_committed_probe(tmp_path):
    from tft_capture.board_reader import BoardReader

    root = Path(__file__).resolve().parents[2]
    reader = BoardReader(_models(), set_number=18, unit_ids={"Karma": "karma"})
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("201")
    pipeline = CapturePipeline(
        "201", ocr=LabelOCR(), sink=logs, visual_reader=reader, own_player_name="Vanko1"
    )
    snapshot = pipeline.tick(
        Image.open(root / "probe/screenshots/2026-10-04/02-shop-with-wisp-2-3.jpg")
    )
    observations = snapshot["fields"]["board_observations"]["value"]
    ninth = [
        item
        for item in observations
        if item["zone"] == "bench" and item["position"] == 8
    ]
    assert len(ninth) == 1
    assert ninth[0]["unit_id"] == "karma"
    assert (
        ninth[0]["items"] is None
    )  # No template inventory means unknown, never empty.
    assert ninth[0]["identity_confidence"] >= 0.55
    assert reader.providers == ("CPUExecutionProvider",)
    assert any(event["kind"] == "snapshot" for event in logs.read_events("201"))


def test_template_cli_prepares_cape_components_without_competing_aliases(
    tmp_path, capsys
):
    import io
    import json

    import httpx
    import numpy as np
    from tft_capture.training import main

    icon = Image.fromarray(
        np.random.default_rng(7).integers(0, 255, (32, 32, 3), dtype=np.uint8)
    )
    content = io.BytesIO()
    icon.save(content, format="PNG")
    entries = [
        {
            "apiName": "DA_TacticiansCape",
            "name": "Tactician’s Cape",
            "icon": "assets/cape.tex",
        },
        {
            "apiName": "TFT_Item_TacticiansRing",
            "name": "Tactician's Cape",
            "icon": "assets/cape.tex",
        },
        {
            "apiName": "DA_Component_BFSword",
            "name": "B.F. Sword",
            "icon": "assets/sword.tex",
        },
    ]
    source = tmp_path / "cdragon.json"
    source.write_text(json.dumps({"items": entries}))
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=content.getvalue())
    )
    assert (
        main(
            [
                "templates",
                "--source",
                str(source),
                "--patch",
                "16.20",
                "--cache",
                str(tmp_path / "icons"),
            ],
            transport=transport,
        )
        == 0
    )
    manifest = json.loads((tmp_path / "icons/templates.json").read_text())
    assert manifest["aliases"]["TFT_Item_TacticiansRing"] == "DA_TacticiansCape"
    assert set(manifest["templates"]) == {"DA_TacticiansCape", "DA_Component_BFSword"}
    assert manifest["patch"] == "16.20"
    assert json.loads(capsys.readouterr().out)["templates"] == 2


def test_reader_disagreement_uses_tracking_below_threshold_and_logs_keyframe(tmp_path):
    from tft_capture.vision import VisionRead

    class RecordedVisual:
        source = "recorded-external-classifier"

        def read(self, image, *, regions, own_view):
            return VisionRead(
                {
                    "board_observations": [
                        {
                            "zone": "board",
                            "position": 5,
                            "bounds": [0, 0, 50, 50],
                            "unit_id": "ashe",
                            "label": "Ashe",
                            "identity_confidence": 0.48,
                            "stars": 2,
                            "star_confidence": 0.95,
                            "items": ["cape"],
                        }
                    ]
                },
                self.source,
                0.48,
            )

    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("202")
    logs.append_event("ownership", {"copies": {"shen": 3}, "complete": True})
    pipeline = CapturePipeline(
        "202",
        ocr=LabelOCR(),
        sink=logs,
        visual_reader=RecordedVisual(),
        own_player_name="Vanko1",
        tracking_events=logs.read_events("202"),
        regions={"scouted": (0, 0, 1, 1), "board": (0, 0, 1, 1)},
    )
    snapshot = pipeline.tick(Image.new("RGB", (100, 100), "white"))
    unit = snapshot["fields"]["board"]["value"]["units"][0]
    assert (
        snapshot["fields"]["board"]["source"]
        == "recorded-external-classifier+purchase-tracking"
    )
    assert unit == {"unit_id": "shen", "stars": 2, "items": ["cape"], "position": 5}
    assert any(
        event["kind"] == "reader_disagreement" for event in logs.read_events("202")
    )
    assert any(
        event["kind"] == "keyframe"
        and event["payload"]["reason"] == "reader_disagreement"
        for event in logs.read_events("202")
    )


def test_foot_offset_cli_keeps_maokai_calibration_explicit(tmp_path, capsys):
    import json

    from tft_capture.training import main

    samples = tmp_path / "positions.json"
    samples.write_text(
        json.dumps(
            [
                {
                    "champion": "Maokai",
                    "bar": [1000, 700, 80, 6],
                    "foot_y": 900,
                    "source": "owner-reviewed-fixture",
                    "game_id": "203",
                }
            ]
        )
    )
    output = tmp_path / "foot-offsets.json"
    assert main(["calibrate", "--samples", str(samples), "--output", str(output)]) == 0
    result = json.loads(output.read_text())
    assert result["foot_offsets"]["maokai"] == 2.5
    assert result["counts"]["maokai"] == 1
    assert result["sources"] == ["owner-reviewed-fixture"]


def test_crop_cli_labels_only_one_unique_missing_owned_unit(tmp_path, capsys):
    import json

    from tft_capture.training import main

    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("204")
    frame = Image.new("RGB", (100, 100), "white")
    stamp = "2026-10-10T12:00:00+00:00"
    logs.append_event(
        "ownership",
        {"copies": {"shen": 1, "ashe": 3}, "complete": True},
        timestamp=stamp,
    )
    logs.write_keyframe(frame, reason="own_board", timestamp=stamp)
    logs.append_event(
        "board_read",
        {
            "observations": [
                {
                    "zone": "board",
                    "position": 0,
                    "bounds": [0, 0, 40, 50],
                    "unit_id": "shen",
                    "identity_confidence": 0.95,
                    "stars": 1,
                },
                {
                    "zone": "board",
                    "position": 1,
                    "bounds": [50, 0, 100, 50],
                    "unit_id": None,
                    "identity_confidence": 0.2,
                    "stars": None,
                },
            ]
        },
        timestamp=stamp,
    )
    output = tmp_path / "crops"
    assert (
        main(["crops", "--log", str(logs.log_path("204")), "--output", str(output)])
        == 0
    )
    manifest = json.loads((output / "crops.json").read_text())
    inferred = [
        row
        for row in manifest["crops"]
        if row["label_source"] == "unique_remaining_ownership"
    ]
    assert (
        len(inferred) == 1
        and inferred[0]["unit_id"] == "ashe"
        and inferred[0]["stars"] == 2
    )
    assert Path(output / inferred[0]["file"]).is_file()
    # Adding a second unaccounted owned identity must keep that crop unlabelled.
    stamp = "2026-10-10T12:00:01+00:00"
    logs.append_event(
        "ownership",
        {"copies": {"shen": 1, "ashe": 3, "lux": 1}, "complete": True},
        timestamp=stamp,
    )
    logs.write_keyframe(frame, reason="own_board", timestamp=stamp)
    logs.append_event(
        "board_read",
        {
            "observations": [
                {
                    "zone": "board",
                    "position": 0,
                    "bounds": [0, 0, 40, 50],
                    "unit_id": "shen",
                    "identity_confidence": 0.95,
                    "stars": 1,
                },
                {
                    "zone": "board",
                    "position": 1,
                    "bounds": [50, 0, 100, 50],
                    "unit_id": None,
                    "identity_confidence": 0.2,
                    "stars": None,
                },
            ]
        },
        timestamp=stamp,
    )
    assert (
        main(["crops", "--log", str(logs.log_path("204")), "--output", str(output)])
        == 0
    )
    manifest = json.loads((output / "crops.json").read_text())
    assert any(
        row["unit_id"] is None and row["label_source"] == "unlabelled"
        for row in manifest["crops"]
    )


def test_split_cli_keeps_whole_games_and_keyframes_out_of_training(tmp_path, capsys):
    import hashlib
    import json

    from tft_capture.training import main

    rows = []
    for game in range(8):
        for frame in range(2):
            name = f"{game}-{frame}.png"
            Image.new("RGB", (20, 20), (game * 25, frame * 80, 7)).save(tmp_path / name)
            rows.append(
                {
                    "id": name,
                    "file": name,
                    "sha256": hashlib.sha256(
                        (tmp_path / name).read_bytes()
                    ).hexdigest(),
                    "game_id": str(game),
                    "keyframe": str(frame),
                    "label": "Shen",
                    "unit_id": "shen",
                    "label_source": "unique_remaining_ownership",
                }
            )
    manifest = tmp_path / "crops.json"
    manifest.write_text(json.dumps({"v": 1, "crops": rows}))
    split = tmp_path / "split.json"
    assert main(["split", "--dataset", str(manifest), "--output", str(split)]) == 0
    first = json.loads(split.read_text())
    train_games = {row["game_id"] for row in first["train"]}
    heldout_games = {row["game_id"] for row in first["heldout"]}
    assert train_games and heldout_games and train_games.isdisjoint(heldout_games)
    assert main(["split", "--dataset", str(manifest), "--output", str(split)]) == 0
    assert json.loads(split.read_text()) == first


def _constant_onnx(directory, labels, choice):
    import json

    import numpy as np
    import pytest

    onnx = pytest.importorskip(
        "onnx", reason="Install the explicit train group for ONNX fixture qualification"
    )
    from onnx import TensorProto, helper, numpy_helper

    directory.mkdir()
    arrays = {
        "axes": np.array([1, 2, 3], dtype=np.int64),
        "expand_axes": np.array([1], dtype=np.int64),
        "zero": np.array(0, dtype=np.float32),
        "logits": np.array(
            [10 if label == choice else 0 for label in labels], dtype=np.float32
        ),
    }
    nodes = [
        helper.make_node("ReduceMean", ["image", "axes"], ["mean"], keepdims=0),
        helper.make_node("Unsqueeze", ["mean", "expand_axes"], ["column"]),
        helper.make_node("Mul", ["column", "zero"], ["zeros"]),
        helper.make_node("Add", ["zeros", "logits"], ["output"]),
    ]
    graph = helper.make_graph(
        nodes,
        "external-fixture",
        [
            helper.make_tensor_value_info(
                "image", TensorProto.FLOAT, ["batch", 3, 16, 16]
            )
        ],
        [
            helper.make_tensor_value_info(
                "output", TensorProto.FLOAT, ["batch", len(labels)]
            )
        ],
        [numpy_helper.from_array(array, name) for name, array in arrays.items()],
    )
    model = helper.make_model(
        graph, opset_imports=[helper.make_opsetid("", 18)], ir_version=10
    )
    onnx.save(model, directory / "unit_classifier.onnx")
    (directory / "unit_classifier.onnx.data").write_bytes(b"")
    (directory / "unit_classifier.json").write_text(
        json.dumps(
            {
                "set_number": 18,
                "engine": "unreal",
                "labels": labels,
                "input_size": 16,
                "mean": [0.485, 0.456, 0.406],
                "std": [0.229, 0.224, 0.225],
                "resize_mode": "letterbox",
                "architecture": "external-fixture",
            }
        )
    )


def test_comparison_cli_rejects_class_regression_despite_equal_overall_score(
    tmp_path, capsys
):
    import hashlib
    import json

    import numpy as np
    from tft_capture.model_validation import fingerprint
    from tft_capture.training import main

    _constant_onnx(tmp_path / "current", ["red", "blue"], "red")
    _constant_onnx(tmp_path / "candidate", ["red", "blue"], "blue")
    rows = []
    for label in ("red", "blue"):
        for index in range(20):
            filename = f"{label}-{index}.png"
            Image.fromarray(
                np.random.default_rng(index + (100 if label == "blue" else 0)).integers(
                    0, 255, (16, 16, 3), dtype=np.uint8
                )
            ).save(tmp_path / filename)
            rows.append(
                {
                    "id": filename,
                    "file": filename,
                    "sha256": hashlib.sha256(
                        (tmp_path / filename).read_bytes()
                    ).hexdigest(),
                    "game_id": f"heldout-{index % 10}",
                    "keyframe": filename,
                    "label": label,
                }
            )
    Image.new("RGB", (16, 16), "black").save(tmp_path / "train.png")
    train = {
        "id": "train",
        "file": "train.png",
        "sha256": hashlib.sha256((tmp_path / "train.png").read_bytes()).hexdigest(),
        "game_id": "train",
        "keyframe": "train",
        "label": "red",
    }
    split = {"v": 1, "train": [train], "heldout": rows}
    split["dataset_fingerprint"] = fingerprint(
        {key: split[key] for key in ("train", "heldout")}
    )
    (tmp_path / "split.json").write_text(json.dumps(split))
    report = tmp_path / "report.json"
    assert (
        main(
            [
                "compare",
                "--current",
                str(tmp_path / "current"),
                "--candidate",
                str(tmp_path / "candidate"),
                "--split",
                str(tmp_path / "split.json"),
                "--report",
                str(report),
            ]
        )
        == 2
    )
    result = json.loads(report.read_text())
    assert result["current_correct"] == result["candidate_correct"] == 20
    assert result["regressed_classes"] == ["red"]
    assert result["per_class"]["red"]["games"] == 10
    assert result["qualified"] is True and result["accepted"] is False


def test_training_cli_fine_tunes_current_cpu_model_without_promoting_unqualified_data(
    tmp_path, capsys
):
    import hashlib
    import json

    import pytest

    pytest.importorskip("torch", reason="Offline train group is explicit")
    from tft_capture.model_validation import fingerprint
    from tft_capture.training import main

    models = _models()
    rows = []
    for index in range(4):
        name = f"crop-{index}.png"
        Image.new("RGB", (64, 80), (index * 50, 40, 90)).save(tmp_path / name)
        rows.append(
            {
                "id": name,
                "file": name,
                "sha256": hashlib.sha256((tmp_path / name).read_bytes()).hexdigest(),
                "game_id": f"game-{index}",
                "keyframe": name,
                "label": "Lux",
            }
        )
    split = {"v": 1, "train": rows[:2], "heldout": rows[2:]}
    split["dataset_fingerprint"] = fingerprint(
        {key: split[key] for key in ("train", "heldout")}
    )
    (tmp_path / "split.json").write_text(json.dumps(split))
    candidate = tmp_path / "candidate"
    assert (
        main(
            [
                "train",
                "--current",
                str(models),
                "--split",
                str(tmp_path / "split.json"),
                "--output",
                str(candidate),
                "--epochs",
                "1",
                "--batch-size",
                "2",
            ]
        )
        == 0
    )
    metadata = json.loads((candidate / "unit_classifier.json").read_text())
    assert (
        metadata["labels"]
        == json.loads((models / "unit_classifier.json").read_text())["labels"]
    )
    assert metadata["training"]["device"] == "cpu"
    assert metadata["training"]["initial_logit_error"] < 0.0001
    assert metadata["training"]["dataset_fingerprint"] == split["dataset_fingerprint"]
    assert (candidate / "unit_classifier.onnx.data").stat().st_size > 1_000_000
    assert (candidate / "star_level_classifier.onnx.data").is_file()
    assert not (candidate / "accepted.json").exists()


def _models():
    import os

    import pytest

    root = Path(__file__).resolve().parents[2]
    choices = (
        [Path(os.environ["TFT_READER_TEST_MODELS"])]
        if "TFT_READER_TEST_MODELS" in os.environ
        else [
            root / "worktrees/model-cache",
            root / "worktrees/references/tft-coach/assets/models",
            root.parents[1] / "worktrees/references/tft-coach/assets/models",
        ]
    )
    for directory in choices:
        if (directory / "unit_classifier.onnx.data").is_file():
            return directory
    pytest.skip(
        "Pinned reader weights are external; prepare the model cache or set TFT_READER_TEST_MODELS"
    )


def test_accept_cli_recomputes_gate_and_preserves_pointer_for_missing_classes(
    tmp_path, capsys
):
    import hashlib
    import json

    from tft_capture.model_validation import fingerprint
    from tft_capture.training import main

    _constant_onnx(tmp_path / "current", ["red", "blue"], "red")
    _constant_onnx(tmp_path / "candidate", ["red", "blue"], "red")
    rows = []
    for index in range(2):
        name = f"crop{index}.png"
        Image.new("RGB", (16, 16), (index * 70, 10, 0)).save(tmp_path / name)
        rows.append(
            {
                "id": name,
                "file": name,
                "sha256": hashlib.sha256((tmp_path / name).read_bytes()).hexdigest(),
                "game_id": str(index),
                "keyframe": name,
                "label": "red",
            }
        )
    split = {"v": 1, "train": rows[:1], "heldout": rows[1:]}
    split["dataset_fingerprint"] = fingerprint(
        {key: split[key] for key in ("train", "heldout")}
    )
    (tmp_path / "split.json").write_text(json.dumps(split))
    pointer = tmp_path / "models.json"
    pointer.write_text('{"version":"last-good"}')
    report = tmp_path / "report.json"
    report.write_text('{"accepted":true}')
    assert (
        main(
            [
                "accept",
                "--current",
                str(tmp_path / "current"),
                "--candidate",
                str(tmp_path / "candidate"),
                "--split",
                str(tmp_path / "split.json"),
                "--report",
                str(report),
                "--pointer",
                str(pointer),
                "--cache",
                str(tmp_path / "cache"),
            ]
        )
        == 2
    )
    assert json.loads(pointer.read_text()) == {"version": "last-good"}
    assert json.loads(report.read_text())["unqualified_classes"] == ["red", "blue"]
    assert not (tmp_path / "cache").exists()


def test_reader_retains_tall_maokai_and_all_nine_slots_without_guessing_projection(
    tmp_path,
):
    import json
    import shutil

    from PIL import ImageDraw
    from tft_capture.board_reader import BoardReader

    _constant_onnx(tmp_path / "units", ["Maokai", "_empty"], "Maokai")
    _constant_onnx(tmp_path / "stars", ["1", "2", "3"], "1")
    for suffix in (".json", ".onnx", ".onnx.data"):
        shutil.copy2(
            tmp_path / "stars" / ("unit_classifier" + suffix),
            tmp_path / "units" / ("star_level_classifier" + suffix),
        )
    frame = Image.new("RGB", (2560, 1440), "black")
    draw = ImageDraw.Draw(frame)
    draw.rectangle((1152, 300, 1265, 305), fill=(0, 255, 0))
    for slot in range(9):
        left = round(2560 * 0.183) + round(2560 * (0.748 - 0.183) * slot / 9) + 35
        draw.rectangle((left, 920, left + 79, 925), fill=(0, 255, 0))
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("205")
    reader = BoardReader(
        tmp_path / "units", set_number=18, unit_ids={"Maokai": "maokai"}
    )
    pipeline = CapturePipeline(
        "205", ocr=LabelOCR(), sink=logs, visual_reader=reader, own_player_name="Vanko1"
    )
    observed = pipeline.tick(frame)["fields"]["board_observations"]["value"]
    tall = [row for row in observed if row["zone"] == "board"]
    assert (
        len(tall) == 1
        and tall[0]["unit_id"] == "maokai"
        and tall[0]["position"] is None
    )
    assert {row["position"] for row in observed if row["zone"] == "bench"} == set(
        range(9)
    )
    calibration = tmp_path / "calibration.json"
    calibration.write_text(json.dumps({"foot_offsets": {"maokai": 2.5}}))
    calibrated = BoardReader(
        tmp_path / "units",
        set_number=18,
        unit_ids={"Maokai": "maokai"},
        foot_offsets=calibration,
    )
    pipeline = CapturePipeline(
        "205",
        ocr=LabelOCR(),
        sink=logs,
        visual_reader=calibrated,
        own_player_name="Vanko1",
    )
    observed = pipeline.tick(frame)["fields"]["board_observations"]["value"]
    assert next(row for row in observed if row["zone"] == "board")["position"] == 3
    assert (
        calibrated.read(
            frame, regions={"board": (0, 0, 2560, 1440)}, own_view=False
        ).fields
        == {}
    )
    assert (
        calibrated.read(
            frame, regions={"board": (0, 0, 2560, 1440)}, own_view=None
        ).fields
        == {}
    )


def test_prepare_models_cli_verifies_all_external_weights_before_replacing_cache(
    tmp_path, capsys
):
    import hashlib
    import json

    import httpx
    from tft_capture.training import main

    files = {
        stem + suffix: (stem + suffix).encode()
        for stem in ("unit_classifier", "star_level_classifier")
        for suffix in (".json", ".onnx", ".onnx.data")
    }
    pointer = tmp_path / "models.json"
    pointer.write_text(
        json.dumps(
            {
                "v": 1,
                "version": "pinned-fixture",
                "base_url": "https://models.invalid/pinned",
                "files": {
                    name: hashlib.sha256(data).hexdigest()
                    for name, data in files.items()
                },
            }
        )
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, content=files[request.url.path.rsplit("/", 1)[1]]
        )
    )
    cache = tmp_path / "cache"
    assert (
        main(
            ["prepare-models", "--pointer", str(pointer), "--cache", str(cache)],
            transport=transport,
        )
        == 0
    )
    assert {path.name for path in (cache / "pinned-fixture").iterdir()} == set(files)
    assert (cache / "pinned-fixture/unit_classifier.onnx.data").read_bytes() == files[
        "unit_classifier.onnx.data"
    ]


def test_reader_data_mapping_collapses_lux_forms_until_positive_form_evidence(tmp_path):
    import shutil

    from PIL import ImageDraw
    from tft_capture.board_reader import BoardReader
    from tft_data.models import DataSnapshot, Entity, TaggedValue

    _constant_onnx(tmp_path / "units", ["Lux", "_empty"], "Lux")
    _constant_onnx(tmp_path / "stars", ["1", "2", "3"], "1")
    for suffix in (".json", ".onnx", ".onnx.data"):
        shutil.copy2(
            tmp_path / "stars" / ("unit_classifier" + suffix),
            tmp_path / "units" / ("star_level_classifier" + suffix),
        )
    data = DataSnapshot(
        "fixture",
        "16.20",
        18,
        {},
        {"board_reader_identity_min": TaggedValue(0.6, "default")},
        entities={
            "DA_Lux18_Base": Entity("DA_Lux18_Base", "unit", "Лукс", cost=4),
            "DA_18_Lux_Coven": Entity(
                "DA_18_Lux_Coven",
                "unit_form",
                "Лукс (Coven)",
                cost=4,
                values={"canonical_id": TaggedValue("DA_Lux18_Base", "cdragon")},
            ),
        },
    )
    reader = BoardReader.from_data(tmp_path / "units", data)
    frame = Image.new("RGB", (2560, 1440), "black")
    ImageDraw.Draw(frame).rectangle((1152, 500, 1231, 505), fill=(0, 255, 0))
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("206")
    snapshot = CapturePipeline(
        "206", ocr=LabelOCR(), sink=logs, visual_reader=reader, own_player_name="Vanko1"
    ).tick(frame)
    assert (
        snapshot["fields"]["board_observations"]["value"][0]["unit_id"]
        == "DA_Lux18_Base"
    )
    assert reader.identity_min == 0.6


def test_comparison_cli_does_not_count_duplicate_pixels_as_independent_evidence(
    tmp_path, capsys
):
    import hashlib
    import json

    from tft_capture.model_validation import fingerprint
    from tft_capture.training import main

    _constant_onnx(tmp_path / "current", ["red"], "red")
    _constant_onnx(tmp_path / "candidate", ["red"], "red")
    Image.new("RGB", (16, 16), "red").save(tmp_path / "same.png")
    digest = hashlib.sha256((tmp_path / "same.png").read_bytes()).hexdigest()
    heldout = [
        {
            "id": str(index),
            "file": "same.png",
            "sha256": digest,
            "game_id": str(index % 10),
            "keyframe": str(index),
            "label": "red",
        }
        for index in range(20)
    ]
    Image.new("RGB", (16, 16), "green").save(tmp_path / "train.png")
    train = {
        "id": "train",
        "file": "train.png",
        "sha256": hashlib.sha256((tmp_path / "train.png").read_bytes()).hexdigest(),
        "game_id": "train",
        "keyframe": "train",
        "label": "red",
    }
    split = {"v": 1, "train": [train], "heldout": heldout}
    split["dataset_fingerprint"] = fingerprint(
        {key: split[key] for key in ("train", "heldout")}
    )
    (tmp_path / "split.json").write_text(json.dumps(split))
    report = tmp_path / "report.json"
    assert (
        main(
            [
                "compare",
                "--current",
                str(tmp_path / "current"),
                "--candidate",
                str(tmp_path / "candidate"),
                "--split",
                str(tmp_path / "split.json"),
                "--report",
                str(report),
            ]
        )
        == 2
    )
    result = json.loads(report.read_text())
    assert result["count"] == 1
    assert result["per_class"]["red"]["count"] == 1
    assert result["qualified"] is False


def test_high_confidence_reader_preserves_disputed_tracking_as_unpositioned_partial_units(
    tmp_path,
):
    from tft_capture.vision import VisionRead

    class RecordedVisual:
        source = "recorded-external-classifier"
        identity_min = 0.55

        def read(self, image, *, regions, own_view):
            return VisionRead(
                {
                    "board_observations": [
                        {
                            "zone": "board",
                            "position": 5,
                            "bounds": [0, 0, 50, 50],
                            "unit_id": "ashe",
                            "label": "Ashe",
                            "identity_confidence": 0.95,
                            "stars": 1,
                            "items": ["cape"],
                        }
                    ]
                },
                self.source,
                0.95,
            )

    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("207")
    logs.append_event("ownership", {"copies": {"shen": 3}, "complete": True})
    snapshot = CapturePipeline(
        "207",
        ocr=LabelOCR(),
        sink=logs,
        visual_reader=RecordedVisual(),
        own_player_name="Vanko1",
        tracking_events=logs.read_events("207"),
        regions={"scouted": (0, 0, 1, 1), "board": (0, 0, 1, 1)},
    ).tick(Image.new("RGB", (100, 100), "white"))
    assert snapshot["fields"]["tracked_units"]["value"] == [
        {"unit_id": "shen", "copies": 3, "stars": 2, "items": None, "position": None}
    ]
    event = next(
        event
        for event in logs.read_events("207")
        if event["kind"] == "reader_disagreement"
    )
    assert event["payload"]["disagreements"][0]["chosen_unit_id"] == "ashe"
    assert "board" not in snapshot["fields"]


def test_accept_cli_promotes_only_recomputed_complete_heldout_bundle(tmp_path, capsys):
    import hashlib
    import json
    import shutil

    import numpy as np
    from tft_capture.board_reader import BoardReader
    from tft_capture.model_validation import fingerprint
    from tft_capture.training import main

    _constant_onnx(tmp_path / "current", ["red", "blue"], "red")
    _constant_onnx(tmp_path / "candidate", ["red", "blue"], "red")
    _constant_onnx(tmp_path / "stars", ["1", "2", "3"], "1")
    for suffix in (".json", ".onnx", ".onnx.data"):
        shutil.copy2(
            tmp_path / "stars" / ("unit_classifier" + suffix),
            tmp_path / "candidate" / ("star_level_classifier" + suffix),
        )
    rows = []
    for label in ("red", "blue"):
        for index in range(20):
            name = f"{label}-{index}.png"
            Image.fromarray(
                np.random.default_rng(index + (100 if label == "blue" else 0)).integers(
                    0, 255, (16, 16, 3), dtype=np.uint8
                )
            ).save(tmp_path / name)
            rows.append(
                {
                    "id": name,
                    "file": name,
                    "sha256": hashlib.sha256(
                        (tmp_path / name).read_bytes()
                    ).hexdigest(),
                    "game_id": f"heldout-{index % 10}",
                    "keyframe": name,
                    "label": label,
                    "label_source": "owner_reviewed",
                }
            )
    Image.new("RGB", (16, 16), "black").save(tmp_path / "train.png")
    train = {
        "id": "train",
        "file": "train.png",
        "sha256": hashlib.sha256((tmp_path / "train.png").read_bytes()).hexdigest(),
        "game_id": "train",
        "keyframe": "train",
        "label": "red",
    }
    split = {"v": 1, "train": [train], "heldout": rows}
    split["dataset_fingerprint"] = fingerprint(
        {key: split[key] for key in ("train", "heldout")}
    )
    (tmp_path / "split.json").write_text(json.dumps(split))
    pointer = tmp_path / "models.json"
    pointer.write_text('{"version":"last-good"}')
    assert (
        main(
            [
                "accept",
                "--current",
                str(tmp_path / "current"),
                "--candidate",
                str(tmp_path / "candidate"),
                "--split",
                str(tmp_path / "split.json"),
                "--report",
                str(tmp_path / "report.json"),
                "--pointer",
                str(pointer),
                "--cache",
                str(tmp_path / "cache"),
            ]
        )
        == 0
    )
    manifest = json.loads(pointer.read_text())
    assert len(manifest["files"]) == 6
    assert manifest["dataset_fingerprint"] == split["dataset_fingerprint"]
    assert all(
        hashlib.sha256(
            (tmp_path / "cache" / manifest["version"] / name).read_bytes()
        ).hexdigest()
        == digest
        for name, digest in manifest["files"].items()
    )
    reader = BoardReader.from_version(
        tmp_path / "cache", pointer=pointer, set_number=18, unit_ids={}
    )
    assert reader.model_version == manifest["version"]


def test_reader_respects_explicit_capture_region_boundaries(tmp_path):
    from tft_capture.board_reader import BoardReader

    root = Path(__file__).resolve().parents[2]
    reader = BoardReader(_models(), set_number=18, unit_ids={"Karma": "karma"})
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("208")
    snapshot = CapturePipeline(
        "208",
        ocr=LabelOCR(),
        sink=logs,
        visual_reader=reader,
        own_player_name="Vanko1",
        regions={"scouted": (0, 0, 1, 1), "board": (0.15, 0.09, 0.855, 0.6)},
    ).tick(Image.open(root / "probe/screenshots/2026-10-04/02-shop-with-wisp-2-3.jpg"))
    assert not any(
        row["zone"] == "bench"
        for row in snapshot["fields"]["board_observations"]["value"]
    )


def test_inventory_reader_omits_competing_item_templates(tmp_path):
    import numpy as np
    from tft_capture.board_reader import BoardReader
    from tft_capture.reader_assets import TemplateBank

    icon = np.random.default_rng(38).integers(0, 255, (36, 36, 3), dtype=np.uint8)
    bank = TemplateBank({"cape": icon, "different-component": icon.copy()})
    reader = BoardReader(_models(), set_number=18, unit_ids={}, templates=bank)
    frame = Image.new("RGB", (50, 200), "black")
    frame.paste(Image.fromarray(icon[:, :, ::-1]), (7, 20))
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("209")
    snapshot = CapturePipeline(
        "209",
        ocr=LabelOCR(),
        sink=logs,
        visual_reader=reader,
        own_player_name="Vanko1",
        regions={
            "scouted": (0, 0, 1, 1),
            "board": (0, 0, 1, 1),
            "item_bench": (0, 0, 1, 1),
        },
    ).tick(frame)
    assert snapshot["fields"]["item_bench_observations"]["value"] == {
        "items": [],
        "complete": False,
    }
