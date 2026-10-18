"""Performance paths must reproduce the reference simulation exactly."""
from collections import OrderedDict, namedtuple
from dataclasses import dataclass, replace
from types import MappingProxyType
import importlib.util
from pathlib import Path
import numpy as np
from tft_engine import Board, GameHistory, Line, SimulationEffects, Unit, simulate_lines


def _fixture():
    spec=importlib.util.spec_from_file_location('synthetic_planning_examples',Path(__file__).with_name('test_planning.py'))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _mixed_cost_case():
    fixture=_fixture(); tag=fixture.tag
    data=fixture.patch()
    static=dict(data.static)|{'shop_odds':tag({str(i):[.35,.25,.2,.12,.08] for i in range(1,11)}),
        'round_types':tag({r:'combat' for r in data.static['round_order'].value})}
    entities=dict(data.entities)
    for index in range(10):
        entities[f'x{index}']=replace(entities['a'],id=f'x{index}',name=f'x{index}',cost=index%5+1)
    data=replace(data,static=static,entities=entities)
    owned=Board((Unit('a',2),Unit('x1')),(Unit('c'),Unit('x3')))
    state=fixture.snapshot(board=owned,bench=owned.bench,level=4,gold=46,hp=30)
    lines=(Line('hold'),Line('floor10',rolls={'3-2':10}),Line('allin',rolls={'3-2':0}),
        Line('stabilize',rolls={'3-2':0},stabilize=True),Line('level',levels={'3-2':6},rolls={'3-3':0}))
    return state,data,lines


def test_grouped_shop_picks_match_the_full_width_scan(monkeypatch):
    import tft_engine.lines as lines_module
    state,data,lines=_mixed_cost_case()
    results={}
    for threshold in (1,10**9):
        monkeypatch.setattr(lines_module,'GROUPED_PICK_ROWS',threshold)
        results[threshold]=[r.to_dict() for r in simulate_lines(state,GameHistory(),data,'A',lines,rollouts=64,seed=7)]
    assert results[1]==results[10**9]


def test_scoped_preparation_reuse_matches_independent_simulations():
    from tft_engine.preparation import evaluation_scope
    state,data,lines=_mixed_cost_case()
    effects=SimulationEffects(gold_delta=6,free_rolls=1)

    @evaluation_scope
    def shared():
        return tuple(simulate_lines(state,GameHistory(),data,comp,lines,effects=change,rollouts=32,seed=11)
            for comp in ('A','B','A') for change in (None,effects))

    independent=tuple(simulate_lines(state,GameHistory(),data,comp,lines,effects=change,rollouts=32,seed=11)
        for comp in ('A','B','A') for change in (None,effects))
    assert [[r.to_dict() for r in rows] for rows in shared()]==[[r.to_dict() for r in rows] for rows in independent]


def test_hash_collisions_fall_back_to_exact_row_grouping(monkeypatch):
    import tft_engine.sim_board as sim_board
    monkeypatch.setattr(sim_board,'_ROW_MULTIPLIERS',np.ones(4096,dtype=np.uint64))
    packed=np.array([[1,0,2],[0,1,2],[1,0,2],[2,0,1]])
    indices,inverse=sim_board._distinct_rows(packed)
    assert len(indices)==3
    assert (packed[indices][inverse]==packed).all()


def test_fast_encoding_and_freezing_keep_subclass_and_dataclass_semantics():
    from tft_data.models import freeze
    from tft_engine.models import _encode

    @dataclass(frozen=True)
    class Pair:
        left: object
        right: object = ()

    Point=namedtuple('Point','x y')
    value={'ordered':OrderedDict(b=1,a=(2,3)),'proxy':MappingProxyType({'k':[Pair(1,(2,))]}),'point':Point(1,2.5),'none':None,'flag':True}
    assert _encode(value)=={'ordered':{'b':1,'a':[2,3]},'proxy':{'k':[{'left':1,'right':[2]}]},'point':[1,2.5],'none':None,'flag':True}
    assert _encode(Pair(Pair('x')))=={'left':{'left':'x','right':[]},'right':[]}
    frozen=freeze({1:OrderedDict(z=[1,{'y':2}]),'p':Point(1,2)})
    assert isinstance(frozen,MappingProxyType) and isinstance(frozen['1'],MappingProxyType)
    assert frozen['1']['z']==(1,MappingProxyType({'y':2})) and frozen['p']==(1,2) and type(frozen['p']) is tuple


def test_cached_history_encodings_match_whole_history_encoding():
    import gc, json
    from datetime import timedelta
    from tft_data.models import freeze
    from tft_engine import TraitSighting
    from tft_engine.models import GameHistory as History, HistoryWindow, _ELEMENT_ENCODINGS, _encode, frozen_history, history_json
    fixture=_fixture()
    snapshots=tuple(fixture.snapshot(gold=10+index,shop=({'unit_id':'a','cost':1},),note=float(index)/3) for index in range(4))
    snapshots=tuple(replace(state,captured_at=state.captured_at+timedelta(seconds=index)) for index,state in enumerate(snapshots))
    sightings=(TraitSighting('p2','3-1',5,{'fire':2},1),)
    for history in (History(snapshots,sightings),History(HistoryWindow(snapshots,1,3),()),History()):
        for _ in range(2):
            assert history_json(history)==json.dumps(_encode(history),sort_keys=True,separators=(',',':'),allow_nan=False)
            assert frozen_history(history)==freeze(_encode(history))
    cached=len(_ELEMENT_ENCODINGS)
    del snapshots,sightings,history
    gc.collect()
    assert len(_ELEMENT_ENCODINGS)<cached
