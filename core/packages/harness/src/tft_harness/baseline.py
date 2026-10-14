"""Qualified owner baseline, frozen from the latest current-set ranked matches."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
import re


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()


def _aware(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Baseline refresh time requires a timezone')
    return result


def _match(row, owner_puuid, platform):
    try:
        identity = row['metadata']['match_id']
        match = re.fullmatch(rf'{re.escape(platform.upper())}_([1-9][0-9]*)', identity)
        info = row['info']
        if not match:
            raise ValueError('Match ID does not follow the configured platform/numeric join')
        for name in ('queue_id', 'tft_set_number', 'game_datetime'):
            if type(info[name]) is not int or info[name] <= 0:
                raise ValueError('Match integer metadata invalid')
        length = info['game_length']
        if type(length) not in (int, float) or not isfinite(length) or length <= 0:
            raise ValueError('Finished match duration unavailable')
        participants = info['participants']
        if not isinstance(participants, list) or len(participants) != 8:
            raise ValueError('Finished match requires all eight participants')
        if len({participant['puuid'] for participant in participants}) != 8:
            raise ValueError('Duplicate participant identity')
        placements = []
        for participant in participants:
            if not isinstance(participant['puuid'], str) or not participant['puuid']:
                raise ValueError('Participant identity unavailable')
            placement = participant['placement']
            if type(placement) is not int or not 1 <= placement <= 8:
                raise ValueError('Final placement invalid')
            placements.append(placement)
            if not isinstance(participant['units'], list) or not isinstance(participant['traits'], list):
                raise ValueError('Final board lists unavailable')
        if set(placements) != set(range(1, 9)):
            raise ValueError('Final elimination ordering invalid')
        own = [participant for participant in participants if participant['puuid'] == owner_puuid]
        if len(own) != 1:
            raise ValueError('Owner absent from match')
        return {'game_id': match.group(1), 'placement': own[0]['placement'],
            'date': datetime.fromtimestamp(info['game_datetime']/1000, timezone.utc)}
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError('Qualified baseline match schema unavailable') from error


def qualify_baseline(source_matches, *, owner_puuid, set_number, rank, logged_games=(),
                     refreshed_at, platform='eun1'):
    """Validate external responses and recompute eligibility, rather than trust counts."""
    if not isinstance(owner_puuid, str) or not owner_puuid or type(set_number) is not int or set_number < 1:
        raise ValueError('Qualified owner and current set are required')
    refreshed = _aware(refreshed_at)
    # Materialize finite private evidence. No key/token is part of this manifest.
    source_matches = json.loads(json.dumps(list(source_matches), allow_nan=False))
    if not 50 <= len(source_matches) <= 1000:
        raise ValueError('Qualified baseline requires at least 50 owner matches (maximum 1000)')
    ranks = [row for row in rank if row.get('queueType') == 'RANKED_TFT']
    if len(ranks) != 1 or not all(isinstance(ranks[0].get(name), str) and ranks[0][name]
        for name in ('tier', 'rank')) or type(ranks[0].get('leaguePoints')) is not int or ranks[0]['leaguePoints'] < 0:
        raise ValueError('Qualified current ranked TFT rank is unavailable')
    games = {str(game['game_id']): game for game in logged_games}
    eligible, excluded, identities = [], Counter(), set()
    for row in source_matches:
        result = _match(row, owner_puuid, platform)
        identity = row['metadata']['match_id']
        if identity in identities:
            raise ValueError('Duplicate baseline match')
        identities.add(identity)
        if result['date'] > refreshed:
            raise ValueError('Baseline includes a future match')
        if row['info']['queue_id'] != 1100:
            excluded['wrong_queue'] += 1
        elif row['info']['tft_set_number'] != set_number:
            excluded['wrong_set'] += 1
        elif result['game_id'] in games and games[result['game_id']]['mode'] != 'silent':
            excluded['coached'] += 1
        else:
            eligible.append((result['date'], int(result['game_id']), row, result['placement']))
    eligible.sort(key=lambda row: (row[0], row[1]), reverse=True)
    if len(eligible) < 50:
        raise ValueError(f'Qualified baseline has only {len(eligible)} eligible current-set ranked games; requires 50')
    chosen = eligible[:50]
    body = {'schema_version': 1, 'source': 'riot_owner_match_details', 'owner_puuid': owner_puuid,
        'set_number': set_number, 'queue_id': 1100, 'platform': platform,
        'refreshed_at': refreshed_at, 'game_count': 50,
        'average_placement': sum(row[3] for row in chosen)/50,
        'rank': dict(ranks[0]), 'rank_response': list(rank),
        'matches': [row[2] for row in chosen], 'source_matches': source_matches,
        'excluded': dict(excluded),
        'join_contract': 'configured-platform numeric game ID; actual-client qualification is separate'}
    return body | {'evidence_hash': _digest(body)}


def validate_baseline(baseline, *, set_id, logged_games):
    """Storage revalidates the raw sample and its current authoritative mode ledger."""
    if not isinstance(baseline, dict) or baseline.get('schema_version') != 1 or 'source_matches' not in baseline:
        raise ValueError('start-run requires a qualified owner baseline, not a shallow count/average/rank manifest')
    if str(baseline.get('set_number')) != str(set_id):
        raise ValueError('Qualified baseline belongs to another set')
    expected = qualify_baseline(baseline['source_matches'], owner_puuid=baseline['owner_puuid'],
        set_number=baseline['set_number'], rank=baseline['rank_response'], logged_games=logged_games,
        refreshed_at=baseline['refreshed_at'], platform=baseline['platform'])
    if expected != baseline:
        raise ValueError('Qualified baseline evidence or current mode eligibility changed; refresh it')
    return expected
