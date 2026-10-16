"""Mode-gated delivery and attribution over immutable Engine evidence.

This module can ship without the Live advisor. It accepts its public serialized
output and never imports that optional package or computes decision values.
"""

from dataclasses import dataclass
from collections import OrderedDict
from datetime import UTC, datetime

from tft_engine.evidence import EvidenceGraph, canonical_bytes, content_id

from tft_core.messages import LiveState

STATE_BYTE_BUDGET = 256 * 1024
DETAIL_BYTE_BUDGET = 60 * 1024


@dataclass(frozen=True)
class PreparedDelivery:
    epoch: int
    state: LiveState
    graph: EvidenceGraph
    cached: bool


class LiveDeliveryController:
    def __init__(self, sessions):
        self.sessions = sessions
        self.current = None
        self.revisions = OrderedDict()
        self.status = "Live advisor waiting for fresh capture"
        self.pin = None
        self.pin_schedule = None
        self.pin_read_at = None
        self.pin_context = None
        self._shown = set()
        self.observation = None
        self.observed_data = None
        self.invalidated = {}
        self._invalidated_logged = set()
        self._observation_seen = False
        self.observed_phase = None
        self.epoch = 0
        self.roster_qualified = None
        self.ownership_qualified = None
        self._current_epoch = None

    def prepare(self, delivery):
        """Validate a bounded summary on the owner loop, without file I/O."""
        if not self.sessions or self.sessions.mode.value != "live" or not self.sessions.live_installed:
            raise ValueError("Live delivery requires the installed advisor and Live mode")
        if self._observation_seen and (self.observation is None or self.observed_data is None):
            raise ValueError("Live delivery rejected because capture is unavailable")
        content = delivery.content
        if self.observed_data is not None and content['data_snapshot_id'] != self.observed_data.snapshot_id:
            raise ValueError('Live delivery uses a different pinned data snapshot')
        if content["game_id"] != self.sessions.active_game_id:
            raise ValueError("Live delivery does not belong to the active game")
        if content["evidence_id"] != delivery.evidence.root_id:
            raise ValueError("Live delivery evidence identity mismatch")
        revision = content_id(content)
        state = LiveState(mode="live", status="Live advice ready", revision=revision, content=content)
        if len(state.model_dump_json().encode()) > STATE_BYTE_BUDGET:
            raise ValueError("Live summary exceeds its delivery byte budget; full evidence remains offline")
        return PreparedDelivery(self.epoch,state,delivery.evidence,revision in self.revisions)

    def persist(self, prepared, *, cancelled=None):
        """Worker-owned file preparation; never mutate controller/window state."""
        if prepared.cached:
            return None
        return self.sessions.write_evidence(prepared.graph,
            expected_game_id=prepared.state.content.game_id,expected_mode="live",
            cancelled=lambda:prepared.epoch!=self.epoch or bool(cancelled and cancelled()))

    def activate(self, prepared, reference):
        """Owner-loop activation after durable evidence and fresh permission checks."""
        state = prepared.state
        content = state.content.model_dump(mode="json")
        if prepared.epoch != self.epoch or not self.sessions or self.sessions.mode.value != "live" or state.content.game_id != self.sessions.active_game_id:
            raise ValueError("Live publication was superseded or its mode permission changed")
        if self._observation_seen and (self.observation is None or self.observed_data is None):
            raise ValueError("Live publication capture is unavailable")
        if self.observed_data is not None and state.content.data_snapshot_id != self.observed_data.snapshot_id:
            raise ValueError('Live publication pinned data was superseded')
        if state.revision not in self.revisions:
            if prepared.cached or not reference or reference.get('evidence_id') != prepared.graph.root_id:
                raise ValueError("Live publication has no current durable evidence")
            event = self.sessions.append_event("advice_delivery", {
                "schema_version": 1, "delivery_revision": state.revision,
                "game_id": content["game_id"], "snapshot_id": content["snapshot_id"],
                "data_snapshot_id": content["data_snapshot_id"], "model_hash": content["model_hash"],
                "captured_at": content["captured_at"], "evaluated_at": content["evaluated_at"],
                "evidence_id": prepared.graph.root_id, "summary": content,
            },expected_game_id=content['game_id'],expected_mode='live')
            self.revisions[state.revision] = (state, prepared.graph, event["timestamp"])
            while len(self.revisions) > 64:
                removed, _ = self.revisions.popitem(last=False)
                self._shown = {key for key in self._shown if key[0] != removed}
                self._invalidated_logged = {key for key in self._invalidated_logged if key[0] != removed}
        self.current = state
        self._current_epoch = self.epoch
        self._invalidate_changed_fields()
        return state

    def publish(self, delivery):
        """Synchronous boundary for offline callers; async shell uses staged I/O."""
        prepared = self.prepare(delivery)
        return self.activate(prepared,self.persist(prepared))

    def state(self, mode):
        if mode.value != "live" or self.current is None or not self.sessions or self.current.content.game_id != self.sessions.active_game_id:
            return LiveState(mode=mode.value, status=self.status)
        return self.current.model_copy(update={"pin": self.pin, "invalidated": self.invalidated,
                                               "next_planning_invalidated": self._next_planning_invalid(),
                                               "observed_phase": self.observed_phase,"roster_qualified":self.roster_qualified,"ownership_qualified":self.ownership_qualified})

    def clear(self, reason):
        context = self.pin_context
        self.epoch += 1
        self.current = None
        self.pin = None
        self.pin_schedule = None
        self.pin_read_at = None
        self.pin_context = None
        self.status = reason
        self.invalidated = {}
        if context is not None:
            self._log_pin_reset(context, reason)

    def _log_pin_reset(self, context, reason):
        # Replay sees the accepted pin until a causal reset; memory alone is not
        # evidence. A detached or replaced game already logged its own boundary.
        if not self.sessions or self.sessions.active_game_id != context["game_id"]:
            return
        try:
            self.sessions.append_event("session_controls_reset", {"schema_version": 1,
                "game_id": context["game_id"], "data_snapshot_id": context["data_snapshot_id"],
                "delivery_revision": context["delivery_revision"], "pin_seq": context["seq"],
                "pin_read_at": context["read_at"], "reason": reason}, expected_game_id=context["game_id"])
        except (OSError, ValueError) as error:
            self.status = f"{reason} · pin reset could not be logged: {error}"

    def observe(self, snapshot, data):
        from tft_engine import GameSnapshot
        from tft_engine.planning import observed_phase
        self._observation_seen = True
        self.observed_data = data
        self.observation = (GameSnapshot.from_dict(snapshot) if isinstance(snapshot, dict) else snapshot)
        if self.observation and (not self.sessions or self.observation.game_id != self.sessions.active_game_id):
            self.observation = None
            self.observed_data = None
        if self.current and self.observation and self.observation.game_id != self.current.content.game_id:
            self.clear('New game · waiting for its own Live advice')
        context=self.pin_context
        if (self.observation and data and context and self.pin_read_at is not None
            and context['game_id']==self.observation.game_id
            and context['data_snapshot_id']==data.snapshot_id
            and context['epoch']==self.epoch
            and self.pin_read_at<=self.observation.captured_at):
            from dataclasses import replace
            from tft_engine import FieldValue
            self.observation=replace(self.observation,fields=dict(self.observation.fields)|{
                'pinned_line':FieldValue(self.pin_schedule,self.pin_read_at,'ui_pin',1)})
        from tft_engine.lobby import lobby_certificate_qualified
        from tft_engine.planning import required
        self.roster_qualified = lobby_certificate_qualified(self.observation,data) if self.observation and data else False
        self.ownership_qualified = not required(self.observation,data,('board','bench','inventory_complete','level')) if self.observation and data else False
        self.observed_phase = (observed_phase(self.observation, data) or 'unknown') if self.observation and data else 'unknown'
        if not self.observation or not data:
            self.clear("Live advice paused · capture or pinned data unavailable")
        else:
            self._invalidate_changed_fields()

    def _next_planning_invalid(self):
        """Combat's preview expires with its round, phase, pinned data, plan and reached level."""
        preview = self.current.content.next_planning
        if preview is None or not preview.available:
            return None
        if self.epoch != self._current_epoch:
            return "plan changed"
        if not self._observation_seen:
            return None
        state, data = self.observation, self.observed_data
        if state is None or data is None:
            return "capture unavailable"
        if state.game_id != self.current.content.game_id or state.round_id != self.current.content.round_id:
            return "round or game changed"
        if data.snapshot_id != self.current.content.data_snapshot_id:
            return "pinned data changed"
        if self.observed_phase in ("planning", "roll_down"):
            return "new planning evidence"
        if self.observed_phase != "combat":
            return "combat phase unread" if self.observed_phase == "unknown" else "combat ended"
        from tft_engine.planning import read
        level = read(state, data, "level")
        if preview.level is not None and level is not None and int(level) >= preview.level:
            return "level reached"
        return None

    def _invalidate_changed_fields(self):
        from tft_engine.models import _encode
        from tft_engine.planning import read,required
        if not self.current or not self.observation or not self.observed_data:
            return
        state, data = self.observation, self.observed_data
        graph = self.revisions[self.current.revision][1]
        invalid = {}
        for index, row in enumerate(self.current.content.advice):
            if row.urgency == "information":
                continue
            if state.game_id != self.current.content.game_id or state.round_id != self.current.content.round_id:
                invalid[row.decision_id] = "round or game changed"
                continue
            evidence_path = ("advice", index, "validity_state")
            if graph.resolve(path=evidence_path + ("data_snapshot_id",)) != data.snapshot_id:
                invalid[row.decision_id] = "pinned data changed"
                continue
            original_fields=graph.resolve(path=evidence_path + ("fields",))
            missing=required(state,data,tuple(name for name,field in original_fields.items() if field is not None and field['value'] is not None))
            if missing:
                invalid[row.decision_id]=f'{missing[0]} unread or stale'
                continue
            for name, original in original_fields.items():
                field = state.fields.get(name)
                actual = read(state, data, name) if field and field.read_at <= state.captured_at else None
                expected = original["value"] if original is not None else None
                if _encode(actual) != expected:
                    invalid[row.decision_id] = f"{name} unread or stale" if actual is None else f"{name} changed"
                    break
        self.invalidated = invalid
        for decision_id,reason in invalid.items():
            key=(self.current.revision,decision_id,reason)
            if key in self._invalidated_logged:
                continue
            self._invalidated_logged.add(key)
            self.sessions.append_event('advice_paused' if 'unread or stale' in reason else 'advice_too_late',
                {'delivery_revision':self.current.revision,'decision_id':decision_id,'reason':reason,
                 'captured_at':state.captured_at.isoformat()},expected_game_id=state.game_id,expected_mode='live')

    def _member(self, game_id, revision, mode):
        if mode.value != "live" or not self.current or game_id != self.sessions.active_game_id or revision not in self.revisions:
            raise ValueError("Live request does not belong to current permitted delivery")
        stored = self.revisions[revision]
        if stored[0].content.game_id != game_id:
            raise ValueError("Live delivery belongs to another game")
        return stored

    def page(self, message, mode):
        state, graph, _ = self._member(message.game_id, message.revision, mode)
        if message.revision != self.current.revision:
            raise ValueError("Detail delivery was superseded")
        return graph.page(path=message.path, cursor=message.cursor, limit=message.limit, max_bytes=DETAIL_BYTE_BUDGET)

    def shown(self, message, mode):
        state, _, delivered_at = self._member(message.game_id, message.revision, mode)
        selected = next((row for row in state.content.advice
                         if row.decision_id == message.decision_id and row.option_id == message.option_id), None)
        current = next((row for row in self.current.content.advice
                        if row.decision_id == message.decision_id and row.option_id == message.option_id), None)
        if not selected or not current:
            raise ValueError("Shown advice is not a current delivered decision/option")
        if message.decision_id in self.invalidated:
            reason = self.invalidated[message.decision_id]
            kind = "advice_paused" if "unread or stale" in reason else "advice_too_late"
            self.sessions.append_event(kind, {"delivery_revision": message.revision,
                "decision_id": message.decision_id, "option_id": message.option_id,
                "surface": message.surface, "reason": reason})
            raise ValueError("Advice no longer applies to the observed capture: " + reason)
        key = (message.revision, message.decision_id, message.option_id, message.surface)
        if key in self._shown:
            return
        now = datetime.now(UTC)
        if message.timestamp < datetime.fromisoformat(delivered_at) or (message.timestamp - now).total_seconds() > 1:
            raise ValueError("Shown timestamp is outside the delivery interval")
        if selected.valid_until and message.timestamp > selected.valid_until:
            self.sessions.append_event("advice_paused", {"delivery_revision": message.revision,
                                       "decision_id": message.decision_id, "option_id": message.option_id,
                                       "surface": message.surface, "reason": "required evidence expired"})
            raise ValueError("Advice expired before acknowledgement")
        self.sessions.append_event("ui_show", {"schema_version": 1, "mode": mode.value,
            "surface": message.surface, "delivery_revision": message.revision,
            "decision_id": message.decision_id, "option_id": message.option_id,
            "evidence_id": state.content.evidence_id, "delivered_at": delivered_at,
            "received_at": now.isoformat()}, timestamp=message.timestamp.isoformat())
        self._shown.add(key)

    def pin_line(self, message, mode):
        self._member(message.game_id, message.revision, mode)
        if message.revision != self.current.revision:
            raise ValueError("Line pin delivery was superseded")
        if message.line_id is None:
            self.pin = None
            self.pin_schedule = None
        else:
            candidate = next((row for row in self.current.content.lines
                              if row.line_id == message.line_id
                              and row.comp_id == message.comp_id
                              and row.seed == message.seed), None)
            econ = next((row for row in self.current.content.advice if row.domain == "econ" and not row.payload.get("paused")), None)
            if not candidate or self.current.content.phase not in {"planning", "roll_down"} or not econ or econ.decision_id in self.invalidated or not econ.valid_until or datetime.now(UTC) > econ.valid_until:
                raise ValueError("Line pin is not a fresh scored planning candidate")
            self.pin = {"comp_id": message.comp_id, "line_id": message.line_id, "seed": message.seed}
            self.pin_schedule = candidate.schedule
        event=self.sessions.append_event("line_pin", {"delivery_revision": message.revision,
            "game_id":message.game_id,"data_snapshot_id":self.current.content.data_snapshot_id,
            "pin": self.pin, "schedule": self.pin_schedule},expected_game_id=message.game_id,expected_mode="live")
        self.epoch += 1
        self.pin_read_at=datetime.fromisoformat(event['timestamp']) if self.pin is not None else None
        self.pin_context=({"game_id":message.game_id,"data_snapshot_id":self.current.content.data_snapshot_id,
            "delivery_revision":message.revision,"epoch":self.epoch,"read_at":event['timestamp'],"seq":event['seq'],
            "schedule":self.pin_schedule,"pin":self.pin} if self.pin is not None else None)
