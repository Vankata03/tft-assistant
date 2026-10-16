"""Live-only evaluation and bounded display projection over the shared Engine."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from tft_engine.evidence import EvidenceGraph, canonical_bytes
from tft_engine.models import _encode
from .surfaces import next_planning_preview, opponent_rows, roll_tracker
from tft_engine.planning import evaluate, observed_phase, field_age


DISPLAY_KEYS = frozenset((
    "id", "levels", "rolls", "family_id",
    "paused", "reason", "missing", "operation", "slot", "slots", "unit_id",
    "item_id", "augment_id", "wisp_id", "cost", "cost_units", "placement_gain",
    "power_gain", "gold_price", "grant_value", "source", "tier", "worth",
    "worth_label", "worth_stage", "paired_standard_error", "champion_slots_after",
    "best_comp", "buys", "allowance", "sell", "gold_gain", "gold_after",
    "gold_floor", "planned_gold", "sell_before_roll", "line_id", "pinned",
    "pin_alternative", "pin_gap", "swap_in", "swap_out", "target", "from",
    "holder", "holder_index", "from_index", "item_index", "item_ids", "transfers",
    "consume_tool", "layout", "arrows", "adjustments", "threat_shares", "voice",
    "turns_on", "threats_available", "ranking", "close", "expected_best",
    "keep_best", "qualified_static_only", "tiers", "model_unavailable",
))


def display_payload(payload):
    return {key: _encode(value) for key, value in payload.items() if key in DISPLAY_KEYS}


@dataclass(frozen=True)
class LiveDelivery:
    content: dict
    evidence: EvidenceGraph


class LiveAdvisor:
    def evaluate(self, snapshot, history, data, *, mode):
        if mode != "live":
            return None
        result = evaluate(snapshot, history, data, "live")
        evidence = EvidenceGraph.factor(_encode(result))
        rows = []
        for index, advice in enumerate(result.advice):
            reads = [snapshot.fields[name].read_at + timedelta(seconds=field_age(data, name, snapshot))
                     for name in advice.validity if data is not None and name in snapshot.fields
                     and not (name=='pinned_line' and snapshot.fields[name].source=='ui_pin')]
            rows.append({
                "decision_id": advice.decision_id,
                "option_id": advice.option_id,
                "domain": advice.decision,
                "action": advice.action,
                "urgency": advice.urgency,
                "confidence": advice.confidence,
                "reason": advice.reason,
                "numbers": dict(advice.numbers),
                "placement_impact": advice.placement_impact,
                "payload": display_payload(advice.payload),
                "anchors": _encode(advice.anchors),
                "validity": list(advice.validity),
                "valid_until": min(reads).isoformat() if reads else None,
                "evidence_path": ["advice", index],
                "options": [{"option_id": option.option_id, "action": option.action,
                             "expected_placement": option.expected_placement,
                             "standard_error": option.standard_error, "reason": option.reason,
                             "payload": display_payload(option.payload),
                             "evidence_path": ["advice", index, "options", position]}
                            for position, option in enumerate(advice.options)],
            })
        lines = [{"comp_id": result.plan.target, "line_id": row.line.id,
                  "seed": str(row.seed), "expected_placement": row.expected_placement,
                  "standard_error": row.standard_error, "hit_probability": row.hit_probability,
                  "death_probability": row.death_probability, "confidence": row.confidence,
                  "schedule": row.line.to_dict(),
                  "evidence_path": ["line_results", result.plan.target, index]}
                 for index, row in enumerate(result.line_results.get(result.plan.target, ()))]
        chosen_id = next((a.payload.get("line_id") for a in result.advice if a.decision == "econ"), None)
        chosen = next((row for row in result.line_results.get(result.plan.target, ()) if row.line.id == chosen_id), None)
        def deadline(names):
            if data is None or any(name not in snapshot.fields for name in names):return None
            return min(snapshot.fields[name].read_at+timedelta(seconds=field_age(data,name,snapshot)) for name in names).isoformat()
        content = {
            "game_id": snapshot.game_id,
            "snapshot_id": snapshot.snapshot_id,
            "captured_at": snapshot.captured_at.isoformat(),
            "evaluated_at": datetime.now(UTC).isoformat(),
            "data_snapshot_id": data.snapshot_id if data else None,
            "model_hash": sha256(canonical_bytes(_encode(data.tunables))).hexdigest() if data else None,
            "round_id": snapshot.round_id,
            "phase": (observed_phase(snapshot, data) or "unknown") if data else "unknown",
            "advice": rows,
            "plan": result.plan.to_dict(),
            "lines": lines,
            "projection": [row.to_dict() for row in chosen.projections] if chosen else [],
            "recommended_board": result.recommended_board.to_dict() if result.recommended_board else None,
            "fits": [{"comp_id": comp, "score": fit.score, "confidence": fit.confidence,
                      "evidence_path": ["comp_fits", comp]}
                     for comp, fit in result.comp_fits.items()],
            "roster_valid_until": deadline(('lobby','lobby_complete')),
            "ownership_valid_until": deadline(('board','bench','inventory_complete','level')),
            "opponents": opponent_rows(snapshot,history,data),
            "roll_tracker": roll_tracker(snapshot,data,result),
            "next_planning": next_planning_preview(snapshot, history, data, result),
            "confidence_medium_min": float(data.tunable('confidence_medium_min')) if data else None,
            "entity_names": {id:entity.name for id,entity in data.entities.items()} if data else {},
            "warnings": list(data.warnings) if data else ['Pinned data unavailable'],
            "evidence_id": evidence.root_id,
        }
        return LiveDelivery(content, evidence)
