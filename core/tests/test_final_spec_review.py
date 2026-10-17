"""Final Spec regressions through protected review and real replay boundaries."""
from datetime import timedelta

import pytest
from PIL import Image

from tft_review import ReviewService
from tests.test_replay_contracts import NOW, ROOT, logged_game


@pytest.mark.parametrize('mode', ['baseline', 'silent'])
def test_production_reader_disagreement_reaches_protected_debug_with_keyframe(tmp_path, mode):
    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode=mode)
    at = (NOW+timedelta(seconds=1)).isoformat()
    # Exact CapturePipeline production event and adjacent keyframe shape.
    event = sessions.append_event('reader_disagreement', {'disagreements': [
        {'zone': 'board', 'position': 5, 'reader_unit_id': 'unit',
         'tracking_unit_id': 'other', 'reader_confidence': .48, 'chosen_unit_id': 'other'}]}, timestamp=at)
    sessions.write_keyframe(Image.new('RGB', (20, 20), 'white'), reason='reader_disagreement', timestamp=at)
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    service = ReviewService(sessions, store, repository=ROOT)
    service.produce('901')
    if mode == 'silent':
        with pytest.raises(PermissionError):
            service.detail('901', path=('debug', 'disagreements'))
        return
    page = service.detail('901', path=('debug', 'disagreements'), limit=1)
    assert page['total'] == 1
    assert page['next_cursor'] is None
    seq = service.detail('901', path=('debug', 'disagreements', 0, 'seq'))
    assert seq['items'][0]['value'] == event['seq']
    media = service.detail('901', path=('debug', 'media'))
    assert media['total'] == 1
    association = service.detail('901', path=('debug', 'disagreements', 0, 'keyframe_paths'))
    assert association['total'] == 1
    stamp = service.detail('901', path=('debug', 'media', 0, 'timestamp'))
    assert stamp['items'][0]['value'] == at


def adoption_game(tmp_path, *, lock=False, incomplete=False, stale=False):
    import json
    import tomllib
    import tomli_w
    from tft_core.storage import SessionStore
    from tft_engine import Board, Unit
    from tests.test_replay_contracts import historical_data, GuideFeed, log_snapshot
    store, _ = historical_data(tmp_path)
    path = tmp_path/'patch'
    entities = json.loads((path/'entities.json').read_text())
    other = dict(entities['entities'][0], id='other', name='Other fixture unit')
    entities['entities'].append(other)
    (path/'entities.json').write_text(json.dumps(entities))
    values = tomllib.loads((path/'tunables.toml').read_text())
    values['fields']['pivot_margin_by_stage']['value'] = {'default':100, 'post_roll_down':100}
    (path/'tunables.toml').write_text(tomli_w.dumps(values))

    class TwoGuides(GuideFeed):
        name = "two-guides-fixture"
        def fetch(self):
            first = super().fetch()['guides'][0]
            return {'guides':[first, dict(first, id='other-guide',
                finalComp=[{'apiName':'other'}], earlyComp=[{'apiName':'other'}], mainChampion='other')]}

    data = store.refresh(path, sources=(TwoGuides(),), now=NOW).snapshot
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.set_mode('baseline')
    sessions.start_game('901', patch=data.patch, data_snapshot_id=data.snapshot_id, timestamp=NOW.isoformat())
    for index, round_id in enumerate(('3-2','3-3','3-4')):
        at = NOW+timedelta(seconds=index)
        fields = {'board':Board((Unit('unit' if index == 0 else 'other', 2),))}
        if lock:
            fields['comp_lock'] = 'guide'
        if incomplete and index:
            fields['inventory_complete'] = False
        snapshot = log_snapshot(data, at=at, snapshot_id=f'phase-{index}', **fields)|{'round_id':round_id}
        if stale and index:
            snapshot['fields']['board']['read_at'] = (NOW-timedelta(seconds=10)).isoformat()
        sessions.append_event('snapshot', snapshot, timestamp=at.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    return sessions, store


def test_uncalled_observed_player_adoption_has_provenance_without_fabricated_pivot_advice(tmp_path):
    from tft_review import ReplayProducer
    sessions, store = adoption_game(tmp_path)
    batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    assert not [row for row in batch.records if row.decision == 'pivot']
    service = ReviewService(sessions, store, repository=ROOT)
    service.produce('901')
    def value(index, field):
        return service.detail('901', path=('surface','plan_timeline',index,field))['items'][0]['value']
    assert value(0, 'target') == 'guide'
    assert value(1, 'target') == 'guide'
    assert value(2, 'target') == 'other-guide'
    assert value(2, 'called_status') == 'taken_without_call'
    assert value(1, 'called_status') == 'display_attribution_unavailable'
    assert value(2, 'pivot_to') is None
    evidence = service.detail('901', path=('plan_timeline',2,'observed_transition'))
    assert evidence['kind'] == 'object'
    assert service.detail('901', path=('plan_timeline',2,'observed_transition','from'))['items'][0]['value'] == 'guide'


@pytest.mark.parametrize('guard', ['lock','incomplete','stale'])
def test_unqualified_or_locked_board_never_becomes_observed_adoption(tmp_path, guard):
    sessions, store = adoption_game(tmp_path, **{guard:True})
    service = ReviewService(sessions, store, repository=ROOT)
    service.produce('901')
    page = service.detail('901', path=('surface','plan_timeline'))
    for index in range(page['total']):
        status = service.detail('901', path=('surface','plan_timeline',index,'called_status'))
        assert status['items'][0]['value'] != 'taken_without_call'
