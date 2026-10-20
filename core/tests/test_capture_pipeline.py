from datetime import datetime, timedelta, timezone

from PIL import Image

from tft_capture.pipeline import CapturePipeline
from tft_capture.ocr import TextLine
from tft_core.storage import SessionStore


class RecordedOCR:
    """Recorded output at the external OCR boundary, not an internal reader stub."""
    source = "recorded-ocr"
    def __init__(self, output):
        self.output = output
    def read(self, image, *, region):
        return self.output.get(region, [])


def test_unchanged_pixels_confirm_known_fields_and_missing_frame_goes_stale(tmp_path):
    start = datetime(2026, 10, 6, tzinfo=timezone.utc)
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("123")
    ocr = RecordedOCR({"gold": [TextLine("27", confidence=0.93)]})
    pipeline = CapturePipeline("123", ocr=ocr, sink=logs, regions={"gold": (0, 0, 1, 1)})
    frame = Image.new("RGB", (20, 20), "white")
    first = pipeline.tick(frame, timestamp=start)
    assert first["fields"]["gold"]["value"] == 27
    from tft_engine.models import GameSnapshot
    assert GameSnapshot.from_dict(first).field("gold") == 27
    repeated = pipeline.tick(frame, timestamp=start + timedelta(seconds=3))
    assert repeated["fields"]["gold"] == {"value": 27, "read_at": (start + timedelta(seconds=3)).isoformat(), "source": "recorded-ocr", "confidence": 0.93}
    missing = pipeline.tick(None, timestamp=start + timedelta(seconds=6))
    assert missing["fields"]["gold"]["read_at"] == repeated["fields"]["gold"]["read_at"]
    assert missing["stale_fields"] == ["gold"]
    pipeline.tick(frame, timestamp=start + timedelta(seconds=7))
    events = logs.read_events("123")
    assert [event["kind"] for event in events].count("capture_gap") == 1
    assert [event["payload"]["fields"]["gold"]["value"] for event in events if event["kind"] == "snapshot"] == [27, 27, 27, 27]


def test_shop_and_wisp_are_locale_matched_and_logged_with_keyframes(tmp_path):
    from tft_capture.ocr import NameCatalog
    start = datetime(2026, 10, 6, tzinfo=timezone.utc)
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("124")
    output = {
        "shop": [
            TextLine("Shen", box=(0.01, 0.82, 0.12, 0.96)), TextLine("2", box=(0.16, 0.82, 0.19, 0.96)),
            TextLine("Master Yi", box=(0.21, 0.82, 0.35, 0.96)), TextLine("3", box=(0.36, 0.82, 0.39, 0.96)),
            TextLine("Veigar", box=(0.41, 0.82, 0.54, 0.96)), TextLine("1", box=(0.56, 0.82, 0.59, 0.96)),
            TextLine("Ornn", box=(0.61, 0.82, 0.75, 0.96)), TextLine("1", box=(0.76, 0.82, 0.79, 0.96)),
            TextLine("Forest Twins", box=(0.81, 0.82, 0.95, 0.96)), TextLine("4", box=(0.96, 0.82, 0.99, 0.96)),
            TextLine("Gain 2 copies of a 2-cost champion you don't have.", box=(0.81, 0.2, 0.99, 0.7)),
        ]
    }
    catalog = NameCatalog({"units": {"shen": "Shen", "yi": "Master Yi", "veigar": "Veigar", "ornn": "Ornn"}, "wisps": {"forest": "Forest Twins"}})
    pipeline = CapturePipeline("124", ocr=RecordedOCR(output), sink=logs, catalog=catalog, regions={"shop": (0, 0, 1, 1)})
    snapshot = pipeline.tick(Image.new("RGB", (100, 50), "white"), timestamp=start)
    assert snapshot["fields"]["wisp_complete"]["value"] is True
    assert snapshot["fields"]["slot_count"]["value"] == 4
    assert [slot["unit_id"] for slot in snapshot["fields"]["shop"]["value"]] == ["shen", "yi", "veigar", "ornn"]
    assert snapshot["fields"]["wisp"]["value"] == {"wisp_id": "forest", "slot": 4, "cost": 4, "text": "Gain 2 copies of a 2-cost champion you don't have."}
    assert any(event["kind"] == "shop_offer" for event in logs.read_events("124"))
    assert any(event["kind"] == "keyframe" for event in logs.read_events("124"))


def test_hud_traits_and_sightings_keep_raw_opponents_in_silent_logs(tmp_path):
    from tft_capture.ocr import NameCatalog
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("125")
    output = {
        "stage": [TextLine("2-3")], "timer": [TextLine("29")],
        "level": [TextLine("Lvl. 4")], "xp": [TextLine("4/10")],
        "odds": [TextLine("55% 30% 15% 0% 0%")], "streak": [TextLine("2")],
        "traits": [TextLine("Inferno 3", box=(0, 0.1, 1, 0.2)), TextLine("Defender 2", box=(0, 0.3, 1, 0.4)), TextLine("3+", box=(0, 0.8, 1, 0.9))],
        "scouted": [TextLine("Opponent Level 4")],
    }
    pipeline = CapturePipeline("125", ocr=RecordedOCR(output), sink=logs, catalog=NameCatalog({"traits": {"inferno": "Inferno", "defender": "Defender"}}), own_player_name="Owner", regions={key: (0, 0, 1, 1) for key in output})
    snapshot = pipeline.tick(Image.new("RGB", (100, 100), "white"))
    assert snapshot["round_id"] == "2-3"
    assert snapshot["fields"]["xp"]["value"] == 4
    assert snapshot["fields"]["shop_odds"]["value"] == [55, 30, 15, 0, 0]
    assert snapshot["fields"]["sighting"]["value"] == {"opponent_id": "Opponent", "round_id": "2-3", "level": 4, "traits": {"inferno": 3, "defender": 2}, "hidden_traits": 3}
    assert any(event["kind"] == "sighting" for event in logs.read_events("125"))
    assert logs.mode.value == "silent"


def test_transport_failure_and_replaced_window_resume_same_log(tmp_path):
    from tft_capture.windows import CapturedFrame, CaptureUnavailable
    from tft_capture.runner import CaptureRunner

    class WindowFrames:
        def __init__(self):
            self.frames = iter([CapturedFrame(Image.new("RGB", (20, 20), "white"), "window-1", "wgc"), CaptureUnavailable("TFT window closed"), CapturedFrame(Image.new("RGB", (20, 20), "white"), "window-2", "wgc")])
        def capture(self):
            value = next(self.frames)
            if isinstance(value, Exception):
                raise value
            return value

    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("126")
    pipeline = CapturePipeline("126", ocr=RecordedOCR({"gold": [TextLine("27")]}), sink=logs, regions={"gold": (0, 0, 1, 1)})
    runner = CaptureRunner(WindowFrames(), pipeline)
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    runner.step(timestamp=now)
    gap = runner.step(timestamp=now+timedelta(seconds=3))
    resumed = runner.step(timestamp=now+timedelta(seconds=4))
    assert gap["stale_fields"] == ["gold"]
    assert resumed["fields"]["gold"]["value"] == 27
    assert [e["kind"] for e in logs.read_events("126")].count("capture_gap") == 1
    assert any(e["kind"] == "capture_status" and "closed" in e["payload"].get("error", "") for e in logs.read_events("126"))


def test_capture_reads_ui_scale_and_preserves_centered_hud_on_wide_window(tmp_path):
    from tft_capture.layout import HudLayout
    config = tmp_path / "game.cfg"
    config.write_text("[HUD]\nGlobalScale=0.8\n[General]\nWindowMode=2\n")
    layout = HudLayout.from_config(config)
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("127")
    pipeline = CapturePipeline("127", ocr=RecordedOCR({"gold": [TextLine("27")]}), sink=logs, layout=layout)
    snapshot = pipeline.tick(Image.new("RGB", (3440, 1440), "white"))
    assert snapshot["fields"]["gold"]["value"] == 27
    assert snapshot["capture_layout"]["ui_scale"] == 0.8
    assert snapshot["capture_layout"]["window_mode"] == "borderless"
    assert snapshot["capture_layout"]["size"] == [3440, 1440]


def test_digit_templates_read_gold_through_capture_boundary(tmp_path):
    from PIL import ImageDraw, ImageFont
    from tft_capture.ocr import DigitTemplates
    font = ImageFont.load_default(size=24)
    templates = {}
    for digit in "0123456789":
        image = Image.new("L", (30, 32), 0)
        ImageDraw.Draw(image).text((1, 1), digit, font=font, fill=255)
        templates[digit] = image
    frame = Image.new("RGB", (60, 32), "black")
    ImageDraw.Draw(frame).text((1, 1), "27", font=font, fill="white")
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("128")
    pipeline = CapturePipeline("128", ocr=DigitTemplates(templates), sink=logs, regions={"gold": (0, 0, 1, 1)})
    snapshot = pipeline.tick(frame)
    assert snapshot["fields"]["gold"]["value"] == 27
    assert snapshot["fields"]["gold"]["source"] == "digit-templates"


def test_digit_templates_do_not_read_bright_blobs_as_a_minus_sign():
    from PIL import ImageDraw, ImageFont
    from tft_capture.ocr import DigitTemplates
    font = ImageFont.load_default(size=24)
    templates = {}
    for digit in "0123456789":
        image = Image.new("L", (30, 32), 0)
        ImageDraw.Draw(image).text((1, 1), digit, font=font, fill=255)
        templates[digit] = image
    minus = Image.new("L", (10, 4), 0)
    ImageDraw.Draw(minus).rectangle((2, 1, 7, 2), fill=255)
    templates["-"] = minus
    reader = DigitTemplates(templates)
    blob = Image.new("RGB", (40, 32), "black")
    ImageDraw.Draw(blob).rectangle((5, 3, 30, 28), fill="white")
    assert reader.read(blob, region="gold") == []
    signed = Image.new("RGB", (60, 32), "black")
    ImageDraw.Draw(signed).rectangle((2, 15, 9, 17), fill="white")
    ImageDraw.Draw(signed).text((14, 1), "4", font=font, fill="white")
    assert [line.text for line in reader.read(signed, region="streak")] == ["-4"]


def test_bundled_cpu_ocr_reads_gold_from_committed_probe_frame(tmp_path):
    from pathlib import Path
    from tft_capture.ocr import RapidOCRReader
    root = Path(__file__).resolve().parents[2]
    image = Image.open(root / "probe/screenshots/2026-10-04/02-shop-with-wisp-2-3.jpg")
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("129")
    pipeline = CapturePipeline("129", ocr=RapidOCRReader.from_bundled_models(), sink=logs,
        regions={"gold": (.529, .811, .556, .851)})
    snapshot = pipeline.tick(image)
    assert snapshot["fields"]["gold"]["value"] == 28
    assert snapshot["fields"]["gold"]["source"] == "rapidocr"


def test_confirmed_empty_slot_and_gold_delta_log_purchase_but_ambiguity_does_not(tmp_path):
    from tft_capture.ocr import NameCatalog
    from tft_capture.vision import VisionRead
    class RecordedVision:
        source = "recorded-vision"
        def __init__(self):
            self.empty = []
        def read(self, image, *, regions, own_view):
            return VisionRead({"shop_empty_slots": self.empty}, self.source, 1.0)
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("130")
    slots = [TextLine("Shen", box=(i*.2+.01, .82, i*.2+.13, .95)) for i in range(5)]
    costs = [TextLine("2", box=(i*.2+.16, .82, i*.2+.19, .95)) for i in range(5)]
    ocr = RecordedOCR({"gold": [TextLine("27")], "stage": [TextLine("2-3")], "shop": slots+costs})
    vision = RecordedVision()
    pipeline = CapturePipeline("130", ocr=ocr, sink=logs, catalog=NameCatalog({"units": {"shen": "Shen"}}), visual_reader=vision, regions={key: (0, 0, 1, 1) for key in ("gold", "stage", "shop", "board")})
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    pipeline.tick(Image.new("RGB", (100, 100), "white"), timestamp=now)
    ocr.output["gold"] = [TextLine("25")]
    ocr.output["shop"] = slots[1:]+costs[1:]
    vision.empty = [0]
    pipeline.tick(Image.new("RGB", (100, 100), "gray"), timestamp=now+timedelta(seconds=.25))
    purchases = [event for event in logs.read_events("130") if event["kind"] == "purchase"]
    assert purchases[0]["payload"] == {"unit_id": "shen", "slot": 0, "cost": 2, "copies": 1}
    # A gold delta alone does not identify another purchase.
    ocr.output["gold"] = [TextLine("23")]
    pipeline.tick(Image.new("RGB", (100, 100), "black"), timestamp=now+timedelta(seconds=.5))
    assert [event["kind"] for event in logs.read_events("130")].count("purchase") == 1


def test_scout_switch_never_confirms_opponent_units_as_own_board(tmp_path):
    from tft_capture.vision import VisionRead
    class RecordedVision:
        source = "recorded-vision"
        def read(self, image, *, regions, own_view):
            return VisionRead({"board": {"units": [{"unit_id": "shen", "stars": 1, "items": [], "position": 0}], "bench": []}} if own_view else {}, self.source, 1)
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("131")
    ocr = RecordedOCR({"scouted": [TextLine("Owner Level 4")]})
    pipeline = CapturePipeline("131", ocr=ocr, sink=logs, visual_reader=RecordedVision(), own_player_name="Owner", regions={"scouted": (0, 0, 1, 1), "board": (0, 0, 1, 1)})
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    pipeline.tick(Image.new("RGB", (100, 100), "white"), timestamp=now)
    previous = pipeline.tick(Image.new("RGB", (100, 100), "gray"), timestamp=now+timedelta(seconds=.25))
    ocr.output["scouted"] = [TextLine("Opponent Level 6")]
    scouted = pipeline.tick(Image.new("RGB", (100, 100), "black"), timestamp=now+timedelta(seconds=.5))
    assert scouted["fields"]["board"]["read_at"] == previous["fields"]["board"]["read_at"]


def test_two_confirmed_rolls_raise_shop_cadence_then_timeout(tmp_path):
    from tft_capture.ocr import NameCatalog
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("132")
    def shop(name):
        return [line for i in range(5) for line in (TextLine(name, box=(i*.2+.01, .82, i*.2+.12, .95)), TextLine("2", box=(i*.2+.16, .82, i*.2+.19, .95)))]
    ocr = RecordedOCR({"gold": [TextLine("20")], "stage": [TextLine("2-3")], "shop": shop("Shen")})
    pipeline = CapturePipeline("132", ocr=ocr, sink=logs, catalog=NameCatalog({"units": {"shen": "Shen", "yi": "Master Yi"}}), regions={key: (0, 0, 1, 1) for key in ocr.output})
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    pipeline.tick(Image.new("RGB", (100, 100), "white"), timestamp=now)
    assert pipeline.poll_interval == .25
    ocr.output.update(gold=[TextLine("18")], shop=shop("Master Yi"))
    pipeline.tick(Image.new("RGB", (100, 100), "gray"), timestamp=now+timedelta(seconds=.8))
    ocr.output.update(gold=[TextLine("16")], shop=shop("Shen"))
    rolling = pipeline.tick(Image.new("RGB", (100, 100), "black"), timestamp=now+timedelta(seconds=1.6))
    assert rolling["roll_down"] is True
    assert pipeline.poll_interval == 1/15
    normal = pipeline.tick(Image.new("RGB", (100, 100), "black"), timestamp=now+timedelta(seconds=5))
    assert normal["roll_down"] is False
    assert [event["kind"] for event in logs.read_events("132")].count("roll") == 2


def test_own_trait_panel_is_not_logged_as_an_opponent_sighting(tmp_path):
    from tft_capture.ocr import NameCatalog
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("133")
    output = {"stage": [TextLine("2-3")], "scouted": [TextLine("Owner Level 4")],
              "traits": [TextLine("Inferno 3"), TextLine("0+")]}
    pipeline = CapturePipeline("133", ocr=RecordedOCR(output), sink=logs,
        own_player_name="Owner", catalog=NameCatalog({"traits": {"inferno": "Inferno"}}),
        regions={key: (0, 0, 1, 1) for key in output})
    snapshot = pipeline.tick(Image.new("RGB", (100, 100), "white"))
    assert "sighting" not in snapshot["fields"]
    assert not any(event["kind"] == "sighting" for event in logs.read_events("133"))


def test_purchase_during_fast_shop_sampling_uses_recent_confirmed_round(tmp_path):
    from tft_capture.ocr import NameCatalog
    from tft_capture.vision import VisionRead
    class RecordedVision:
        source = "recorded-vision"
        def read(self, image, *, regions, own_view):
            return VisionRead({"shop_empty_slots": [0] if image.getpixel((0, 0)) == (0, 0, 0) else []}, self.source, 1)
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("134")
    slots = [TextLine("Shen", box=(i*.2+.01, .82, i*.2+.13, .95)) for i in range(5)]
    costs = [TextLine("2", box=(i*.2+.16, .82, i*.2+.19, .95)) for i in range(5)]
    ocr = RecordedOCR({"gold": [TextLine("27")], "stage": [TextLine("2-3")], "shop": slots+costs})
    pipeline = CapturePipeline("134", ocr=ocr, sink=logs, catalog=NameCatalog({"units": {"shen": "Shen"}}),
        visual_reader=RecordedVision(), regions={key: (0, 0, 1, 1) for key in ocr.output})
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    pipeline.tick(Image.new("RGB", (100, 100), "white"), timestamp=now)
    pipeline.start_roll_down(timestamp=now)
    ocr.output.update(gold=[TextLine("25")], shop=slots[1:]+costs[1:])
    snapshot = pipeline.tick(Image.new("RGB", (100, 100), "black"), timestamp=now+timedelta(seconds=1/15))
    assert snapshot["fields"]["round"]["read_at"] == now.isoformat()
    assert [event["kind"] for event in logs.read_events("134")].count("purchase") == 1


def test_unchanged_own_board_confirms_reader_fields_without_repeating_vision(tmp_path):
    from tft_capture.vision import VisionRead
    class RecordedVision:
        source = "recorded-vision"
        calls = 0
        def read(self, image, *, regions, own_view):
            self.calls += 1
            return VisionRead({"board": {"units": [{"unit_id": "shen", "stars": 1, "items": [], "position": 0}], "bench": []}}, self.source, .9)
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("135")
    reader = RecordedVision()
    pipeline = CapturePipeline("135", ocr=RecordedOCR({"scouted": [TextLine("Owner Level 4")]}), sink=logs,
        visual_reader=reader, own_player_name="Owner", regions={"scouted": (0, 0, 1, 1), "board": (0, 0, 1, 1)})
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    frame = Image.new("RGB", (100, 100), "white")
    pipeline.tick(frame, timestamp=now)
    repeated = pipeline.tick(frame, timestamp=now+timedelta(seconds=3))
    assert reader.calls == 1
    assert repeated["fields"]["board"]["read_at"] == repeated["captured_at"]
    assert repeated["fields"]["board"]["source"] == "recorded-vision"
    assert repeated["fields"]["board"]["confidence"] == .9
    missing = pipeline.tick(None, timestamp=now+timedelta(seconds=6))
    assert "board" in missing["stale_fields"]


def test_unreadable_first_round_reports_actionable_calibration_status(tmp_path):
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("136")
    pipeline = CapturePipeline("136", ocr=RecordedOCR({}), sink=logs, regions={"gold": (0, 0, 1, 1)})
    pipeline.tick(Image.new("RGB", (100, 100), "white"))
    assert pipeline.finish_calibration_round() is False
    event = [event for event in logs.read_events("136") if event["kind"] == "calibration_status"][-1]
    assert event["payload"]["state"] == "unreadable"
    assert "UI scale" in event["payload"]["error"]
    assert event["payload"]["layout"]["size"] == [100, 100]


def test_two_empty_slots_and_two_gold_spent_remain_ambiguous(tmp_path):
    from tft_capture.ocr import NameCatalog
    from tft_capture.vision import VisionRead
    class RecordedVision:
        source = "recorded-vision"
        def read(self, image, *, regions, own_view):
            return VisionRead({"shop_empty_slots": [0, 1] if image.getpixel((0, 0)) == (0, 0, 0) else []}, self.source, 1)
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("137")
    slots = [TextLine("Shen", box=(i*.2+.01, .82, i*.2+.13, .95)) for i in range(5)]
    costs = [TextLine("1", box=(i*.2+.16, .82, i*.2+.19, .95)) for i in range(5)]
    ocr = RecordedOCR({"gold": [TextLine("27")], "stage": [TextLine("2-3")], "shop": slots+costs})
    pipeline = CapturePipeline("137", ocr=ocr, sink=logs, catalog=NameCatalog({"units": {"shen": "Shen"}}),
        visual_reader=RecordedVision(), regions={key: (0, 0, 1, 1) for key in ocr.output})
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    pipeline.tick(Image.new("RGB", (100, 100), "white"), timestamp=now)
    ocr.output.update(gold=[TextLine("25")], shop=slots[2:]+costs[2:])
    pipeline.tick(Image.new("RGB", (100, 100), "black"), timestamp=now+timedelta(seconds=.25))
    kinds = [event["kind"] for event in logs.read_events("137")]
    assert "roll" not in kinds
    assert "purchase" not in kinds
    assert "tracking_ambiguity" in kinds


def test_positive_empty_shop_does_not_require_invented_ocr_text(tmp_path):
    from tft_capture.vision import VisionRead
    class RecordedVision:
        source = "recorded-vision"
        def read(self, image, *, regions, own_view):
            return VisionRead({"shop_empty_slots": [0, 1, 2, 3, 4]}, self.source, .9)
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("138")
    pipeline = CapturePipeline("138", ocr=RecordedOCR({}), sink=logs,
        visual_reader=RecordedVision(), regions={"shop": (0, 0, 1, 1)})
    snapshot = pipeline.tick(Image.new("RGB", (100, 100), "black"))
    assert snapshot["fields"]["shop"]["value"] == [{"slot": i, "unit_id": None, "cost": None, "traits": []} for i in range(5)]
    assert snapshot["fields"]["shop"]["source"] == "recorded-vision"
    assert snapshot["fields"]["shop"]["confidence"] == .9


def test_roll_down_field_is_certified_by_current_shop_reads_and_keeps_age_on_loss(tmp_path):
    from datetime import datetime,UTC,timedelta
    from PIL import Image
    from tft_capture.pipeline import CapturePipeline
    from tft_capture.ocr import TextLine
    from tft_capture.ocr import NameCatalog
    from tft_core.storage import SessionStore
    class ShopOCR:
        source='external-recorded-shop'
        def read(self,image,*,region):
            return [line for slot in range(5) for line in (TextLine('Alpha',box=(slot*.2+.01,.82,slot*.2+.12,.96)),TextLine('1',box=(slot*.2+.16,.82,slot*.2+.19,.96)))] if region=='shop' else []
    logs=SessionStore(tmp_path/'app',tmp_path/'config',live_installed=False);logs.start_game('123')
    now=datetime(2026,10,13,tzinfo=UTC)
    pipeline=CapturePipeline('123',sink=logs,ocr=ShopOCR(),catalog=NameCatalog({'units':{'a':'Alpha'}}),regions={'shop':(0,0,1,1)})
    pipeline.start_roll_down(gold_floor=10,timestamp=now)
    first=pipeline.tick(Image.new('RGB',(100,50)),timestamp=now)
    assert first['fields']['roll_down']['value'] is True
    assert first['fields']['roll_down_floor']['value']==10
    assert first['fields']['roll_down']['read_at']==now.isoformat()
    lost=pipeline.tick(None,timestamp=now+timedelta(seconds=1))
    assert lost['fields']['roll_down']['read_at']==first['fields']['roll_down']['read_at']


STANDALONE_SETTINGS = (";METADATA=(Diff=true, UseCommands=true)\n"
    "[/Script/TFTSettings.TFTUserSettings]\nResolutionSizeX=2560\nResolutionSizeY=1440\nFullscreenMode={mode}\n"
    "[/Script/TFTDevice.TFTDeviceSettings]\nClientConfig=(Name=\"a\",Value=\"1\")\nClientConfig=(Name=\"b\",Value=\"2\")\n")
MEASURED_HUD = ('format = "tft-assistant-measured-hud/1"\nclient_settings = "GameUserSettings.ini"\n'
    '[hud_scale]\nvalue = 1.0\nmeasured_at = "2026-10-20"\nclient_size = [2560, 1440]\n'
    'method = "bottom HUD text boxes match the probe reference frames"\n')


def test_standalone_client_layout_uses_the_measured_hud_scale(tmp_path):
    import pytest
    from tft_capture.layout import HudLayout
    (tmp_path/"GameUserSettings.ini").write_text(STANDALONE_SETTINGS.format(mode=2))
    record = tmp_path/"measured-hud.toml"
    record.write_text(MEASURED_HUD)
    layout = HudLayout.from_config(record)
    assert (layout.ui_scale, layout.window_mode, layout.scale_source) == (1.0, "windowed", "measured")
    (tmp_path/"GameUserSettings.ini").write_text(STANDALONE_SETTINGS.format(mode=1))
    changed = HudLayout.from_config(record)
    assert changed.window_mode == "borderless"
    assert changed.config_sha256 != layout.config_sha256
    with pytest.raises(ValueError, match="measured HUD"):
        HudLayout.from_config(tmp_path/"GameUserSettings.ini")


def test_measured_hud_record_rejects_incomplete_or_conflicting_evidence(tmp_path):
    import pytest
    from tft_capture.layout import HudLayout
    (tmp_path/"GameUserSettings.ini").write_text(STANDALONE_SETTINGS.format(mode=2))
    (tmp_path/"game.cfg").write_text("[HUD]\nGlobalScale=0.8\n[General]\nWindowMode=2\n")
    record = tmp_path/"measured-hud.toml"
    for text in (MEASURED_HUD.replace('method = "bottom HUD text boxes match the probe reference frames"\n', ''),
                 MEASURED_HUD + 'guess = true\n',
                 MEASURED_HUD.replace('value = 1.0', 'value = "1.0"'),
                 MEASURED_HUD.replace('client_size = [2560, 1440]', 'client_size = [2560]'),
                 MEASURED_HUD.replace('GameUserSettings.ini', 'game.cfg'),
                 MEASURED_HUD.replace('GameUserSettings.ini', 'missing.ini')):
        record.write_text(text)
        with pytest.raises((ValueError, OSError)):
            HudLayout.from_config(record)


ROUND_TYPES = {"2-1": "carousel", "2-2": "combat", "2-3": "combat", "2-7": "pve"}


def enemy_side_pipeline(tmp_path, game_id, output):
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game(game_id)
    regions = {name: (0, 0, 1, 1) for name in ("stage", "timer", "scouted", "board")}
    return CapturePipeline(game_id, ocr=RecordedOCR(output), sink=logs, regions=regions,
                           own_player_name="Owner", round_types=ROUND_TYPES)


def enemy_side_frame(tick, red):
    from PIL import ImageDraw
    frame = Image.new("RGB", (100, 100), "black")
    frame.putpixel((tick % 100, 99), (90, 90, 90))
    if red:
        ImageDraw.Draw(frame).rectangle((10, 10, 60, 14), fill=(220, 30, 30))
    return frame


def test_enemy_side_health_bars_mark_combat_and_first_countdown_marks_planning(tmp_path):
    output = {"scouted": [TextLine("Owner Level 4")]}
    pipeline = enemy_side_pipeline(tmp_path, "140", output)
    start = datetime(2026, 10, 20, tzinfo=timezone.utc)
    phases = []
    for tick, (round_id, timer, red) in enumerate([("2-1", 20, False), ("2-2", 30, False), ("2-2", 10, False),
                                                   ("2-2", 30, True), ("2-2", 20, False), ("2-3", 30, True)]):
        output.update(stage=[TextLine(round_id)], timer=[TextLine(str(timer))])
        snapshot = pipeline.tick(enemy_side_frame(tick, red), timestamp=start + timedelta(seconds=3 * tick))
        phases.append(snapshot["phase"])
    # Carousel round, planning, planning, combat, enemies gone in combat, enemies on the new round's planning.
    assert phases == ["unknown", "planning", "planning", "combat", "unknown", "combat"]
    assert snapshot["fields"]["phase"]["source"] == "enemy-side-bars"


def test_enemy_side_phase_is_unavailable_without_own_view_pvp_round_or_observed_round_start(tmp_path):
    output = {"scouted": [TextLine("Owner Level 4")], "stage": [TextLine("2-2")], "timer": [TextLine("15")]}
    pipeline = enemy_side_pipeline(tmp_path, "141", output)
    start = datetime(2026, 10, 20, tzinfo=timezone.utc)
    # Attached mid-round: the first countdown was not observed.
    assert pipeline.tick(enemy_side_frame(0, False), timestamp=start)["phase"] == "unknown"
    output.update(stage=[TextLine("2-3")], timer=[TextLine("30")])
    assert pipeline.tick(enemy_side_frame(1, False), timestamp=start + timedelta(seconds=3))["phase"] == "planning"
    pipeline.tick(None, timestamp=start + timedelta(seconds=6))
    output.update(timer=[TextLine("20")])
    # A capture gap loses the countdown history for the round.
    assert pipeline.tick(enemy_side_frame(2, False), timestamp=start + timedelta(seconds=9))["phase"] == "unknown"
    output.update(stage=[TextLine("2-7")], timer=[TextLine("30")])
    assert pipeline.tick(enemy_side_frame(3, True), timestamp=start + timedelta(seconds=12))["phase"] == "unknown"
    output.update(stage=[TextLine("2-2")], scouted=[TextLine("Opponent Level 4")])
    assert pipeline.tick(enemy_side_frame(4, True), timestamp=start + timedelta(seconds=15))["phase"] == "unknown"
