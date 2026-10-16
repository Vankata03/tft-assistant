"""Read-only Live display projections from qualified capture and shared models."""
from collections.abc import Mapping
from tft_data.models import DataError
from tft_engine.lobby import alive_lobby
from tft_engine.opponents import opponents_from_history, round_index
from tft_engine.planning import read, required, owned_board, observed_phase, causal_history
from tft_engine.power import estimate_strength, win_probability, static
from tft_engine.shop_math import key_goals, hit_probability, owned_copies, canonical_id


def opponent_rows(snapshot, history, data):
    if data is None:
        return []
    lobby = read(snapshot, data, 'lobby')
    lobby = lobby if isinstance(lobby, Mapping) else {}
    own = read(snapshot, data, 'player_id') or read(snapshot, data, 'local_player_id')
    ids = {id for id,row in lobby.items() if id != own and not (isinstance(row,Mapping) and row.get('is_self'))}
    sightings = {}
    causal_sightings = []
    for sighting in history.sightings:
        if ((sighting.read_at is None or sighting.read_at <= snapshot.captured_at)
            and round_index(sighting.round_id,data) <= round_index(snapshot.round_id,data)):
            causal_sightings.append(sighting)
            old = sightings.get(sighting.opponent_id)
            if old is None or (round_index(sighting.round_id,data),sighting.read_at or snapshot.captured_at) >= (round_index(old.round_id,data),old.read_at or snapshot.captured_at):
                sightings[sighting.opponent_id] = sighting
    ids |= set(sightings)
    eligible = None
    try:
        alive = alive_lobby(snapshot,data)
        count = static(data,'rules_flags').get('recent_opponent_exclusion_count')
        certificate = snapshot.fields.get('recent_opponent_fights_complete')
        fights = snapshot.field('recent_opponent_fights')
        if type(count) is not int or count < 0 or not certificate or certificate.value is not True or certificate.read_at > snapshot.captured_at or not isinstance(fights,(tuple,list)) or len(fights)<count:
            raise DataError('Confirmed matchup history/policy unavailable')
        recent = {row['opponent_id'] for row in fights[-count:]} if count else set()
        eligible = set(alive)-recent
        if not eligible:
            eligible = None
    except (DataError, KeyError, TypeError, ValueError):
        pass
    own_power = None
    if not required(snapshot,data,('board','bench','inventory_complete','level')):
        try:
            own_power = estimate_strength(owned_board(snapshot,data),int(read(snapshot,data,'level')),data).power
        except (DataError,KeyError,ValueError,TypeError):
            pass
    estimates = {}
    model_reason = None
    try:
        causal = type(history)(snapshots=tuple(s for s in history.snapshots if s.captured_at<=snapshot.captured_at),sightings=tuple(causal_sightings))
        estimates = {row.opponent_id:row for row in opponents_from_history(causal,snapshot.round_id,data,opponent_ids=ids)}
    except (DataError,KeyError,ValueError,TypeError) as error:
        model_reason = str(error)
    rows = []
    for id in sorted(ids):
        sighting,estimate = sightings.get(id),estimates.get(id)
        age = round_index(snapshot.round_id,data)-round_index(sighting.round_id,data) if sighting else None
        probability = (1/len(eligible) if id in eligible else 0.) if eligible is not None else None
        lobby_row = lobby.get(id)
        name = lobby_row.get('name',id) if isinstance(lobby_row,Mapping) else id
        traits = dict(sighting.traits) if sighting else None
        threats = set()
        for trait,count in (traits or {}).items():
            entity=data.entities.get(trait)
            thresholds=entity.values.get('threat_breakpoints') if entity else None
            for tag in entity.threat_tags if entity else ():
                threshold=thresholds.value.get(tag) if thresholds and isinstance(thresholds.value,Mapping) else None
                if type(threshold) is int and threshold>0 and count>=threshold:
                    threats.add(tag)
        threats=sorted(threats)
        chance = win_probability(own_power,estimate.power,int(snapshot.round_id.split('-')[0]),data) if own_power is not None and estimate else None
        rows.append({'opponent_id':id,'name':name,'player_row_index':lobby_row.get('row') if isinstance(lobby_row,Mapping) else None,'age_rounds':age,'read_at':sighting.read_at.isoformat() if sighting and sighting.read_at else None,
            'traits':traits,'threat_tags':threats,'next_probability':probability,'win_probability':chance,
            'inference_certainty':estimate.inference_certainty if estimate else None,
            'confidence':estimate.confidence if estimate else None,'level':estimate.level if estimate else None,
            'expected_unit_count':getattr(estimate,'expected_unit_count',None),
            'unit_probabilities':dict(estimate.probabilities) if estimate else {},
            'warnings':list(estimate.warnings) if estimate else [model_reason or 'Opponent model unavailable'],
            'scout_due':bool(probability is not None and probability>=.13 and (age is None or age>=3))})
    return rows


def roll_tracker(snapshot, data, result):
    if data is None or read(snapshot,data,'roll_down') is not True:
        return None
    econ = next((row for row in result.advice if row.decision=='econ' and not row.payload.get('paused')),None)
    if econ is None or required(snapshot,data,('gold','level','shop','board','bench','inventory_complete')):
        return {'available':False,'reason':'Complete current ownership, gold, shop and Line required'}
    floor = read(snapshot,data,'roll_down_floor')
    if type(floor) not in (int,float) or floor<0 or result.plan.target not in data.guides:
        return {'available':False,'reason':'Confirmed roll-down floor unavailable'}
    from tft_engine.effects import captured
    try:
        from tft_engine.lines import SimulationEffects
        effects=captured(snapshot,data) or SimulationEffects()
    except (DataError,KeyError,ValueError,TypeError) as error:
        return {'available':False,'reason':str(error)}
    rules=static(data,'rules_flags')
    cost=float(rules['roll_cost'])+effects.roll_cost_delta+float(effects.round_modifiers.get(snapshot.round_id,{}).get('roll_cost_delta',0))
    if cost<=0:
        return {'available':False,'reason':'Qualified positive roll cost unavailable'}
    rolls=int(max(0,(float(read(snapshot,data,'gold'))-float(floor))//cost))+effects.free_rolls
    owned=read(snapshot,data,'owned_copies')
    if not isinstance(owned,Mapping) or any(type(count) is not int or count<0 for count in owned.values()):return {'available':False,'reason':'Confirmed current copy ledger unavailable'}
    shop=read(snapshot,data,'shop')
    slots=read(snapshot,data,'slot_count')
    if slots is None:
        return {'available':False,'reason':'Shop slot count unavailable'}
    rows=[]
    for id,goal in key_goals(data.guides[result.plan.target],data).items():
        rows.append({'unit_id':id,'copies':owned.get(id,0),'goal':goal,
            'in_shop':any(canonical_id(row['unit_id'],data)==id for row in shop),
            'hit_probability':hit_probability(id,max(0,goal-owned.get(id,0)),rolls,float(slots),int(read(snapshot,data,'level')),data,owned=owned)})
    return {'available':True,'gold_floor':floor,'rolls_left':rolls,'units':rows,'source':'qualified-own-ownership-and-Line-floor'}


PLANNING_FIELDS = ('board', 'bench', 'gold', 'hp', 'level', 'xp', 'streak', 'lobby')
UNAVAILABLE = {'comp_id': None, 'line_id': None, 'pinned': False, 'planning_round': None,
               'planning_snapshot_id': None, 'round_id': None, 'level': None, 'gold_floor': None,
               'evidence_path': ['plan', 'line']}


def next_planning_preview(snapshot, history, data, result):
    """Combat's one-chip preview of the next planning call.

    It names the next scheduled level or roll-down point of the Line the Engine
    selected in a qualified planning phase of this same round. It describes that
    schedule only; future gold, HP and board state are never projected.
    """
    if data is None or observed_phase(snapshot, data) != 'combat':
        return None
    def unavailable(reason):
        return UNAVAILABLE | {'available': False, 'reason': reason}
    plan = result.plan
    econ = next((row for row in result.advice if row.decision == 'econ'), None)
    # The combat gate pauses econ naming the phase or the unread fields. Any
    # other pause is an evaluation failure, so the folded plan is not certified.
    if econ is None or not econ.payload.get('paused') or not econ.payload.get('missing'):
        return unavailable('Planning evaluation unavailable')
    try:
        current = round_index(snapshot.round_id, data)
        sources = [state for state in causal_history(snapshot, history, data).snapshots
                   if state.round_id == snapshot.round_id and observed_phase(state, data) in ('planning', 'roll_down')
                   and not required(state, data, PLANNING_FIELDS)]
        if plan.line is None or plan.target is None or plan.planning_round != snapshot.round_id or not sources:
            return unavailable("No qualified plan from this round's planning phase")
        def pin_id(state):
            pin = read(state, data, 'pinned_line')
            return (pin.get('id') if isinstance(pin, Mapping) else str(pin)) if pin else None
        pinned = pin_id(snapshot)
        if pin_id(sources[-1]) != pinned or (pinned is not None and pinned != plan.line.id):
            return unavailable('Pinned Line changed since planning')
        points = sorted({id for id in (*plan.line.levels, *plan.line.rolls) if round_index(id, data) > current},
                        key=lambda id: round_index(id, data))
    except (DataError, KeyError, TypeError, ValueError) as error:
        return unavailable(str(error))
    if not points:
        return unavailable('The planned Line schedules no later level or roll-down')
    at = points[0]
    return {'available': True, 'reason': None, 'comp_id': plan.target, 'line_id': plan.line.id,
            'pinned': pinned is not None, 'planning_round': plan.planning_round,
            'planning_snapshot_id': sources[-1].snapshot_id, 'round_id': at,
            'level': plan.line.levels.get(at), 'gold_floor': plan.line.rolls.get(at),
            'evidence_path': ['plan', 'line']}
