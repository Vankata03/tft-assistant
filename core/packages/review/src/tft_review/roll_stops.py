"""Certify bounded observed refresh programs, without inferring player intent.

An idle boundary identifies an ex-post action count, not a chosen gold floor.
Only continuously sampled, complete ownership/shop/gold ledgers with positively
empty remaining effects and a complete augment inventory qualify in this first supported path.
"""
from collections import Counter
from datetime import datetime, timedelta

from tft_data import DataError
from tft_engine import GameSnapshot
from tft_engine.planning import read
from tft_engine.lines import horizon_rounds
from tft_engine.effects import captured

from .contracts import json_value


def certify_roll_stops(batch, context, data, actions):
    rolls = [event for event in actions if event['kind'] == 'roll']
    if not rolls:
        return {}, ()
    original = batch.snapshot_for(context)
    if any(read(original,data,name) != expected for name,expected in
        (('remaining_effects_complete',True),('remaining_effects',()),
         ('held_augments_complete',True))) or read(original,data,'held_augments') is None:
        raise DataError('observed_roll_effects_unavailable')
    captured(original,data) # Reject held recurring effects omitted from the claimed empty inventory.
    horizon_end = max(row.log_seq for row in batch.contexts
        if row.log_seq >= context.log_seq and row.snapshot['round_id'] in horizon_rounds(original,data))
    if any(event['kind'] == 'tracking_ambiguity' and context.log_seq < event['seq'] <= horizon_end
        for event in batch.observations):
        raise DataError('observed_roll_ledger_unsupported')
    if data.value('rules_flags')['roll_cost'] != 2:
        raise DataError('observed_roll_cost_unsupported')
    groups = []
    for event in rolls:
        if (not groups or event['payload'].get('round_id') != groups[-1][-1]['payload'].get('round_id')
            or (_at(event)-_at(groups[-1][-1])).total_seconds() >= 3):
            groups.append([])
        groups[-1].append(event)
    counts, certificates = {}, []
    for group in groups:
        first, last = group[0], group[-1]
        round_id = first['payload'].get('round_id')
        before = [row for row in batch.contexts if context.log_seq <= row.log_seq < first['seq']
            and row.snapshot['round_id'] == round_id and datetime.fromisoformat(row.timestamp) < _at(first)
            and row.snapshot['fields'].get('owned_copies',{}).get('read_at') == row.timestamp]
        after = [row for row in batch.contexts if row.log_seq > last['seq']
            and row.snapshot['round_id'] == round_id and datetime.fromisoformat(row.timestamp) >= _at(last)+timedelta(seconds=3)
            and row.snapshot['fields'].get('owned_copies',{}).get('read_at') == row.timestamp]
        if not before or not after:
            raise DataError('observed_roll_stop_unconfirmed')
        begin, end = before[-1], after[0]
        samples = [row for row in batch.contexts if begin.log_seq <= row.log_seq <= end.log_seq]
        ledger = [event for event in batch.observations if begin.log_seq < event['seq'] < end.log_seq]
        paid = [event for event in ledger if event['kind'] == 'roll']
        if [event['seq'] for event in paid] != [event['seq'] for event in group]:
            raise DataError('observed_roll_stop_unconfirmed')
        if any(event['payload'].get('cost') != 2 for event in paid):
            raise DataError('observed_roll_cost_unsupported')
        if any(event['kind'] in ('capture_gap','tracking_ambiguity','level_up','sell','unit_grant','wisp_purchase') for event in ledger):
            raise DataError('observed_roll_ledger_unsupported')
        previous = ownership = None
        max_interval = 0.
        for row in samples:
            state = GameSnapshot.from_dict(json_value(row.snapshot))
            names = ('gold','shop','slot_count','level','xp','inventory_complete','owned_copies',
                'phase','planning_phase','board','bench','remaining_effects','remaining_effects_complete','held_augments','held_augments_complete')
            fields = {name: read(state,data,name) for name in names}
            if (state.round_id != round_id or any(value is None for value in fields.values())
                or any(not 0 <= (state.captured_at-state.fields[name].read_at).total_seconds() <= .5 for name in names)
                or any(state.fields[name].read_at != state.captured_at for name in ('gold','shop'))
                or fields['planning_phase'] is not True or fields['phase'] not in ('planning','roll_down')
                or fields['inventory_complete'] is not True
                or fields['remaining_effects_complete'] is not True or fields['remaining_effects']
                or fields['held_augments_complete'] is not True):
                raise DataError('observed_roll_coverage_unavailable')
            captured(state,data)
            if previous:
                prior, values, seq = previous
                interval = (state.captured_at-prior.captured_at).total_seconds()
                if not 0 < interval <= .5:
                    raise DataError('observed_roll_coverage_unavailable')
                max_interval = max(max_interval, interval)
                events = [event for event in ledger if seq < event['seq'] < row.log_seq]
                refreshes = [event for event in events if event['kind'] == 'roll']
                purchases = [event for event in events if event['kind'] == 'purchase']
                spent = sum(event['payload']['cost'] for event in refreshes+purchases)
                for event in refreshes+purchases:
                    if event['timestamp'] != row.timestamp:
                        raise DataError('observed_roll_ledger_unsupported')
                for event in purchases:
                    payload = event['payload']
                    if payload.get('copies') != 1 or type(payload.get('cost')) is not int or payload['cost'] < 0:
                        raise DataError('observed_roll_ledger_unsupported')
                if (fields['gold'] != values['gold']-spent
                    or fields['level'] != values['level'] or fields['xp'] != values['xp']
                    or (fields['shop'] != values['shop'] and not refreshes and not purchases)):
                    raise DataError('observed_roll_ledger_unsupported')
            # Shop-only high-rate polls retain the last regular ownership read.
            # Reconcile its complete ledger when the next complete read arrives.
            if state.fields['owned_copies'].read_at == state.captured_at:
                if ownership is not None:
                    copies, seq = ownership
                    acquired = Counter()
                    for event in ledger:
                        if seq < event['seq'] < row.log_seq and event['kind'] == 'purchase':
                            acquired[event['payload']['unit_id']] += event['payload']['copies']
                    if Counter(fields['owned_copies']) != copies+acquired:
                        raise DataError('observed_roll_ownership_unsupported')
                ownership = Counter(fields['owned_copies']), row.log_seq
            previous = state, fields, row.log_seq
        counts[round_id] = counts.get(round_id,0)+len(paid)
        certificates.append({'reason':'observed_idle_3s','complete':True,'round_id':round_id,
            'start_at':begin.timestamp,'last_roll_at':last['timestamp'],'end_at':end.timestamp,
            'start_log_seq':begin.log_seq,'end_log_seq':end.log_seq,'sample_count':len(samples),
            'max_interval_seconds':max_interval,'paid_roll_count':len(paid),
            'purchase_count':sum(event['kind']=='purchase' for event in ledger),
            'roll_log_seqs':[event['seq'] for event in paid],
            'ownership_support':'fresh_complete_inventory_and_confirmed_purchase_ledger',
            'policy':'observed_paid_refresh_count_no_inferred_floor'})
    return counts, tuple(certificates)


def _at(event):
    return datetime.fromisoformat(event['timestamp'])
