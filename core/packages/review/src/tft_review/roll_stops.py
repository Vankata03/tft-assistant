"""Certify inferred action programs without inferring player intent.

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
    _certify_financial_horizon(batch, context, data, horizon_end)
    if not rolls:
        return {}, ()
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


def _certify_financial_horizon(batch, context, data, end):
    """Account for the entire program interval, including time between bursts.

    Later finances qualify the action ledger only; they never seed valuation.
    Unknown income, XP spending or unobserved intervals cannot prove no refresh.
    """
    from math import floor
    rows = [row for row in batch.contexts if context.log_seq <= row.log_seq <= end]
    rules = data.value('rules_flags')
    order = tuple(data.value('round_order'))
    previous = None
    ownership = None
    def total_xp(fields):
        table = data.value('xp_table')
        return sum(table[str(level)] for level in range(1, fields['level'])) + fields['xp']
    for row in rows:
        state = GameSnapshot.from_dict(json_value(row.snapshot))
        names = ('gold','xp','level','streak','owned_copies','inventory_complete',
                 'remaining_effects','remaining_effects_complete','held_augments','held_augments_complete')
        values = {name: read(state,data,name) for name in names}
        if (any(value is None for value in values.values())
            or any(not 0 <= (state.captured_at-state.fields[name].read_at).total_seconds() <= .5 for name in names)
            or state.fields['gold'].read_at != state.captured_at
            or values['inventory_complete'] is not True or values['remaining_effects_complete'] is not True
            or values['remaining_effects'] or values['held_augments_complete'] is not True):
            raise DataError('observed_roll_horizon_coverage_unavailable')
        captured(state,data)
        if previous:
            prior, old, seq = previous
            if not 0 < (state.captured_at-prior.captured_at).total_seconds() <= 2:
                raise DataError('observed_roll_horizon_coverage_unavailable')
            events = [event for event in batch.observations if seq < event['seq'] < row.log_seq]
            if any(event['kind'] in ('sell','unit_grant','wisp_purchase','capture_gap','tracking_ambiguity') for event in events):
                raise DataError('observed_roll_ledger_unsupported')
            spending = 0
            acquired = Counter()
            for event in events:
                if event['kind'] in ('roll','purchase'):
                    cost = event['payload'].get('cost')
                    if type(cost) is not int or cost < 0 or event['timestamp'] != row.timestamp:
                        raise DataError('observed_roll_ledger_unsupported')
                    spending += cost
                    if event['kind'] == 'purchase':
                        acquired[event['payload']['unit_id']] += event['payload']['copies']
            income = passive = 0
            if state.round_id != prior.round_id:
                if order.index(state.round_id) != order.index(prior.round_id)+1:
                    raise DataError('observed_roll_horizon_coverage_unavailable')
                # PvE grants with unknown gold cannot establish a financial ledger.
                # PvP needs a positively observed result and resulting streak.
                kind = data.value('round_types')[prior.round_id]
                won = False
                if kind == 'pve':
                    if rules['pve_orb_gold'].get(prior.round_id, 0):
                        raise DataError('observed_roll_income_unavailable')
                    expected_streak = old['streak'] if rules['pve_preserves_streak'] else 0
                elif kind == 'pvp':
                    results = [event for event in events if event['kind']=='fight_result'
                               and event['payload'].get('round_id') == prior.round_id]
                    if len(results) != 1 or results[0]['payload'].get('result') not in ('win','loss'):
                        raise DataError('observed_roll_income_unavailable')
                    won = results[0]['payload']['result'] == 'win'
                    expected_streak = max(0,old['streak'])+1 if won else min(0,old['streak'])-1
                else:
                    raise DataError('observed_roll_income_unavailable')
                if values['streak'] != expected_streak:
                    raise DataError('observed_roll_income_unavailable')
                interest = data.value('interest')
                streak = max(((int(threshold),amount) for threshold,amount in data.value('streak_gold').items()
                              if abs(expected_streak)>=int(threshold)), default=(0,0))[1]
                base = data.value('gold_by_round')
                income = (base.get(prior.round_id,base.get('default',0))
                          + min(floor(old['gold']/interest['gold_per_tick'])*interest['gold_per_interest'],interest['cap'])
                          + streak + won*rules['combat_win_gold'])
                passive = rules['passive_xp']
            elif values['streak'] != old['streak']:
                # Combat rewards arriving separately need their own observed boundary.
                raise DataError('observed_roll_income_unavailable')
            purchased_xp = total_xp(values)-total_xp(old)-passive
            if purchased_xp < 0 or purchased_xp % rules['xp_buy_amount']:
                raise DataError('observed_roll_xp_ledger_unsupported')
            if purchased_xp and not any(event['kind']=='level_up' for event in events):
                raise DataError('observed_roll_xp_action_unsupported')
            spending += purchased_xp/rules['xp_buy_amount']*rules['xp_buy_cost']
            if values['gold'] != old['gold']+income-spending:
                raise DataError('observed_roll_ledger_unsupported')
        # Shop polls carry bounded older ownership. Reconcile the entire interval
        # between complete reads, including purchases before intermediate polls.
        if state.fields['owned_copies'].read_at == state.captured_at:
            if ownership is not None:
                copies, seq = ownership
                acquired = Counter()
                for event in batch.observations:
                    if seq < event['seq'] < row.log_seq and event['kind']=='purchase':
                        acquired[event['payload']['unit_id']] += event['payload']['copies']
                if Counter(values['owned_copies']) != copies+acquired:
                    raise DataError('observed_roll_ownership_unsupported')
            ownership = Counter(values['owned_copies']), row.log_seq
        previous = state, values, row.log_seq
