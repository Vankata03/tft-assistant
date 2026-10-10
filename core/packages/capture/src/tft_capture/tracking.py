"""Conservative events from independently observed shop and gold transitions."""
from collections import Counter
from datetime import datetime


class PurchaseTracker:
    def __init__(self):
        self.previous = None
        self.confirmed_acquisitions = Counter()
        self.owned_copies = Counter()
        self.inventory_complete = False

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
                self.owned_copies[unit_id] += 1
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

    def restore(self, events):
        """Recover positively established ownership from the same game's durable log."""
        for event in events:
            kind,payload=event.get("kind"),event.get("payload",{})
            if kind=="ownership":
                copies=payload.get("copies",{})
                if any(not isinstance(value,int) or isinstance(value,bool) or value<0 for value in copies.values()):
                    raise ValueError("Ownership copies must be nonnegative integers")
                self.owned_copies=Counter(copies)
                self.inventory_complete=payload.get("complete") is True
            elif kind=="purchase":
                self.owned_copies[payload["unit_id"]]+=payload.get("copies",1)

    def reconcile(self, observations, *, identity_min=.55):
        """Preserve reader geometry/details; replace identity only with unique complete tracking evidence."""
        remaining=self.owned_copies.copy()
        assignments=[]
        pending=[]
        disagreements=[]
        for observation in observations:
            identity=observation.get("unit_id")
            confident=identity is not None and observation.get("identity_confidence",0)>=identity_min
            copies=3**(observation["stars"]-1) if observation.get("stars") in (1,2,3) else 1
            if confident and remaining[identity]>=copies:
                remaining[identity]-=copies
                assignments.append((observation,identity))
            else:
                pending.append((observation,confident,copies))
        for observation,confident,copies in pending:
            expected=[identity for identity,count in remaining.items() if count>=copies] if self.inventory_complete else []
            observed=observation.get("unit_id")
            tracked=expected[0] if len(expected)==1 else None
            identity=observed if confident else tracked
            if tracked and identity==tracked:
                remaining[tracked]-=copies
            if tracked and tracked!=observed:
                disagreements.append({"position":observation.get("position"),"zone":observation["zone"],
                    "reader_unit_id":observed,"tracking_unit_id":tracked,
                    "reader_confidence":observation.get("identity_confidence",0),"chosen_unit_id":identity})
            if identity:
                assignments.append((observation,identity))
        units,bench=[],[]
        incomplete=False
        for observation,identity in assignments:
            if observation.get("stars") not in (1,2,3) or observation.get("items") is None:
                incomplete=True
                continue
            unit={"unit_id":identity,"stars":observation["stars"],"items":observation["items"],"position":observation.get("position")}
            (bench if observation["zone"]=="bench" else units).append(unit)
        unpositioned=[]
        for identity,count in remaining.items():
            if count<=0:
                continue
            if not self.inventory_complete:
                unpositioned.append({"unit_id":identity,"copies":count,"stars":None,"items":None,"position":None})
                continue
            for stars in (3,2,1):
                copies=3**(stars-1)
                while count>=copies:
                    unpositioned.append({"unit_id":identity,"copies":copies,"stars":stars,"items":None,"position":None})
                    count-=copies
        fields={"tracked_units":unpositioned}
        if not incomplete and not unpositioned and len(assignments)==len(observations) and observations:
            fields["board"]={"units":units,"bench":bench,"trait_counts":None}
            fields["bench"]=bench
        return fields,disagreements
