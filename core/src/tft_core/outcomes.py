"""Validated post-game facts. Missing fields never become inferred outcomes.

The private artifact contains only the match identity and whitelisted final
facts. Placement orders the elimination list; it does not establish the timing
of simultaneous eliminations or any player's last observed board position.
"""
from hashlib import sha256
import json
from math import isfinite
import re


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _integer(value, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError('Outcome integer field invalid')
    return value


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Outcome identity field unavailable')
    return value


def qualify_outcome(raw, *, game_id, owner_puuid, set_number, queue_id=None, platform='eun1'):
    """Join a complete Riot match response to the original capture identity."""
    try:
        game_id = str(game_id)
        if not re.fullmatch(r'[1-9][0-9]*', game_id) or not re.fullmatch(r'[a-zA-Z0-9]+', platform):
            raise ValueError('Outcome game identity invalid')
        match_id = f'{platform.upper()}_{game_id}'
        if raw['metadata']['match_id'] != match_id:
            raise ValueError('Outcome belongs to another match')
        info = raw['info']
        queue = _integer(info['queue_id'], 1)
        current_set = _integer(info['tft_set_number'], 1)
        if current_set != _integer(set_number, 1) or (queue_id is not None and queue != queue_id):
            raise ValueError('Outcome set or queue conflicts with capture')
        rows = info['participants']
        if not isinstance(rows, list) or len(rows) != 8:
            raise ValueError('Outcome requires all eight final participants')
        participants = []
        for row in rows:
            units, traits = row['units'], row['traits']
            if not isinstance(units, list) or not isinstance(traits, list):
                raise ValueError('Outcome final board lists unavailable')
            board = []
            for unit in units:
                items = unit.get('itemNames', unit.get('items'))
                if not isinstance(items, list) or any(
                    not ((type(item) is int and item >= 0) or (isinstance(item, str) and item.strip()))
                    for item in items
                ):
                    raise ValueError('Outcome unit items unavailable')
                board.append({'character_id': _text(unit['character_id']),
                    'tier': _integer(unit['tier'], 1, 4), 'items': items})
            final_traits = [{'name': _text(trait['name']),
                **{name: _integer(trait[name]) for name in ('num_units', 'style', 'tier_current', 'tier_total')}}
                for trait in traits]
            participant = {'participant_id': _text(row['puuid']),
                'placement': _integer(row['placement'], 1, 8), 'units': board, 'traits': final_traits}
            if 'last_round' in row:
                participant['last_round'] = _integer(row['last_round'])
            if 'time_eliminated' in row:
                value = row['time_eliminated']
                if type(value) not in (int, float) or not isfinite(value) or value < 0:
                    raise ValueError('Outcome elimination time invalid')
                participant['time_eliminated'] = value
            participants.append(participant)
        if len({row['participant_id'] for row in participants}) != 8 or {row['placement'] for row in participants} != set(range(1, 9)):
            raise ValueError('Outcome identities or final placements are not unique')
        own = [row for row in participants if row['participant_id'] == _text(owner_puuid)]
        if len(own) != 1:
            raise ValueError('Outcome owner absent')
        participants.sort(key=lambda row: row['placement'])
        body = {'schema_version': 1, 'game_id': game_id, 'match_id': match_id,
            'source': 'riot_match', 'queue_id': queue, 'set_number': current_set,
            'owner_id': owner_puuid, 'placement': own[0]['placement'], 'participants': participants,
            'elimination_order': [row['participant_id'] for row in reversed(participants)],
            'elimination_order_source': 'final_placement'}
        # Copy external mutable containers and reject non-finite JSON before publication.
        body = json.loads(json.dumps(body, allow_nan=False))
        return body | {'evidence_hash': _digest(body)}
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Outcome match schema unavailable') from error


def validate_outcome(value, *, game_id, set_number, queue_id=None):
    """Revalidate stored bytes and the capture join whenever truth is consumed."""
    try:
        participants = [{**row, 'puuid': row['participant_id']} for row in value['participants']]
        expected = qualify_outcome({'metadata': {'match_id': value['match_id']},
            'info': {'queue_id': value['queue_id'], 'tft_set_number': value['set_number'],
                'participants': participants}}, game_id=game_id, owner_puuid=value['owner_id'],
            set_number=set_number, queue_id=queue_id, platform=value['match_id'].split('_')[0])
        if expected != value:
            raise ValueError('Outcome evidence changed or schema unavailable')
        return expected
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Outcome artifact schema unavailable') from error


class OutcomeCollector:
    """Owner-scoped match collection on the review identity worker, never capture.

    Configuration is private ``outcome-source.json`` with ``owner_puuid``,
    ``platform`` and ``region``. The frozen EUNE baseline can supply the owner
    and routing after start-run. No account discovery or speculative match fetch
    is allowed: the match must first appear on that owner's match-id endpoint.
    """

    def __init__(self, sessions, *, client=None, client_factory=None):
        self.sessions = sessions
        self.client = client
        self.client_factory = client_factory
        self._configured_client = None
        self._source_key = None

    def status(self, game_id):
        game_id = str(game_id)
        if not re.fullmatch(r'[1-9][0-9]*', game_id):
            raise ValueError('Outcome game identity invalid')
        path = self.sessions.root/'outcome-status'/f'{game_id}.json'
        return json.loads(path.read_text()) if path.exists() else None

    def collect(self, game_id):
        from tft_data.models import DataError
        from tft_data.riot import RiotClient
        from .review_lease import atomic_record

        game_id = str(game_id)
        previous = self.status(game_id)
        status = {'game_id': game_id, 'attempts': (previous or {}).get('attempts', 0) + 1,
            'configured': False,
            'state': 'unavailable', 'reason': 'Configure private outcome-source.json with owner_puuid, platform and region, or start the EUNE run'}
        if self.sessions.read_outcome(game_id) is not None:
            status.update(state='confirmed', reason=None)
        else:
            try:
                path = self.sessions.config_root/'outcome-source.json'
                status['configured'] = path.exists() or self.sessions.run is not None
                source = json.loads(path.read_text()) if path.exists() else (self.sessions.run or {}).get('baseline')
                if source:
                    status['configured'] = True
                    owner, platform = _text(source['owner_puuid']), _text(source['platform'])
                    region = source.get('region', 'europe' if platform.lower() == 'eun1' else None)
                    if region is None:
                        raise ValueError('Explicit outcome routing region required')
                    source_key = (owner, platform, region)
                    if self.client is None and source_key != self._source_key:
                        self._configured_client = (self.client_factory or RiotClient)(
                            key_path=self.sessions.config_root/'riot-api-key', platform=platform, region=region)
                        self._source_key = source_key
                    client = self.client or self._configured_client
                    # RiotClient also validates configured routing when HTTP is injected.
                    if client.platform != platform or client.region != region:
                        raise ValueError('Outcome source and client routing conflict')
                    client.owner_puuid = owner
                    match_id = f'{platform.upper()}_{game_id}'
                    if match_id not in client.match_ids(count=100):
                        status.update(state='pending', reason='Finished match not yet present in owner history; retry pending')
                    else:
                        client.sleep(1.25)
                        self.sessions.record_outcome(game_id, client.match(match_id), owner_puuid=owner, platform=platform)
                        status.update(state='confirmed', reason=None)
            except DataError:
                status.update(state='pending', reason='Owner match API unavailable; check local key, connectivity and routing; retry pending')
            except (OSError, ValueError, KeyError, TypeError):
                status.update(state='unavailable', reason='Outcome configuration or match evidence invalid; last-good facts preserved; review private source and retry')
        atomic_record(self.sessions.root/'outcome-status'/f'{game_id}.json', status)
        return status
