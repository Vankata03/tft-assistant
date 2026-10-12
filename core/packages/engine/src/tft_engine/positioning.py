"""Exact histogram assignment and history-folded trait threats; layouts have no placement value."""
from .planning import read
from datetime import datetime
from math import log, inf, isfinite
from collections.abc import Mapping
from tft_data.models import DataError
from .models import Advice
from .planning import paused, observed_phase, owned_board, required
from .power import tunable, static
from .opponents import round_index, age_weight
from .transition import strongest_owned_board


def assign(costs):
    """Rectangular Hungarian minimum-cost assignment, with forbidden cells at infinity."""
    n=len(costs)
    if not n:
        return ()
    m=len(costs[0])
    if n>m:
        raise DataError('More units than free layout cells')
    u=[0.0]*(n+1); v=[0.0]*(m+1); p=[0]*(m+1); way=[0]*(m+1)
    for i in range(1,n+1):
        p[0]=i; j0=0; minima=[inf]*(m+1); used=[False]*(m+1)
        while True:
            used[j0]=True; i0=p[j0]; delta=inf; j1=0
            for j in range(1,m+1):
                if not used[j]:
                    current=costs[i0-1][j-1]-u[i0]-v[j]
                    if current<minima[j]:
                        minima[j]=current; way[j]=j0
                    if minima[j]<delta:
                        delta=minima[j]; j1=j
            if not isfinite(delta):
                raise DataError('Histogram has no feasible positive-weight layout')
            for j in range(m+1):
                if used[j]:
                    u[p[j]]+=delta; v[j]-=delta
                else:
                    minima[j]-=delta
            j0=j1
            if p[j0]==0:
                break
        while True:
            j1=way[j0]; p[j0]=p[j1]; j0=j1
            if j0==0:
                break
    result=[0]*n
    for j in range(1,m+1):
        if p[j]:
            result[p[j]-1]=j-1
    return tuple(result)


def threat_share(state,history,data,tag):
    lobby=read(state,data,'lobby')
    if lobby is None:
        raise DataError('Fresh lobby required for positioning threats')
    rule=static(data,'rules_flags').get('recent_opponent_exclusion_count')
    if not isinstance(rule,int) or isinstance(rule,bool) or rule<0:
        raise DataError('Sourced recent-opponent exclusion policy unavailable')
    recent=()
    if rule:
        if read(state,data,'recent_opponent_fights_complete') is not True:
            raise DataError('Positive uninterrupted recent fight history required')
        # Confirmed fights are historical facts, not two-second OCR fields.
        observations=[s for s in history.snapshots if s.game_id==state.game_id and s.captured_at<=state.captured_at]+[state]
        certified=[]
        for observation in observations:
            field=observation.fields.get('recent_opponent_fights')
            if field and field.read_at<=state.captured_at:
                certified.extend(row for row in field.value if datetime.fromisoformat(row['read_at'])<=state.captured_at and round_index(row['round_id'],data)<=round_index(state.round_id,data))
        if not certified:
            raise DataError('Confirmed recent fights unavailable for matchup exclusion')
        unique={(row['round_id'],row['read_at'],row['opponent_id']):row for row in certified}
        fights=sorted(unique.values(),key=lambda row:(datetime.fromisoformat(row['read_at']),round_index(row['round_id'],data)))
        if len(fights)<rule:
            raise DataError('Insufficient confirmed fight history for matchup exclusion')
        recent=tuple(row['opponent_id'] for row in fights[-rule:])
    if isinstance(lobby,Mapping):
        lobby=tuple(dict(value,player_id=id) if isinstance(value,Mapping) else {'player_id':id,'alive':value>0} for id,value in lobby.items())
    possible={str(row.get('player_id',row.get('opponent_id'))) for row in lobby
        if row.get('alive',True) and not row.get('is_self',False)}-set(recent)
    latest={}
    for sighting in history.sightings:
        if sighting.opponent_id not in possible or (sighting.read_at and sighting.read_at>state.captured_at) or round_index(sighting.round_id,data)>round_index(state.round_id,data):
            continue
        old=latest.get(sighting.opponent_id)
        if old is None or round_index(sighting.round_id,data)>=round_index(old.round_id,data):
            latest[sighting.opponent_id]=sighting
    numerator=denominator=0.0
    for sighting in latest.values():
        weight=age_weight(max(0,round_index(state.round_id,data)-round_index(sighting.round_id,data)),data)
        threats=False
        for id,count in sighting.traits.items():
            entity=data.entities.get(id)
            if entity is None or tag not in entity.threat_tags:
                continue
            thresholds=entity.values.get('threat_breakpoints')
            points=entity.values.get('breakpoints')
            threshold=thresholds.value.get(tag) if thresholds else min(points.value) if points and points.value else None
            if threshold is None:
                raise DataError(f'Trait threat activation unavailable: {id}/{tag}')
            threats=threats or count>=int(threshold)
        denominator+=weight; numerator+=weight*threats
    return numerator/denominator if denominator else 0.0


def adjustments(state,history,data):
    states=[s for s in history.snapshots if s.game_id==state.game_id and s.captured_at<state.captured_at and observed_phase(s,data) in ('planning','roll_down')]
    states.sort(key=lambda s:s.captured_at)
    active={'backline_access':False,'aoe':False}; shares={}
    for observation in states+[state]:
        for tag in active:
            share=threat_share(observation,history,data,tag); shares[tag]=share
            if share>=float(tunable(data,'threat_share_on')):
                active[tag]=True
            elif share<float(tunable(data,'threat_share_off')):
                active[tag]=False
    return active,shares


def layout(board,context,active):
    data=context.data; guide=data.guides[context.plan.target]
    positions={}; protected=set(); adjusted=set(); used=set()
    locks=read(context.snapshot,context.data,'position_locks') or {}
    for i,unit in enumerate(board.units):
        locked=locks.get(str(i),locks.get(unit.unit_id))
        cell=locked if locked is not None else guide.positions.get(unit.unit_id)
        if cell is not None:
            if not isinstance(cell,int) or isinstance(cell,bool) or not 0<=cell<28 or cell in used:
                raise DataError('Conflicting or invalid Guide/owner layout cells')
            positions[i]=cell; used.add(cell)
            if locked is not None or guide.source=='owner':
                protected.add(i)
    def move(i,cells):
        if i in protected or i in adjusted:
            return False
        for cell in cells:
            blocker=next((j for j,c in positions.items() if c==cell and j!=i),None)
            if blocker in protected or blocker in adjusted:
                continue
            if i in positions:
                used.discard(positions[i])
            if blocker is not None:
                del positions[blocker]
            positions[i]=cell; used.add(cell); adjusted.add(i)
            return True
        return False
    # Positional rules are explicit sourced selectors/cells, never inferred effects.
    rules=data.static.get('positioning_rules')
    for rule in rules.value if rules else ():
        enabled=True
        if 'trait_id' in rule:
            if board.trait_counts is None:
                raise DataError('Authoritative traits required for own positional rule')
            enabled=board.trait_counts.get(rule['trait_id'],0)>=rule['breakpoint']
        if 'augment_id' in rule:
            held=read(context.snapshot,context.data,'held_augments')
            if held is None or read(context.snapshot,context.data,'held_augments_complete') is not True:
                raise DataError('Held augments required for own positional rule')
            enabled=enabled and rule['augment_id'] in held
        if enabled:
            for i,unit in enumerate(board.units):
                if unit.unit_id in rule['unit_ids']:
                    move(i,rule['cells'])
    templates=data.static.get('positioning_templates')
    carries=[i for i,u in enumerate(board.units) if u.unit_id in guide.carry_ids]
    if active['backline_access']:
        if templates is None or 'anti_dive' not in templates.value:
            raise DataError('Sourced anti-dive template unavailable')
        template=templates.value['anti_dive']
        for i in carries:
            if move(i,template['carry_cells']):
                guards=[j for j,u in enumerate(board.units) if j!=i and data.entities[u.unit_id].values.get('item_class') and data.entities[u.unit_id].values['item_class'].value=='tank']
                for j in guards:
                    if move(j,template['bodyguard_cells'].get(str(positions[i]),())):
                        break
    if active['aoe']:
        if templates is None or 'anti_aoe' not in templates.value:
            raise DataError('Sourced spread template unavailable')
        cells=templates.value['anti_aoe']['cells']
        backliners=[i for i,u in enumerate(board.units) if i in carries or (data.entities[u.unit_id].values.get('position_role') and data.entities[u.unit_id].values['position_role'].value=='backline')]
        for i in backliners:
            move(i,[cell for cell in cells if cell not in used or positions.get(i)==cell])
    remaining=[i for i in range(len(board.units)) if i not in positions]
    free=[cell for cell in range(28) if cell not in positions.values()]
    costs=[]
    for i in remaining:
        histogram=data.positioning.get(board.units[i].unit_id)
        if histogram is None:
            raise DataError(f'Position histogram unavailable: {board.units[i].unit_id}')
        costs.append([-log(histogram[cell]) if histogram[cell]>0 else inf for cell in free])
    for i,j in zip(remaining,assign(costs)):
        positions[i]=free[j]
    return tuple({'unit_index':i,'unit_id':unit.unit_id,'cell':positions[i]} for i,unit in enumerate(board.units))


def advice(context):
    if context.plan.target is None:
        return ()
    if context.recommended_board is None:
        if required(context.snapshot,context.data,('board','bench','level')):
            return ()
        from dataclasses import replace
        context=replace(context,recommended_board=strongest_owned_board(owned_board(context.snapshot,context.data),int(read(context.snapshot,context.data,'level')),context.data,target=context.plan.target,round_id=context.snapshot.round_id))
    state,data=context.snapshot,context.data
    settled=read(state,data,'board_settled_since')
    if settled is None:
        return (paused('Positive settled-board clock unavailable',missing=('board_settled_since',),domain='positioning'),)
    try:
        since=datetime.fromisoformat(settled)
        if since.tzinfo is None:
            raise DataError('Settled-board timestamp requires a timezone')
        if (state.captured_at-since).total_seconds()<float(tunable(data,'board_settle_seconds')):
            return ()
        warning=(); threats_available=True
        try:
            active,shares=adjustments(state,context.history,data)
        except DataError as error:
            active={'backline_access':False,'aoe':False}; shares={}; threats_available=False
            warning=(paused(str(error),domain='positioning'),)
        target=layout(context.recommended_board,context,active)
        # Reconstruct the last eligible layout rather than keep mutable UI state.
        previous=[s for s in context.history.snapshots if s.game_id==state.game_id and s.round_id==state.round_id and s.captured_at<state.captured_at and observed_phase(s,data) in ('planning','roll_down') and read(s,data,'inventory_complete') is True and read(s,data,'board_settled_since')]
        prior=None
        if previous:
            old=max(previous,key=lambda s:s.captured_at)
            if (old.captured_at-datetime.fromisoformat(read(old,data,'board_settled_since'))).total_seconds()>=float(tunable(data,'board_settle_seconds')):
                old_board=read(old,data,'board'); old_bench=read(old,data,'bench')
                if old_board is not None and old_bench is not None:
                    from dataclasses import replace
                    from .models import Board
                    old_recommended=strongest_owned_board(Board(old_board.units,old_bench,old_board.trait_counts),int(read(old,data,'level')),data,target=context.plan.target,round_id=old.round_id)
                    try:
                        old_active,_=adjustments(old,context.history,data)
                    except DataError:
                        old_active={'backline_access':False,'aoe':False}
                    prior=(layout(old_recommended,replace(context,snapshot=old),old_active),old_active)
                    if prior==(target,active):
                        return warning
        turns_on=tuple(tag for tag,on in active.items() if on and (prior is None or not prior[1][tag]))
        arrows=tuple({'unit_index':row['unit_index'],'from':context.recommended_board.units[row['unit_index']].position,'to':row['cell']} for row in target
            if context.recommended_board.units[row['unit_index']].position is not None and context.recommended_board.units[row['unit_index']].position!=row['cell'])
        return (Advice('positioning','Move to target layout','act_this_phase',float(tunable(data,'confidence_medium_min')),'template_layout',
            validity=('board','bench','lobby','recent_opponents','board_settled_since','position_locks','round'),
            option_id='positioning:layout',payload={'operation':'layout','layout':target,'arrows':arrows,'adjustments':active,'threat_shares':shares,'voice':bool(turns_on) and threats_available,'turns_on':turns_on,'threats_available':threats_available}),)+warning
    except (DataError,KeyError,TypeError,ValueError) as error:
        return (paused(str(error),domain='positioning'),)
