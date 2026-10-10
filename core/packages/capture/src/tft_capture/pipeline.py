"""Automatic capture to JSON-safe snapshots and durable game-log events.

The OCR object is the external recognition boundary. Failed reads retain the
last known value and timestamp. Unchanged successfully captured pixels confirm
freshness without changing the original source or confidence.
"""
import hashlib
from copy import deepcopy
from uuid import uuid4
import re
from datetime import datetime, timezone
from typing import Protocol

from PIL import Image

from tft_capture.ocr import NameCatalog, TextLine
from tft_capture.layout import HudLayout
from tft_capture.tracking import PurchaseTracker
from tft_capture.vision import VisionRead, VisualReader


class OCR(Protocol):
    source: str
    def read(self, image: Image.Image, *, region: str) -> list[TextLine]: ...


class EventSink(Protocol):
    def append_event(self, kind: str, payload: dict, *, timestamp: str | None = None) -> dict: ...
    def write_keyframe(self, image: Image.Image, *, reason: str, timestamp: str | None = None) -> str: ...


class CapturePipeline:
    def __init__(self, game_id: str, *, ocr: OCR, sink: EventSink, regions: dict[str, tuple] | None = None,
                 catalog: NameCatalog | None = None, layout: HudLayout | None = None, visual_reader: VisualReader | None = None, own_player_name: str | None = None, tracking_events=()):
        self.game_id, self.ocr, self.sink = str(game_id), ocr, sink
        self.regions = regions
        self.layout = layout or HudLayout()
        self._frame_size = None
        self.visual_reader, self.own_player_name = visual_reader, own_player_name
        self._vision_fields = {}
        self._vision_digest = None
        self._vision_result = None
        self.tracker = PurchaseTracker()
        self.tracker.restore(tracking_events)
        self._last_disagreements = None
        self._last_board_read = None
        self.catalog = catalog or NameCatalog()
        self.fields: dict[str, dict] = {}
        self._hashes: dict[str, bytes] = {}
        self._region_fields: dict[str, list[str]] = {}
        self._gap_start: datetime | None = None
        self._sequence = 0
        self._instance_id = uuid4().hex
        self._rolling = False
        self._last_roll = None
        self._roll_times = []
        self._gold_floor = None
        self._last_regular = None

    def tick(self, frame: Image.Image | None, *, timestamp: datetime | None = None) -> dict:
        now = timestamp or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("capture timestamps require a timezone")
        if self._rolling and self._last_roll and (now-self._last_roll).total_seconds() >= 3:
            self._rolling = False
        if frame is None:
            if self._gap_start is None:
                self._gap_start = now
        else:
            if self._gap_start:
                self.sink.append_event("capture_gap", {"reason": "window_unavailable", "start": self._gap_start.isoformat(), "end": now.isoformat()}, timestamp=now.isoformat())
                self._gap_start = None
            self._frame_size = frame.size
            rectangles = self.regions or self.layout.regions(frame.size)
            if self._rolling and self._last_regular and (now-self._last_regular).total_seconds() < .25:
                rectangles = {name: rectangle for name, rectangle in rectangles.items() if name in {"shop", "gold"}}
            else:
                self._last_regular = now
            pixel_regions = {name: tuple(int(value*(frame.width if index % 2 == 0 else frame.height)) for index, value in enumerate(rectangle))
                             for name, rectangle in rectangles.items()}
            # Read the viewed player's label before allowing any own-board read.
            for name in rectangles:
                if name not in {"shop", "board", "bench", "item_bench", "carousel"}:
                    self._read_region(name, frame.crop(pixel_regions[name]), frame, now)
            if self.visual_reader:
                self._read_vision(frame, pixel_regions, now)
            if "shop" in rectangles:
                self._read_region("shop", frame.crop(pixel_regions["shop"]), frame, now)
        if frame is not None and all(name in self.fields for name in ("round", "trait_rows", "hidden_traits", "scouted_player", "scouted_level")):
            names = ("round", "trait_rows", "hidden_traits", "scouted_player", "scouted_level")
            if (self.own_player_name and self.fields["scouted_player"]["value"] != self.own_player_name
                and all(self.fields[name]["read_at"] == now.isoformat() for name in names)):
                sighting = {"opponent_id": self.fields["scouted_player"]["value"], "round_id": self.fields["round"]["value"],
                            "level": self.fields["scouted_level"]["value"], "traits": self.fields["trait_rows"]["value"],
                            "hidden_traits": self.fields["hidden_traits"]["value"]}
                previous = self.fields.get("sighting", {}).get("value")
                if previous != sighting:
                    self.sink.append_event("sighting", sighting, timestamp=now.isoformat())
                    self.sink.write_keyframe(frame, reason="scouted_board", timestamp=now.isoformat())
                self.fields["sighting"] = {"value": sighting, "read_at": now.isoformat(), "source": self.ocr.source,
                                            "confidence": min(self.fields[name]["confidence"] for name in names)}
        stale = sorted(name for name, value in self.fields.items() if (now - datetime.fromisoformat(value["read_at"])).total_seconds() > (.5 if self._rolling and name in {"shop", "wisp", "slot_count"} else 2))
        snapshot = {"game_id": self.game_id, "round_id": self.fields.get("round", {}).get("value", ""),
                    "captured_at": now.isoformat(), "fields": deepcopy(self.fields),
                    "snapshot_id": f"{self.game_id}:{self._instance_id}:{self._sequence}", "stale_fields": stale,
                    "capture_layout": self.layout.describe(self._frame_size) if self._frame_size else None}
        self._sequence += 1
        for kind, payload in self.tracker.observe(snapshot):
            self.sink.append_event(kind, payload, timestamp=now.isoformat())
            if kind == "roll":
                self._last_roll = now
                self._roll_times = [time for time in self._roll_times if (now-time).total_seconds() <= 2] + [now]
                if len(self._roll_times) >= 2:
                    self._rolling = True
        gold = self.fields.get("gold", {})
        if self._rolling and self._gold_floor is not None and gold.get("read_at") == now.isoformat() and gold.get("value", 999) <= self._gold_floor:
            self._rolling = False
        snapshot["roll_down"] = self._rolling
        self.sink.append_event("snapshot", snapshot, timestamp=now.isoformat())
        return snapshot

    def finish_calibration_round(self, *, timestamp: datetime | None = None) -> bool:
        """Called by the lifecycle owner after the first round, including unreadable rounds."""
        now = timestamp or datetime.now(timezone.utc)
        readable = any(name not in {"shop_empty_slots"} for name in self.fields)
        payload = {"state": "readable" if readable else "unreadable",
                   "layout": self.layout.describe(self._frame_size) if self._frame_size else None}
        if not readable:
            payload["error"] = "No HUD fields read in the first round; check the game UI scale, client locale and region calibration"
        self.sink.append_event("calibration_status", payload, timestamp=now.isoformat())
        return readable

    @property
    def poll_interval(self):
        return 1/15 if self._rolling else .25

    def start_roll_down(self, *, gold_floor: int | None = None, timestamp: datetime | None = None):
        self._rolling = True
        self._gold_floor = gold_floor
        self._last_roll = timestamp or datetime.now(timezone.utc)

    def _read_vision(self, frame, pixel_regions, now):
        viewed_field = self.fields.get("scouted_player", {})
        viewed = viewed_field.get("value") if viewed_field.get("read_at") == now.isoformat() else None
        own_view = viewed == self.own_player_name if viewed and self.own_player_name else None
        visual_names = {"board", "bench", "item_bench", "cards", "carousel", "shop", "players"}
        fingerprints = tuple((name, frame.crop(rectangle).size,
            hashlib.blake2b(frame.crop(rectangle).tobytes(), digest_size=16).digest())
            for name, rectangle in pixel_regions.items() if name in visual_names)
        digest = (own_view, fingerprints)
        try:
            if digest != self._vision_digest:
                observed = self.visual_reader.read(frame, regions=pixel_regions, own_view=own_view)
                self._vision_result = VisionRead(deepcopy(observed.fields), observed.source,
                    observed.confidence, observed.inventory_complete)
                # A result with no observed fields is a failed read and must remain retryable.
                self._vision_digest = digest if self._vision_result.fields else None
            result = self._vision_result
            self._vision_fields = deepcopy(result.fields)
            output_fields=deepcopy(result.fields)
            field_sources={}
            if own_view is True and "board_observations" in result.fields:
                observations=result.fields["board_observations"]
                merged,disagreements=self.tracker.reconcile(observations,identity_min=getattr(self.visual_reader,"identity_min",.55))
                # Reconciliation owns the typed board; a raw complete reader result cannot bypass uncertainty.
                output_fields.pop("board",None)
                output_fields.pop("bench",None)
                output_fields.update(merged)
                if "board" in merged and any(observation.get("identity_confidence",0)<getattr(self.visual_reader,"identity_min",.55) for observation in observations):
                    field_sources.update(board=result.source+"+purchase-tracking",bench=result.source+"+purchase-tracking")
                if disagreements and disagreements!=self._last_disagreements:
                    self.sink.append_event("reader_disagreement",{"disagreements":disagreements},timestamp=now.isoformat())
                    self.sink.write_keyframe(frame,reason="reader_disagreement",timestamp=now.isoformat())
                self._last_disagreements=deepcopy(disagreements)
                if observations!=self._last_board_read:
                    self.sink.append_event("board_read",{"observations":observations,"model_version":getattr(self.visual_reader,"model_version",result.source),"label_map":getattr(self.visual_reader,"label_map",{})},timestamp=now.isoformat())
                    self.sink.write_keyframe(frame,reason="own_board",timestamp=now.isoformat())
                self._last_board_read=deepcopy(observations)
            for field, value in output_fields.items():
                if field in {"board", "bench", "board_observations", "tracked_units", "item_bench_observations", "items", "item_bench", "components", "completed_items", "owned_copies"} and own_view is not True:
                    continue
                self.fields[field] = {"value": deepcopy(value), "read_at": now.isoformat(),
                                      "source": field_sources.get(field,result.source), "confidence": result.confidence}
            if own_view is True and any(field in output_fields for field in ("board", "bench")):
                self.fields["inventory_complete"] = {"value": result.inventory_complete, "read_at": now.isoformat(),
                    "source": result.source, "confidence": result.confidence}
        except (ValueError, OSError, RuntimeError):
            self._vision_fields = {}
            self._vision_digest = None

    def _read_region(self, name, crop, frame, now):
        digest = hashlib.blake2b(crop.tobytes(), digest_size=16).digest()
        if self._hashes.get(name) == digest:
            for field in self._region_fields.get(name, []):
                self.fields[field] = {**self.fields[field], "read_at": now.isoformat()}
            return
        try:
            lines = self.ocr.read(crop, region=name)
            values = self._parse(name, lines)
        except (ValueError, OSError, RuntimeError):
            values = {}
        # Failed reads remain eligible for retry even when the pixels repeat.
        if not values:
            return
        self._hashes[name] = digest
        self._region_fields[name] = list(values)
        if name == "shop":
            self.sink.append_event("shop_offer", values, timestamp=now.isoformat())
            self.sink.write_keyframe(frame, reason="shop_offer", timestamp=now.isoformat())
        source = self.ocr.source_for(name) if hasattr(self.ocr, "source_for") else self.ocr.source
        confidences = [line.confidence for line in lines]
        if name == "shop" and self._vision_fields.get("shop_empty_slots"):
            confidences.append(self._vision_result.confidence)
            source = f"{source}+{self._vision_result.source}" if lines else self._vision_result.source
        for field, value in values.items():
            self.fields[field] = {"value": value, "read_at": now.isoformat(), "source": source,
                                  "confidence": min(confidences)}

    def _parse(self, region: str, lines: list[TextLine]) -> dict:
        if region == "gold" and len(lines) == 1 and lines[0].text.strip().isdigit():
            value = int(lines[0].text.strip())
            return {"gold": value} if 0 <= value <= 999 else {}
        text = " ".join(line.text for line in lines)
        if region == "stage":
            matches = re.findall(r"(?<!\d)([1-9])-([1-9])(?!\d)", text)
            if len(matches) == 1:
                return {"round": "-".join(matches[0]), "stage": int(matches[0][0])}
        if region in {"timer", "streak", "hp"} and len(lines) == 1:
            if text.strip().isdigit():
                value = int(text.strip())
                maximum = {"timer": 300, "streak": 99, "hp": 200}[region]
                return {region: value} if 0 <= value <= maximum else {}
        if region == "level":
            match = re.fullmatch(r"(?:Lvl\.?\s*|Level\s*)?(\d{1,2})", text.strip(), re.IGNORECASE)
            if match and 1 <= int(match[1]) <= 15:
                return {"level": int(match[1])}
        if region == "xp":
            match = re.fullmatch(r"(\d+)\s*/\s*(\d+)", text.strip())
            if match and int(match[1]) <= int(match[2]):
                return {"xp": int(match[1]), "xp_to_level": int(match[2])}
        if region == "odds":
            values = [int(value) for value in re.findall(r"(\d+)%", text)]
            if len(values) == 5 and sum(values) == 100:
                return {"shop_odds": values}
        if region == "traits":
            traits = {}
            hidden = None
            for line in lines:
                if re.fullmatch(r"\d+\+", line.text.strip()):
                    hidden = int(line.text.strip()[:-1])
                    continue
                match = re.fullmatch(r"(.+?)\s+(\d+)(?:\s*/\s*\d+)?", line.text.strip())
                if match:
                    trait = self.catalog.match(match[1], "traits")
                    if trait and int(match[2]) > 0:
                        traits[trait] = int(match[2])
            # Absence of N+ is not enough to prove zero hidden rows.
            values = {"trait_rows": traits} if traits else {}
            if hidden is not None:
                values["hidden_traits"] = hidden
            return values
        if region == "scouted":
            match = re.fullmatch(r"(.+?)\s+(?:Level|Lvl\.?)\s*(\d+)", text.strip(), re.IGNORECASE)
            if match and 1 <= int(match[2]) <= 15:
                return {"scouted_player": match[1], "scouted_level": int(match[2])}
        if region == "shop":
            slots = []
            wisp = None
            for index in range(5):
                rows = [line for line in lines if min(4, int((line.box[0]+line.box[2])/2*5)) == index]
                names = [line for line in rows if line.box[1] >= 0.72]
                unit_names = [(self.catalog.match(line.text, "units"), line) for line in names]
                unit_names = [(unit_id, line) for unit_id, line in unit_names if unit_id]
                wisp_names = [(self.catalog.match(line.text, "wisps"), line) for line in names]
                wisp_names = [(wisp_id, line) for wisp_id, line in wisp_names if wisp_id]
                costs = [int(line.text.strip()) for line in names if line.text.strip().isdigit() and 0 <= int(line.text.strip()) <= 99]
                if index in self._vision_fields.get("shop_empty_slots", []):
                    if unit_names or wisp_names:
                        return {}
                    slots.append({"slot": index, "unit_id": None, "cost": None, "traits": []})
                    continue
                if len(costs) != 1:
                    return {}
                if len(unit_names) == 1 and not wisp_names:
                    traits = [self.catalog.match(line.text, "traits") for line in rows if line.box[1] < 0.72]
                    slots.append({"slot": index, "unit_id": unit_names[0][0], "cost": costs[0], "traits": [trait for trait in traits if trait]})
                elif index == 4 and len(wisp_names) == 1 and not unit_names:
                    effect = " ".join(line.text for line in rows if line.box[1] < 0.72)
                    wisp = {"wisp_id": wisp_names[0][0], "cost": costs[0], "text": effect}
                else:
                    return {}
            return {"shop": slots, "wisp": wisp, "slot_count": len(slots)}
        return {}
