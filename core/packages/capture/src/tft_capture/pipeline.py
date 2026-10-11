"""Automatic capture to JSON-safe snapshots and durable game-log events.

The OCR object is the external recognition boundary. Failed reads retain the
last known value and timestamp. Unchanged successfully captured pixels confirm
freshness without changing the original source or confidence.
"""
import hashlib
from collections import Counter
from copy import deepcopy
from uuid import uuid4
import re
from datetime import datetime, timezone
from typing import Protocol

from PIL import Image

from tft_capture.frames import full_image
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
                 catalog: NameCatalog | None = None, layout: HudLayout | None = None, visual_reader: VisualReader | None = None, own_player_name: str | None = None, tracking_events=(), unit_traits=None, item_traits=None, sale_values=None, video=None, unit_variants=None, data_snapshot_id=None, effect_sources=None, item_trait_sources=None):
        self.game_id, self.ocr, self.sink = str(game_id), ocr, sink
        self.video = video
        self._closed = False
        self._media_status = None
        self.regions = regions
        self.layout = layout or HudLayout()
        self._frame_size = None
        self.visual_reader, self.own_player_name = visual_reader, own_player_name
        self._vision_fields = {}
        self._vision_digest = None
        self._vision_result = None
        tracking_events = tuple(tracking_events)
        original_pins = {event.get('payload', {}).get('data_snapshot_id') for event in tracking_events
            if event.get('kind') in {'game_start', 'snapshot'} and event.get('payload', {}).get('data_snapshot_id')}
        if original_pins and original_pins != {data_snapshot_id}:
            raise ValueError('Resume capture with the original pinned data snapshot')
        self.tracker = PurchaseTracker(sale_values=sale_values)
        self.tracker.restore(tracking_events)
        self._last_disagreements = None
        self._last_board_read = None
        self.catalog = catalog or NameCatalog()
        self.unit_traits, self.item_traits = unit_traits or {}, item_traits or {}
        self.item_trait_sources = item_trait_sources or {}
        self.unit_variants = unit_variants or {}
        self.effect_sources = effect_sources or {}
        self.data_snapshot_id = data_snapshot_id
        self._last_ownership = None
        self._last_conflict = None
        self.fields: dict[str, dict] = {}
        self._picked_choices = set()
        for event in tracking_events:
            if event.get("kind") == "snapshot":
                self.fields = deepcopy(event["payload"].get("fields", {}))
            if event.get("kind") in {"augment_pick", "item_pick", "carousel_pick"}:
                token = event.get("payload", {}).get("choice_token")
                if token:
                    self._picked_choices.add(token)
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
        self._fight = None
        self._finished_fights = set()
        self._settled_signature = None
        self._settled_since = None
        self._level_previous = None
        self._wisp_round = None
        self._wisp_count = 0
        self._wisp_count_known = False
        self._wisp_baselined = set()
        for event in tracking_events:
            if event.get("kind") == "round_tracking_start":
                self._wisp_baselined.add(event["payload"]["round_id"])
        for event in tracking_events:
            kind, payload = event.get("kind"), event.get("payload", {})
            if kind == "fight_start":
                self._fight = deepcopy(payload)
            elif kind in {"fight_result", "fight_incomplete"}:
                self._finished_fights.add(payload["round_id"])
                self._fight = None

    @classmethod
    def from_data(cls, game_id, *, data, **kwargs):
        from tft_capture.knowledge import project_data
        options = project_data(data)
        options.update(kwargs)
        return cls(game_id, data_snapshot_id=data.snapshot_id, **options)

    def tick(self, frame: Image.Image | None, *, timestamp: datetime | None = None) -> dict:
        now = timestamp or datetime.now(timezone.utc)
        if self._closed:
            raise ValueError("Capture pipeline is closed")
        if now.tzinfo is None:
            raise ValueError("capture timestamps require a timezone")
        self._prior_inventory = {name: deepcopy(self.fields[name]) for name in ("held_augments", "held_augments_complete", "item_bench", "item_inventory_complete", "owned_copies", "inventory_complete", "board") if name in self.fields}
        if self._rolling and self._last_roll and (now-self._last_roll).total_seconds() >= 3:
            self._rolling = False
        if frame is None:
            if self._gap_start is None:
                self._gap_start = now
                self._invalidate_tracking()
                if self.video:
                    self.video.flush()
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
            for name in sorted(rectangles, key=lambda name: name != "scouted"):
                if name not in {"shop", "board", "bench", "item_bench", "carousel", "cards"}:
                    self._read_region(name, frame.crop(pixel_regions[name]), frame, now)
            own_view = (self.fields.get("scouted_player", {}).get("read_at") == now.isoformat()
                        and self.fields.get("scouted_player", {}).get("value") == self.own_player_name
                        and self.own_player_name is not None)
            trait_fields = ("trait_rows", "hidden_traits")
            if own_view and all(self.fields.get(name, {}).get("read_at") == now.isoformat() for name in trait_fields):
                source = self.fields["trait_rows"]
                self.fields["own_traits"] = {**source, "value": {"traits": deepcopy(source["value"]),
                    "hidden_traits": self.fields["hidden_traits"]["value"]}}
                if self.fields["hidden_traits"]["value"] == 0:
                    self.fields["own_trait_counts"] = deepcopy(source)
            if self.visual_reader:
                self._read_vision(frame, pixel_regions, now)
            if own_view and all(self.fields.get(name, {}).get("read_at") == now.isoformat() for name in ("board", "own_trait_counts")):
                board = self.fields["board"]
                counts = self.fields["own_trait_counts"]
                board["value"]["trait_counts"] = deepcopy(counts["value"])
                board["source"] += "+" + counts["source"]
                board["confidence"] = min(board["confidence"], counts["confidence"])
            if "shop" in rectangles:
                self._read_region("shop", frame.crop(pixel_regions["shop"]), frame, now)
            if "cards" in rectangles:
                self._read_region("cards", frame.crop(pixel_regions["cards"]), frame, now)
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
                    self.sink.write_keyframe(full_image(frame), reason="scouted_board", timestamp=now.isoformat())
                self.fields["sighting"] = {"value": sighting, "read_at": now.isoformat(), "source": self.ocr.source,
                                            "confidence": min(self.fields[name]["confidence"] for name in names)}
        if frame is not None:
            self._record_choices(frame, now)
            self._record_fight(frame, now)
            self._record_level(frame, now)
        self._record_certificates(frame, now)
        stale = sorted(name for name, value in self.fields.items() if (now - datetime.fromisoformat(value["read_at"])).total_seconds() > (.5 if self._rolling and name in {"shop", "wisp", "slot_count"} else 2))
        snapshot = {"game_id": self.game_id, "round_id": self.fields.get("round", {}).get("value", ""),
                    "captured_at": now.isoformat(), "fields": deepcopy(self.fields), "data_snapshot_id": self.data_snapshot_id, "roll_down": self._rolling,
                    "snapshot_id": f"{self.game_id}:{self._instance_id}:{self._sequence}", "stale_fields": stale,
                    "capture_layout": self.layout.describe(self._frame_size) if self._frame_size else None}
        phase = self.fields.get("phase", {})
        snapshot["phase"] = phase.get("value", "unknown") if phase and (now-datetime.fromisoformat(phase["read_at"])).total_seconds() <= 2 else "unknown"
        self._sequence += 1
        for kind, payload in self.tracker.observe(snapshot):
            self.sink.append_event(kind, payload, timestamp=now.isoformat())
            if kind == "wisp_purchase" and self._wisp_count_known:
                self._wisp_count += 1
                previous = self.fields["wisp_purchases_this_round"]
                self.fields["wisp_purchases_this_round"] = {**previous, "value": self._wisp_count, "read_at": now.isoformat(), "source": previous["source"]+"+confirmed-wisp-purchases"}
                snapshot["fields"] = deepcopy(self.fields)
            if kind == "tracking_ambiguity":
                self._wisp_count_known = False
                self.fields["wisp_purchase_count_complete"] = {"value": False, "read_at": now.isoformat(), "source": "capture-tracking-ambiguity", "confidence": 1.}
                snapshot["fields"] = deepcopy(self.fields)
            if kind == "tracking_ambiguity" and frame is not None:
                self.sink.write_keyframe(full_image(frame), reason="tracking_ambiguity", timestamp=now.isoformat())
            if kind == "roll":
                self._last_roll = now
                self._roll_times = [time for time in self._roll_times if (now-time).total_seconds() <= 2] + [now]
                if len(self._roll_times) >= 2:
                    self._rolling = True
        gold = self.fields.get("gold", {})
        if self._rolling and self._gold_floor is not None and gold.get("read_at") == now.isoformat() and gold.get("value", 999) <= self._gold_floor:
            self._rolling = False
        if frame is not None and hasattr(self.sink, "media_mode") and self.sink.media_mode == "full_video":
            try:
                if self.video is None:
                    raise RuntimeError("Full video requires a configured encoder")
                self.video.submit(full_image(frame), now)
                status = {"state": "recording"}
            except (ValueError, OSError, RuntimeError) as error:
                status = {"state": "unavailable", "error": str(error)}
            if status != self._media_status:
                self.sink.append_event("media_status", status, timestamp=now.isoformat())
                self._media_status = status
        snapshot["capture_copy"] = deepcopy(getattr(frame, "copy_stats", {}))
        snapshot["roll_down"] = self._rolling
        self.sink.append_event("snapshot", snapshot, timestamp=now.isoformat())
        return snapshot

    def _invalidate_tracking(self):
        self._settled_signature, self._settled_since = None, None
        self._wisp_count_known = False
        self._level_previous = None
        self.tracker.invalidate()

    def _record_level(self, frame, now):
        names = ('level', 'xp', 'xp_to_level')
        if not all(self.fields.get(name, {}).get('read_at') == now.isoformat() for name in names):
            self._level_previous = None
            return
        current = {name: self.fields[name]['value'] for name in names}
        previous = self._level_previous
        if previous and (now-datetime.fromisoformat(previous['read_at'])).total_seconds() <= 2 and current['level'] > previous['value']['level']:
            self.sink.append_event('level_up', {'before': previous['value'], 'after': current,
                'before_read_at': previous['read_at'], 'after_read_at': now.isoformat(),
                'sources': {name: self.fields[name]['source'] for name in names},
                'confidence': min(self.fields[name]['confidence'] for name in names)}, timestamp=now.isoformat())
            self.sink.write_keyframe(full_image(frame), reason='level_up', timestamp=now.isoformat())
        self._level_previous = {'value': current, 'read_at': now.isoformat()}

    def record_gap(self, *, start, end, reason):
        """Invalidate continuity when the runner replaces a window without a failed poll."""
        self._invalidate_tracking()
        if self.video:
            self.video.flush()
        self.sink.append_event("capture_gap", {"reason": reason, "start": start.isoformat(), "end": end.isoformat()}, timestamp=end.isoformat())

    def _record_certificates(self, frame, now):
        fresh = {name: field["value"] for name, field in self.fields.items() if field["read_at"] == now.isoformat()}
        if frame is not None and fresh.get("inventory_complete") is True and all(name in fresh for name in ("board", "bench")):
            signature = (fresh["board"], fresh["bench"])
            if signature != self._settled_signature:
                self._settled_signature = deepcopy(signature)
                self._settled_since = now.isoformat()
            self.fields["board_settled_since"] = {"value": self._settled_since, "read_at": now.isoformat(), "source": "complete-unchanged-own-board", "confidence": min(self.fields[name]["confidence"] for name in ("board", "bench", "inventory_complete"))}
        else:
            self._settled_signature, self._settled_since = None, None
        round_id = fresh.get("round")
        if round_id and round_id != self._wisp_round:
            self._wisp_round, self._wisp_count, self._wisp_count_known = round_id, 0, False
        baseline = round_id and fresh.get("round_start") is True and round_id not in self._wisp_baselined
        if baseline:
            self._wisp_baselined.add(round_id)
            self._wisp_count, self._wisp_count_known = 0, True
            self.sink.append_event("round_tracking_start", {"round_id": round_id}, timestamp=now.isoformat())
        if not baseline and (frame is None or fresh.get("wisp_complete") is not True):
            self._wisp_count_known = False
        certificate = {"read_at": now.isoformat(), "source": "positive-round-start-and-continuous-shop-tracking", "confidence": 1.}
        self.fields["wisp_purchase_count_complete"] = {**certificate, "value": self._wisp_count_known}
        if self._wisp_count_known:
            self.fields["wisp_purchases_this_round"] = {**certificate, "value": self._wisp_count}

    def close(self, *, timestamp=None):
        """Flush media and terminal gaps before the lifecycle owner ends the game log."""
        if self._closed:
            return
        now = timestamp or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("capture timestamps require a timezone")
        if self._gap_start:
            self.sink.append_event("capture_gap", {"reason": "window_unavailable", "start": self._gap_start.isoformat(), "end": now.isoformat()}, timestamp=now.isoformat())
            self._gap_start = None
        media_error = None
        if self.video:
            try:
                self.video.close()
            except (OSError, ValueError, RuntimeError) as error:
                media_error = error
                self.sink.append_event('media_status', {'state': 'unavailable', 'error': str(error)}, timestamp=now.isoformat())
        if self._fight:
            self.sink.append_event("fight_incomplete", {**self._fight, "reason": "Capture closed without a confirmed outcome"}, timestamp=now.isoformat())
        self.sink.append_event("capture_closed", {}, timestamp=now.isoformat())
        self._closed = True
        if media_error:
            raise media_error

    def _record_fight(self, frame, now):
        fresh = {key: field["value"] for key, field in self.fields.items() if field["read_at"] == now.isoformat()}
        round_id = fresh.get("round")
        if (self._fight is None and round_id and round_id not in self._finished_fights
            and fresh.get("phase") == "combat" and "fight_opponent" in fresh and "hp" in fresh):
            self._fight = {"round_id": round_id, "opponent_id": fresh["fight_opponent"], "hp_before": fresh["hp"]}
            encounters = self.fields.get("recent_opponent_fights", {}).get("value", []) + [{"opponent_id": fresh["fight_opponent"], "round_id": round_id, "read_at": now.isoformat()}]
            source = self.fields["fight_opponent"]
            self.fields["recent_opponent_fights"] = {**source, "value": encounters}
            self.fields["recent_opponents"] = {**source, "value": [row["opponent_id"] for row in encounters]}
            self.sink.append_event("fight_start", deepcopy(self._fight), timestamp=now.isoformat())
            self.sink.write_keyframe(full_image(frame), reason="fight_start", timestamp=now.isoformat())
        if self._fight and round_id and round_id != self._fight["round_id"]:
            self.sink.append_event("fight_incomplete", {**self._fight, "reason": "Next round without a confirmed outcome"}, timestamp=now.isoformat())
            self._fight = None
        if self._fight and fresh.get("fight_result") in {"win", "loss", "draw"} and "hp" in fresh and round_id == self._fight["round_id"]:
            payload = {**self._fight, "result": fresh["fight_result"], "hp_after": fresh["hp"]}
            if fresh["hp"] <= self._fight["hp_before"]:
                payload["hp_lost"] = self._fight["hp_before"]-fresh["hp"]
            self.sink.append_event("fight_result", payload, timestamp=now.isoformat())
            self.sink.write_keyframe(full_image(frame), reason="fight_result", timestamp=now.isoformat())
            source = self.fields["fight_result"]
            self.fields["last_fight"] = {**source, "value": payload, "confidence": min(source["confidence"], self.fields["hp"]["confidence"]), "source": source["source"]+"+"+self.fields["hp"]["source"]}
            self._finished_fights.add(round_id)
            self._fight = None

    def _record_choices(self, frame, now):
        confirmation = self.fields.get("confirmed_pick", {})
        inferred = None
        if confirmation.get("read_at") != now.isoformat() or not isinstance(confirmation.get("value"), dict):
            before = self._prior_inventory.get("held_augments", {})
            prior_complete = self._prior_inventory.get("held_augments_complete", {})
            held = self.fields.get("held_augments", {})
            complete = self.fields.get("held_augments_complete", {})
            if (prior_complete.get("value") is True and complete.get("value") is True
                and held.get("read_at") == now.isoformat() and complete.get("read_at") == now.isoformat()
                and before and (now-datetime.fromisoformat(before["read_at"])).total_seconds() <= 2):
                gained, lost = Counter(held["value"])-Counter(before["value"]), Counter(before["value"])-Counter(held["value"])
                rows = [row for row in self.fields.get("augments", {}).get("value", []) if gained.get(row["augment_id"]) == 1]
                if sum(gained.values()) == 1 and not lost and len(rows) == 1:
                    confirmation = {**held, "value": {"kind": "augment", "slot": rows[0]["slot"]}}
                    inferred = "held_augment_gain"
            if not inferred:
                return
        choice = confirmation["value"]
        kind, slot = choice.get("kind"), choice.get("slot")
        offers_name = {"augment": "augments", "item": "item_offers", "carousel": "carousel"}.get(kind)
        offers = self.fields.get(offers_name, {})
        if not offers_name or not isinstance(slot, int) or isinstance(slot, bool):
            return
        completeness = self.fields.get({"augment": "augment_offers_complete", "item": "item_offers_complete", "carousel": "carousel_complete"}[kind], {})
        if not offers or completeness.get("value") is not True or (now-datetime.fromisoformat(offers["read_at"])).total_seconds() > 2:
            return
        rows = [row for row in offers["value"] if row.get("slot") == slot]
        if len(rows) != 1:
            return
        row = rows[0]
        identity = row.get("augment_id") if kind == "augment" else row.get("item_id")
        token = repr((self.fields.get("round", {}).get("value"), kind, slot, row.get("augment_id"), row.get("unit_id"), row.get("item_id")))
        if token in self._picked_choices:
            return
        self._picked_choices.add(token)
        payload = {**deepcopy(row), "choice_token": token, "evidence": inferred or "positive_pick_confirmation"}
        if kind == 'carousel':
            before = self._prior_inventory.get('owned_copies', {})
            before_complete = self._prior_inventory.get('inventory_complete', {})
            current = self.fields.get('owned_copies', {})
            current_complete = self.fields.get('inventory_complete', {})
            before_known = before and before_complete.get('value') is True and (now-datetime.fromisoformat(before['read_at'])).total_seconds() <= 2
            current_known = current and current_complete.get('value') is True and current.get('read_at') == now.isoformat()
            included = False
            if current_known and current['value'].get(row['unit_id'], 0):
                if not before_known:
                    included = None
                else:
                    gain = Counter(current['value'])-Counter(before['value'])
                    loss = Counter(before['value'])-Counter(current['value'])
                    included = gain == Counter({row['unit_id']: 1}) and not loss
            payload['ownership_included'] = included
            if included is False:
                self.tracker.owned_copies[row['unit_id']] += 1
            if included is not True:
                self.tracker.inventory_complete = False
                self.fields['inventory_complete'] = {**confirmation, 'value': False, 'source': confirmation['source']+'+acquisition-awaiting-independent-ownership'}
            self.tracker.confirmed_acquisitions[row['unit_id']] += 1
        self.sink.append_event(kind+"_pick", payload, timestamp=now.isoformat())
        self.sink.write_keyframe(full_image(frame), reason=kind+"_pick", timestamp=now.isoformat())
        if kind == "augment" and inferred is None:
            held = self.fields.get("held_augments", {})
            complete = self.fields.get("held_augments_complete", {})
            known = (complete.get("value") is True and held and
                (now-datetime.fromisoformat(complete["read_at"])).total_seconds() <= 2 and
                (now-datetime.fromisoformat(held["read_at"])).total_seconds() <= 2)
            prior = self._prior_inventory.get('held_augments', {})
            prior_complete = self._prior_inventory.get('held_augments_complete', {})
            observed_gain = (prior_complete.get('value') is True and prior and held and
                Counter(held['value'])-Counter(prior['value']) == Counter({identity: 1}) and
                not Counter(prior['value'])-Counter(held['value']))
            uncertain_overlap = (prior_complete.get('value') is not True and held and
                held.get('read_at') == now.isoformat() and identity in held['value'])
            if known and not observed_gain and not uncertain_overlap:
                self.fields["held_augments"] = {"value": held["value"] + [identity], "read_at": now.isoformat(),
                    "source": confirmation["source"]+"+confirmed-choice-tracking", "confidence": min(confirmation["confidence"], held["confidence"])}
                self.fields["held_augments_complete"] = {**self.fields["held_augments"], "value": True}

    def finish_calibration_round(self, *, timestamp: datetime | None = None) -> bool:
        """Called by the lifecycle owner after the first round, including unreadable rounds."""
        now = timestamp or datetime.now(timezone.utc)
        readable = any(name != "shop_empty_slots" and not name.endswith("_complete") for name in self.fields)
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
        visual_names |= set(getattr(self.visual_reader, "observed_regions", ()))
        fingerprints = tuple((name, frame.crop(rectangle).size,
            hashlib.blake2b(frame.crop(rectangle).tobytes(), digest_size=16).digest())
            for name, rectangle in pixel_regions.items() if name in visual_names)
        digest = (own_view, fingerprints)
        try:
            if digest != self._vision_digest:
                observed = self.visual_reader.read(frame, regions=pixel_regions, own_view=own_view)
                self._vision_result = VisionRead(deepcopy(observed.fields), observed.source,
                    observed.confidence, observed.inventory_complete, deepcopy(observed.provenance))
                # A result with no observed fields is a failed read and must remain retryable.
                self._vision_digest = digest if self._vision_result.fields else None
            result = self._vision_result
            self._vision_fields = deepcopy(result.fields)
            output_fields=deepcopy(result.fields)
            output_fields.pop("owned_copies", None)
            output_fields.pop("inventory_complete", None)
            if own_view is True and any(name in result.fields for name in ("board_observations", "slot_inventory")):
                output_fields["inventory_complete"] = False
            field_sources={}
            if own_view is True and result.fields.get("trait_panel_empty") is True:
                self.fields["own_trait_counts"] = {"value": {}, "read_at": now.isoformat(), "source": result.source, "confidence": result.confidence}
            if own_view is True and "board_observations" in result.fields:
                observations=result.fields["board_observations"]
                complete = self._complete_ownership(result, observations, now)
                if complete:
                    copies = Counter()
                    for observation in observations:
                        copies[observation["unit_id"]] += 3**(observation["stars"]-1)
                    payload = {"copies": dict(copies), "complete": True}
                    if payload != self._last_ownership:
                        self.sink.append_event("ownership", payload, timestamp=now.isoformat())
                    self.tracker.owned_copies, self.tracker.inventory_complete = copies, True
                    self._last_ownership = payload
                    output_fields["owned_copies"] = dict(copies)
                output_fields["inventory_complete"] = complete
                item_provenance = {item: deepcopy(self.item_trait_sources[item]) for row in observations
                    for item in row.get("items") or () if item in self.item_trait_sources}
                if complete and item_provenance:
                    sources = sorted({value["source"] for value in item_provenance.values()})
                    field_sources["inventory_complete"] = result.source+"+pinned-item-traits:"+",".join(sources)
                if result.inventory_complete and not complete and result.fields != self._last_conflict:
                    self.sink.append_event("capture_conflict", {"reason": "Reader, independent slots, unit count and complete traits do not agree"}, timestamp=now.isoformat())
                    self.sink.write_keyframe(full_image(frame), reason="capture_conflict", timestamp=now.isoformat())
                    self._last_conflict = deepcopy(result.fields)
                merged,disagreements=self.tracker.reconcile(observations,identity_min=getattr(self.visual_reader,"identity_min",.55))
                # Reconciliation owns the typed board; a raw complete reader result cannot bypass uncertainty.
                output_fields.pop("board",None)
                output_fields.pop("bench",None)
                output_fields.update(merged)
                if complete and not observations:
                    output_fields.update(board={"units": [], "bench": [], "trait_counts": {}}, bench=[])
                if "board" in merged and any(observation.get("identity_confidence",0)<getattr(self.visual_reader,"identity_min",.55) for observation in observations):
                    field_sources.update(board=result.source+"+purchase-tracking",bench=result.source+"+purchase-tracking")
                if disagreements and disagreements!=self._last_disagreements:
                    self.sink.append_event("reader_disagreement",{"disagreements":disagreements},timestamp=now.isoformat())
                    self.sink.write_keyframe(full_image(frame),reason="reader_disagreement",timestamp=now.isoformat())
                self._last_disagreements=deepcopy(disagreements)
                if observations!=self._last_board_read:
                    self.sink.append_event("board_read",{"observations":observations,"model_version":getattr(self.visual_reader,"model_version",result.source),"label_map":getattr(self.visual_reader,"label_map",{}),"item_trait_provenance":item_provenance},timestamp=now.isoformat())
                    self.sink.write_keyframe(full_image(frame),reason="own_board",timestamp=now.isoformat())
                self._last_board_read=deepcopy(observations)
            for field, value in output_fields.items():
                if field in {"board", "bench", "board_observations", "tracked_units", "item_bench_observations", "items", "item_bench", "components", "completed_items", "owned_copies", "slot_inventory", "inventory_complete", "item_inventory_complete", "tools", "removers", "reforgers", "trait_panel_empty", "own_trait_counts", "lux_origin", "held_augments", "held_augments_complete"} and own_view is not True:
                    continue
                if field in {"item_offers", "carousel"} and self.fields.get(field, {}).get("value") != value:
                    reason = "item_offer" if field == "item_offers" else "carousel_offer"
                    self.sink.append_event(reason, {field: deepcopy(value)}, timestamp=now.isoformat())
                    self.sink.write_keyframe(full_image(frame), reason=reason, timestamp=now.isoformat())
                self.fields[field] = {"value": deepcopy(value), "read_at": now.isoformat(),
                                      "source": field_sources.get(field,result.provenance.get(field, {}).get("source", result.source)), "confidence": result.provenance.get(field, {}).get("confidence", result.confidence)}
            if own_view is True and any(field in output_fields for field in ("board", "bench")) and "inventory_complete" not in output_fields:
                self.fields["inventory_complete"] = {"value": False, "read_at": now.isoformat(),
                    "source": result.source, "confidence": result.confidence}
        except (ValueError, OSError, RuntimeError):
            self._vision_fields = {}
            self._vision_digest = None

    def _complete_ownership(self, result, observations, now):
        if not result.inventory_complete or any(self.fields.get(name, {}).get("read_at") != now.isoformat()
            for name in ("unit_count", "own_trait_counts")):
            return False
        slots = result.fields.get("slot_inventory", {})
        for zone, total in (("board", 28), ("bench", 9)):
            occupied, empty = slots.get(zone+"_occupied", []), slots.get(zone+"_empty", [])
            if len(occupied)+len(empty) != total or set(occupied+empty) != set(range(total)):
                return False
            actual = [row.get("position") for row in observations if row.get("zone") == zone]
            if sorted(actual, key=str) != sorted(occupied, key=str):
                return False
        if len(slots["board_occupied"]) != self.fields["unit_count"]["value"]:
            return False
        possibilities = [Counter()]
        target = self.fields["own_trait_counts"]["value"]
        seen = set()
        for row in observations:
            if not row.get("unit_id") or row.get("stars") not in (1, 2, 3) or row.get("items") is None or row.get("identity_confidence", 0) < getattr(self.visual_reader, "identity_min", .55):
                return False
            if row["zone"] == "board":
                if row["unit_id"] not in seen:
                    variants = self.unit_variants.get(row["unit_id"])
                    if variants is None:
                        known = self.unit_traits.get(row["unit_id"])
                        if known is None:
                            return False
                        variants = [known]
                    possibilities = [counts+Counter(variant) for counts in possibilities for variant in variants
                        if all(counts.get(trait, 0)+count <= target.get(trait, 0) for trait, count in variant.items())]
                    if not possibilities or len(possibilities) > 4096:
                        return False
                    seen.add(row["unit_id"])
                for item in row["items"]:
                    if item not in self.item_traits:
                        return False
                    possibilities = [counts+Counter(self.item_traits[item]) for counts in possibilities]
        return any(dict(counts) == target for counts in possibilities)

    def _read_region(self, name, crop, frame, now):
        if name in {"origin", "unit_count"} and not (self.own_player_name and self.fields.get("scouted_player", {}).get("value") == self.own_player_name
            and self.fields["scouted_player"]["read_at"] == now.isoformat()):
            return
        digest = hashlib.blake2b(crop.tobytes(), digest_size=16).digest()
        if name == "cards":
            digest += repr((self._vision_fields.get("augment_tier"), self._vision_fields.get("augment_rerolls"))).encode()
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
            self.sink.write_keyframe(full_image(frame), reason="shop_offer", timestamp=now.isoformat())
        if "augments" in values:
            old = self.fields.get("augments", {})
            if old and (now-datetime.fromisoformat(old["read_at"])).total_seconds() <= 2:
                before = {row["slot"]: row for row in old["value"]}
                changed = [(before[row["slot"]], row) for row in values["augments"]
                    if row["slot"] in before and before[row["slot"]]["augment_id"] != row["augment_id"]]
                for prior, after in changed:
                    if prior.get("reroll_available") is True and after.get("reroll_available") is False:
                        self.sink.append_event("augment_reroll", {"slot": after["slot"], "before": prior["augment_id"], "after": after["augment_id"]}, timestamp=now.isoformat())
                        self.sink.write_keyframe(full_image(frame), reason="augment_reroll", timestamp=now.isoformat())
            self.sink.append_event("augment_offer", {"augments": values["augments"], "tier": values["augment_tier"]}, timestamp=now.isoformat())
            self.sink.write_keyframe(full_image(frame), reason="augment_offer", timestamp=now.isoformat())
        source = self.ocr.source_for(name) if hasattr(self.ocr, "source_for") else self.ocr.source
        confidences = [line.confidence for line in lines]
        if name == "shop" and self._vision_fields.get("shop_empty_slots"):
            confidences.append(self._vision_result.confidence)
            source = f"{source}+{self._vision_result.source}" if lines else self._vision_result.source
        if name == "cards" and self._vision_result:
            confidences.append(self._vision_result.confidence)
            source += "+" + self._vision_result.source
        for field, value in values.items():
            self.fields[field] = {"value": value, "read_at": now.isoformat(), "source": source,
                                  "confidence": min(confidences)}

    def _parse(self, region: str, lines: list[TextLine]) -> dict:
        if region == "effects":
            counts, effects = [], []
            for line in lines:
                header = re.fullmatch(r"Remaining effects:\s*(\d+)", line.text.strip(), re.IGNORECASE)
                if header:
                    counts.append(int(header[1]))
                    continue
                match = re.fullmatch(r"(.+?):\s*(\d+)\s+(rounds|rolls|gold|xp)\s+remaining", line.text.strip(), re.IGNORECASE)
                identity = self.catalog.match(match[1], "effects") if match else None
                if identity in self.effect_sources:
                    effects.append({"effect_id": identity, "source_kind": self.effect_sources[identity],
                        "remaining_"+match[3].lower(): int(match[2])})
            if not counts:
                return {}
            complete = len(counts) == 1 and counts[0] == len(effects) and len({row['effect_id'] for row in effects}) == len(effects)
            values = {"remaining_effects_complete": complete}
            if complete:
                values["remaining_effects"] = effects
            return values
        if region == "fight_opponent" and len(lines) == 1:
            match = re.fullmatch(r"Opponent:\s*(.+)", lines[0].text.strip(), re.IGNORECASE)
            if match:
                identity = self.catalog.match(match[1], "players") if self.catalog.names.get("players") else match[1]
                return {"fight_opponent": identity} if identity else {}
        if region == "fight_result" and len(lines) == 1:
            result = self.catalog.match(lines[0].text, "fight_results") or {"victory": "win", "defeat": "loss", "draw": "draw"}.get(lines[0].text.strip().casefold())
            return {"fight_result": result} if result in {"win", "loss", "draw"} else {}
        if region == "gold" and len(lines) == 1 and lines[0].text.strip().isdigit():
            value = int(lines[0].text.strip())
            return {"gold": value} if 0 <= value <= 999 else {}
        text = " ".join(line.text for line in lines)
        if region == "unit_count":
            match = re.fullmatch(r"(\d{1,2})\s*/\s*(\d{1,2})", text.strip())
            if match and 0 <= int(match[1]) <= int(match[2]) <= 28:
                return {"unit_count": int(match[1]), "unit_capacity": int(match[2])}
        if region == "cards":
            offers = []
            for slot in range(3):
                group = [line for line in lines if min(2, int((line.box[0]+line.box[2])/2*3)) == slot]
                matches = [(self.catalog.match(line.text, "augments"), line) for line in group]
                matches = [(identity, line) for identity, line in matches if identity]
                if len(matches) != 1:
                    continue
                identity, name_line = matches[0]
                offer = {"slot": slot, "augment_id": identity, "name": name_line.text,
                    "text": " ".join(line.text for line in group if line is not name_line and line.box[1] > name_line.box[1])}
                offers.append(offer)
            if not offers:
                return {}
            tier = self._vision_fields.get("augment_tier")
            rerolls = self._vision_fields.get("augment_rerolls", {})
            complete = (len(offers) == 3 and tier in {"silver", "gold", "prismatic"}
                        and all(isinstance(rerolls.get(str(slot)), bool) for slot in range(3)))
            values = {"augment_observations": offers, "augment_offers_complete": complete}
            if complete:
                for offer in offers:
                    offer.update(tier=tier, reroll_available=rerolls[str(offer["slot"])])
                values.update(augments=offers, augment_tier=tier)
            return values
        if region == "players":
            groups = {}
            for line in lines:
                row = min(7, int((line.box[1]+line.box[3])/2*8))
                groups.setdefault(row, []).append(line)
            players = []
            for row, group in sorted(groups.items()):
                value = " ".join(line.text for line in sorted(group, key=lambda line: line.box[0]))
                match = re.fullmatch(r"(.+?)\s+(\d{1,3})", value.strip())
                if not match or not 0 <= int(match[2]) <= 200:
                    continue
                name = match[1].strip()
                identity = self.catalog.match(name, "players") if self.catalog.names.get("players") else name
                if identity:
                    players.append({"player_id": identity, "name": name, "hp": int(match[2]),
                        "alive": int(match[2]) > 0, "is_self": name == self.own_player_name, "row": row})
            if not players:
                return {}
            complete = len(players) == 8 and len({row["player_id"] for row in players}) == 8
            values = {"player_rows": players, "lobby_complete": complete}
            if complete:
                values["lobby"] = {row["player_id"]: row for row in sorted(players, key=lambda row: row["player_id"])}
            own = [row for row in players if row["is_self"]]
            if len(own) == 1:
                values.update(hp=own[0]["hp"], player_id=own[0]["player_id"])
            return values
        if region == "phase" and len(lines) == 1:
            aliases = {"planning": "planning", "combat": "combat", "carousel": "carousel",
                       "choose augment": "augment", "end": "end"}
            phase = self.catalog.match(text, "phases") or aliases.get(text.strip().casefold())
            if phase in {"planning", "roll_down", "augment", "carousel", "combat", "end"}:
                return {"phase": phase, "planning_phase": phase in {"planning", "roll_down"}}
        if region == "origin":
            match = re.fullmatch(r"Origin:\s*(.+)", text.strip(), re.IGNORECASE)
            identity = self.catalog.match(match[1], "traits") if match else None
            return {"lux_origin": identity} if identity else {}
        if region == "stage":
            matches = re.findall(r"(?<!\d)([1-9])-([1-9])(?!\d)", text)
            if len(matches) == 1:
                return {"round": "-".join(matches[0]), "stage": int(matches[0][0])}
        if region in {"timer", "streak", "hp"} and len(lines) == 1:
            if re.fullmatch(r"-?\d+" if region == "streak" else r"\d+", text.strip()):
                value = int(text.strip())
                maximum = {"timer": 300, "streak": 99, "hp": 200}[region]
                return {region: value} if (abs(value) <= maximum if region == "streak" else 0 <= value <= maximum) else {}
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
                    wisp = {"wisp_id": wisp_names[0][0], "slot": index, "cost": costs[0], "text": effect}
                else:
                    return {}
            return {"shop": slots, "wisp": wisp, "wisp_complete": True, "slot_count": len(slots)}
        return {}
