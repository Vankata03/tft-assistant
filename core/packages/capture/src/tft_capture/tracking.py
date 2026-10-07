"""Conservative events from independently observed shop and gold transitions."""
from collections import Counter
from datetime import datetime


class PurchaseTracker:
    def __init__(self):
        self.previous = None
        self.confirmed_acquisitions = Counter()

    def observe(self, snapshot: dict) -> list[tuple[str, dict]]:
        now = snapshot["captured_at"]
        values = {key: item["value"] for key, item in snapshot["fields"].items() if item["read_at"] == now}
        round_field = snapshot["fields"].get("round", {})
        if round_field and (datetime.fromisoformat(now) - datetime.fromisoformat(round_field["read_at"])).total_seconds() <= 2:
            values["round"] = round_field["value"]
        current = {"gold": values.get("gold"), "shop": values.get("shop"), "wisp": values.get("wisp"),
                   "round": values.get("round"), "timestamp": now}
        previous = self.previous
        self.previous = current
        if (not previous or current["gold"] is None or previous["gold"] is None or
            not current["shop"] or not previous["shop"] or not current["round"] or current["round"] != previous["round"]):
            return []
        difference = previous["gold"] - current["gold"]
        old = {slot["slot"]: slot for slot in previous["shop"]}
        new = {slot["slot"]: slot for slot in current["shop"]}
        changes = [(index, old[index], new[index]) for index in old.keys() & new.keys() if old[index].get("unit_id") != new[index].get("unit_id")]
        if len(changes) == 1:
            index, before, after = changes[0]
            if before.get("unit_id") and after.get("unit_id") is None and difference == before.get("cost"):
                unit_id = before["unit_id"]
                self.confirmed_acquisitions[unit_id] += 1
                return [("purchase", {"unit_id": unit_id, "slot": index, "cost": difference, "copies": 1})]
        if previous["wisp"] and current["wisp"] is None and len(new) == 5 and len(old) == 4 and difference == previous["wisp"]["cost"]:
            return [("wisp_purchase", dict(previous["wisp"]))]
        if (len(changes) >= 2 and difference == 2 and old.keys() == new.keys()
            and all(after.get("unit_id") for _, _, after in changes)
            and previous["wisp"] == current["wisp"]):
            return [("roll", {"cost": 2, "round_id": current["round"]})]
        if changes:
            return [("tracking_ambiguity", {"reason": "shop/gold transition has no unique purchase or roll", "gold_delta": difference})]
        return []
