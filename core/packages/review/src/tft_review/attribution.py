"""Shown-advice attribution from the UI's logged display acknowledgements.

Live delivery logs each delivered revision (`advice_delivery`), each surface
acknowledgement (`ui_show`) and each delivery that stopped applying before it
was shown (`advice_too_late`, `advice_paused`). Review joins those events to the
replayed decision by the Engine's semantic decision identity, falling back to
the delivered domain and snapshot inside the replay's decision segment. Follow
attribution requires an acknowledgement before the player's choice started.
Displays after that boundary remain recorded, with unknown following.
"""
from datetime import datetime
from collections.abc import Mapping


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
    if not isinstance(line, Mapping) or not horizon:
        return None
    initial = player['payload'].get('initial_level', 0)
    advised = {round_id: level for round_id, level in line.get('levels', {}).items()
        if round_id in horizon and level > initial}
    advised_rolls = {round_id: gold for round_id, gold in line.get('rolls', {}).items() if round_id in horizon}
    return advised == dict(player['payload'].get('levels', {})) and advised_rolls == dict(player['payload'].get('rolls', {}))


def same_choice(shown_option, shown_row, player):
    if player.get('action') == 'shop':
        shown = (shown_row or {}).get('payload', {}).get('buys')
        actual = player['payload'].get('buys')
        if shown is None or actual is None:
            return None
        identity = lambda rows: sorted((row['slot'], row['unit_id']) for row in rows)
        return identity(shown) == identity(actual)
    if player['option_id'] == shown_option:
        return True
    if player.get('action') == 'line':
        return _same_line(shown_row, player)
    follows = player.get('follows')
    if follows is not None:
        return shown_option in follows
    return False


def _before_action(show, player):
    """Compare display with onset evidence, falling back to a confirmed choice.

    Equal clocks require earlier logged display evidence. A missing sequence
    cannot establish that ordering; a strictly earlier timestamp still can.
    """
    if player is None:
        return False
    onset = player.get('observed_started_at')
    at = onset or player.get('observed_at')
    if at is None:
        return False
    display_at, action_at = _at(show['timestamp']), _at(at)
    if display_at != action_at:
        return display_at < action_at
    seq = player.get('observed_start_log_seq' if onset else 'observed_log_seq')
    return type(seq) is int and type(show.get('seq')) is int and show['seq'] < seq


def shown_status(display, record, *, mode, window, segment_snapshots, player, cost, close_call):
    """One shown-advice status per decision point.

    `window` is the replay segment's half-open time interval. A capture gap means
    no matching display acknowledgement exists. Known displays remain shown
    even when they cannot establish that the player followed them.
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
    if shows:
        causal = [event for event in shows if _before_action(event, player)]
        latest = max(causal or shows, key=lambda event: (_at(event['timestamp']), event['seq']))
        option = latest['payload']['option_id']
        followed = None if player is None or not causal else same_choice(option, display.row(latest), player)
        shown = {'shown_option_id': option, 'shown_at': latest['timestamp'],
            'delivery_revision': latest['payload']['delivery_revision'],
            'surfaces': sorted({event['payload']['surface'] for event in causal or shows
                if event['payload']['option_id'] == option}), 'followed': followed}
        if followed is None:
            reason = 'display_not_confirmed_before_policy_onset' if player is not None and not causal else 'player_choice_unavailable'
            return shown | {'status': 'shown', 'reason': reason}
        if not followed:
            return shown | {'status': 'ignored'}
        harmful = cost is not None and cost < 0 and not close_call
        return shown | {'status': 'engine_error' if harmful else 'followed'}
    delivered = [row for key in keys for row in display.delivered.get(key, ())]
    dropped = [event for key in keys for event in display.dropped.get(key, ())]
    if dropped:
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
