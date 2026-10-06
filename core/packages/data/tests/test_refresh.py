from datetime import datetime, timezone
from pathlib import Path
import pytest
from tft_data import DataStore, DataError

NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)


def test_missing_patch_does_not_invent_game_data(tmp_path):
    store = DataStore(tmp_path / 'snapshots')
    result = store.refresh(tmp_path / 'missing', now=NOW)
    assert result.snapshot is None
    assert 'missing' in result.warnings[0].lower()


def patch_files(path):
    import tomli_w
    from tft_data.config import REQUIRED_STATIC, TUNABLE_FAMILIES
    path.mkdir()
    static = {name: {'value': {}, 'source': 'default'} for name in REQUIRED_STATIC}
    static['threat_keywords']['value'] = {'backline_access': ['backline'], 'aoe': ['nearby enemies']}
    (path / 'static.toml').write_text(tomli_w.dumps({'patch':'test.1','set_number':18,'fields':static}))
    tunables = {name: {'value': 1, 'source':'default','family':family} for name,family in TUNABLE_FAMILIES.items()}
    (path / 'tunables.toml').write_text(tomli_w.dumps({'patch':'test.1','fields':tunables}))
    (path / 'entities.json').write_text('{"entities":[{"id":"fixture-unit","kind":"unit","name":"Fixture unit","cost":2,"traits":[],"text":"Reaches the backline","icon":"https://example.invalid/icon.png","values":{}}]}')
    return path


def test_refresh_publishes_immutable_snapshot_and_retains_it_on_invalid_static(tmp_path):
    path = patch_files(tmp_path / 'patch')
    store = DataStore(tmp_path / 'snapshots')
    first = store.refresh(path, now=NOW)
    assert first.snapshot.names['fixture-unit'] == 'Fixture unit'
    with pytest.raises(TypeError):
        first.snapshot.static['shop_odds'].value['8'] = [1]
    assert first.snapshot.entities['fixture-unit'].threat_tags == ('backline_access',)
    (path / 'static.toml').write_text('patch="test.1"')
    failed = store.refresh(path, now=NOW)
    assert failed.snapshot.snapshot_id == first.snapshot.snapshot_id
    assert 'stale since' in failed.warnings[0]


def test_refresh_uses_cdragon_unit_names_and_ddragon_icons(tmp_path):
    path = patch_files(tmp_path / 'patch')
    from tft_data.adapters import CommunityDragon, DataDragon
    cdragon = {'setData':[{'number':18,'champions':[{'apiName':'fixture-unit','name':'Fixture translated','cost':2,'traits':['Fixture trait'],'ability':{'desc':'Hits nearby enemies','variables':[]},'squareIcon':'ASSETS/unit.tex'}],'traits':[]}], 'items':[]}
    ddragon = {'data':{'fixture-unit':{'id':'fixture-unit','name':'Fixture translated','tier':2,'image':{'full':'fixture.png'}}}}
    result = DataStore(tmp_path / 'snapshots').refresh(path, now=NOW, entity_adapters=[CommunityDragon(cdragon,18),DataDragon(ddragon,'test.1','champion')])
    assert result.snapshot.entities['fixture-unit'].name == 'Fixture translated'
    assert result.snapshot.icons['fixture-unit'].endswith('/img/tft-champion/fixture.png')
    assert result.snapshot.entities['fixture-unit'].values['cost'].source == 'ddragon'
