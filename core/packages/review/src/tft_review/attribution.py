"""Shown-advice attribution from the UI's logged display acknowledgements.

Live delivery logs each delivered revision (`advice_delivery`), each surface
acknowledgement (`ui_show`) and each delivery that stopped applying before it
was shown (`advice_too_late`, `advice_paused`). Review joins those events to the
replayed decision by the Engine's semantic decision identity, falling back to
the delivered domain and snapshot inside the replay's decision segment. Only an
acknowledgement logged before the player's confirmed choice counts as shown.
"""
from datetime import datetime


def _at(value):
    return datetime.fromisoformat(value)


class DisplayLog:
    """Index of one game's logged display evidence."""

    def __init__(self, observations):
        self.deliveries, self.delivered, self.shows, self.dropped = {}, {}, {}, {}
        for event in observations:
            payload = event['payload']
            if event['kind'] == 'advice_delivery':
                rows = payload.get('summary', {}).get('advice', ())
                self.deliveries[payload.get('delivery_revision')] = (event, rows)
                for row in rows:
                    self.delivered.setdefault(row.get('decision_id'), []).append((event, row))
            elif event['kind'] == 'ui_show' and payload.get('delivery_revision'):
                self.shows.setdefault(payload.get('decision_id'), []).append(event)
            elif event['kind'] in ('advice_too_late', 'advice_paused'):
                self.dropped.setdefault(payload.get('decision_id'), []).append(event)

    def keys(self, record, segment_snapshots):
        keys = {record.decision_id}
        for rows in self.delivered.values():
            for event, row in rows:
                if (row.get('domain') == record.decision
                        and event['payload'].get('snapshot_id') in segment_snapshots):
                    keys.add(row.get('decision_id'))
        return keys

    def row(self, show):
        delivery = self.deliveries.get(show['payload']['delivery_revision'])
        if delivery is None:
            return None
        return next((row for row in delivery[1] if row.get('decision_id') == show['payload']['decision_id']
            and row.get('option_id') == show['payload']['option_id']), None)


def _same_line(shown_row, player):
    """A followed Line repeats the shown schedule over the observed horizon."""
    line = (shown_row or {}).get('payload', {}).get('line')
    horizon = player['payload'].get('horizon_rounds')
    if not isinstance(line, dict) or not horizon:
        return None
    advised = {round_id: level for round_id, level in line.get('levels', {}).items() if round_id in horizon}
    advised_rolls = {round_id: gold for round_id, gold in line.get('rolls', {}).items() if round_id in horizon}
    return advised == dict(player['payload'].get('levels', {})) and advised_rolls == dict(player['payload'].get('rolls', {}))


def same_choice(shown_option, shown_row, player):
    if player['option_id'] == shown_option:
        return True
    if player.get('action') == 'line':
        return _same_line(shown_row, player)
    follows = player.get('follows')
    if follows is not None:
        return shown_option in follows
    return False


def shown_status(display, record, *, mode, window, segment_snapshots, player, cost, close_call):
    """One shown-advice status per decision point.

    `window` is the replay segment's half-open time interval. A capture gap means
    the coach would have said the Engine's choice but no acknowledgement reached
    the log before the player chose.
    """
    if mode == 'baseline':
        return {'status': 'no_advice_in_baseline_mode'}
    if mode == 'silent':
        return {'status': 'no_advice_in_silent_mode'}
    start, stop = window
    keys = display.keys(record, segment_snapshots)
    shows = [event for key in keys for event in display.shows.get(key, ())
        if display.row(event) is not None and _at(event['timestamp']) >= start
        and (stop is None or _at(event['timestamp']) < stop)]
    chosen_at = _at(player['observed_at']) if player and player.get('observed_at') else None
    before = [event for event in shows if chosen_at is None or _at(event['timestamp']) <= chosen_at]
    if before:
        latest = max(before, key=lambda event: (_at(event['timestamp']), event['seq']))
        option = latest['payload']['option_id']
        followed = None if player is None else same_choice(option, display.row(latest), player)
        shown = {'shown_option_id': option, 'shown_at': latest['timestamp'],
            'delivery_revision': latest['payload']['delivery_revision'],
            'surfaces': sorted({event['payload']['surface'] for event in before
                if event['payload']['option_id'] == option}), 'followed': followed}
        if followed is None:
            return shown | {'status': 'shown', 'reason': 'player_choice_unavailable'}
        if not followed:
            return shown | {'status': 'ignored'}
        harmful = cost is not None and cost < 0 and not close_call
        return shown | {'status': 'engine_error' if harmful else 'followed'}
    delivered = [row for key in keys for row in display.delivered.get(key, ())]
    dropped = [event for key in keys for event in display.dropped.get(key, ())]
    if shows:
        cause = 'shown_after_choice'
    elif dropped:
        cause = dropped[0]['kind']
    elif delivered:
        cause = 'delivered_not_shown'
    else:
        cause = 'not_delivered'
    return {'status': 'capture_gap', 'cause': cause,
        'would_have_said': record.advice.get('option_id'), 'followed': None}


def follow_rate(statuses):
    eligible = [status for status in statuses if status.get('followed') is not None]
    followed = sum(status['followed'] for status in eligible)
    if not eligible:
        return {'value': None, 'reason': 'no_shown_advice_with_known_choice', 'eligible': 0, 'followed': 0}
    return {'value': followed/len(eligible), 'reason': None, 'eligible': len(eligible), 'followed': followed}
