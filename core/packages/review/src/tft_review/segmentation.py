"""Conservative semantic segmentation that retains the original capture ledger."""
from datetime import datetime

from tft_engine.planning import field_age
from tft_engine.registry import evaluation_dependency_fields

from .contracts import json_value
from .identity import digest

# Display acknowledgements and media do not change Engine information. Captured
# actions, sightings, gaps and outcomes do, even when the next shop looks alike.
_NON_INPUT_EVENTS = {'snapshot', 'keyframe', 'video', 'ui_show', 'preview_shown', 'advice_delivery',
    'replay_cache', 'capture_status', 'reader_tracker_disagreement'}


def semantic_fingerprint(snapshot, data, events, through_seq, *, hooks=None):
    fields = {}
    dependencies = evaluation_dependency_fields(hooks)
    for name in dependencies:
        field = snapshot.fields.get(name)
        if field is None:
            continue
        fields[name] = {'value': json_value(field.value), 'source': field.source,
            'confidence': field.confidence,
            'fresh': field.age_seconds(snapshot.captured_at) <= field_age(data, name, snapshot)}
    settled = snapshot.fields.get('board_settled_since')
    if 'board_settled_since' in fields and settled and isinstance(settled.value, str):
        at = datetime.fromisoformat(settled.value)
        delay = data.tunables['board_settle_seconds'].value
        fields['board_settled_since']['settled'] = (snapshot.captured_at-at).total_seconds() >= delay
    causal = [(event['seq'], event['kind']) for event in events
        if event['seq'] <= through_seq and event['kind'] not in _NON_INPUT_EVENTS
        and datetime.fromisoformat(event['timestamp']) <= snapshot.captured_at]
    return digest({'round': snapshot.round_id, 'fields': fields, 'causal_inputs': causal})
