"""Offline tunable overlays preserve each game's historical static and source data."""
from dataclasses import replace
from tft_data.config import TUNABLE_FAMILIES, tagged
from tft_review.contracts import json_value
from tft_review.identity import digest


class TunableOverlay:
    def __init__(self, historical_store, fields, *, citation='unaccepted harness candidate'):
        self.historical_store = historical_store
        raw = {name: {'value': json_value(value), 'source': 'owner', 'citation': citation,
            'family': TUNABLE_FAMILIES.get(name)} for name, value in fields.items()}
        if set(raw)-set(TUNABLE_FAMILIES):
            raise ValueError('Candidate contains unknown tunables')
        self.fields = tagged(raw, 'harness candidate', families=TUNABLE_FAMILIES)
        self.identity = digest(self.fields)

    def get(self, snapshot_id):
        original = self.historical_store.get(snapshot_id)
        return replace(original, tunables=dict(original.tunables)|dict(self.fields))
