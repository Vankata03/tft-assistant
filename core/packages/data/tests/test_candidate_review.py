"""Public candidate workflows use synthetic tagged fixtures, never production defaults."""
import json
from datetime import UTC, datetime
import pytest

from tft_data import DataStore
from tft_data.cli import main
from .test_refresh import patch_files


def inputs(tmp_path):
    rules=patch_files(tmp_path/'rules')
    payload={'setData':[{'number':18,'mutator':'TFTSet18','champions':[
        {'apiName':id,'name':id,'cost':1,'traits':[]} for id in ('DA_18_Ornn','DA_18_Sivir')],
        'traits':[],'items':['fixture-item'],'augments':[]}],
        'items':[{'apiName':'fixture-item','name':'Fixture item','isAugment':False,'composition':[]}]}
    dragon=tmp_path/'cdragon.json';dragon.write_text(json.dumps(payload))
    overlay=tmp_path/'overlay.json'
    overlay.write_text(json.dumps({'schema_version':1,'patch':'test.1','set_number':18,
        'entities':{**{id:{'values':{'team_slot_cost':{'value':1,'source':'owner',
            'citation':'Declared synthetic ordinary-unit certificate; not patch evidence'}}} for id in ('DA_18_Ornn','DA_18_Sivir')},
            'fixture-item':{'values':{
            'category':{'value':'finished','source':'patch-notes','citation':'https://example.invalid/synthetic-item'},
            'trait_grants':{'value':{},'source':'patch-notes','citation':'https://example.invalid/synthetic-no-grant-certificate'}}}}}))
    return rules,dragon,overlay


def test_bootstrap_installs_reviewed_tagged_overlay_before_immutable_validation(tmp_path):
    rules,dragon,overlay=inputs(tmp_path)
    destination=tmp_path/'candidate'
    assert main(['bootstrap','test.1','--data-dir',str(destination),
        '--static-file',str(rules/'static.toml'),'--tunables-file',str(rules/'tunables.toml'),
        '--cdragon-file',str(dragon),'--entity-overlay-file',str(overlay)])==0
    result=DataStore(tmp_path/'isolated-snapshots').refresh(destination/'test.1',now=datetime(2026,10,12,tzinfo=UTC))
    assert result.error is None
    item=result.snapshot.entities['fixture-item']
    assert item.values['category'].value=='finished'
    assert item.values['trait_grants'].value=={}
    assert item.values['trait_grants'].source=='patch-notes'
    assert item.values['trait_grants'].citation=='https://example.invalid/synthetic-no-grant-certificate'
    report=(destination/'test.1'/'patch-diff.md').read_text()
    assert 'fixture-item.trait_grants' in report and 'absent' in report
    assert 'synthetic-no-grant-certificate' in report
    assert not (destination/'patches.toml').exists()


def test_review_cli_is_deterministic_offline_and_keeps_unknown_requirements_unpublished(tmp_path):
    from hashlib import sha256
    rules,dragon,overlay=inputs(tmp_path)
    bundle=tmp_path/'ddragon.json';bundle.write_text('{}')
    outputs=[]
    for name in ('review-one','review-two'):
        destination=tmp_path/name
        assert main(['prepare-review','test.1','--set', '18','--review-dir',str(destination),
            '--cdragon-file',str(dragon),'--ddragon-file',str(bundle),'--entity-overlay-file',str(overlay)])==0
        outputs.append({p.name:p.read_bytes() for p in destination.iterdir()})
    assert outputs[0]==outputs[1]
    requirements=json.loads(outputs[0]['requirements.json'])
    assert requirements['qualification_status']=='incomplete_review_input'
    assert all(row['value'] is None for row in requirements['static'])
    assert all(row['value'] is None for row in requirements['tunables'])
    assert not (tmp_path/'review-one'/'static.toml').exists()
    manifest=json.loads(outputs[0]['manifest.json'])
    for name,expected in manifest['outputs'].items():
        assert sha256(outputs[0][name]).hexdigest()==expected
    assert manifest['inputs']['cdragon']['sha256']==sha256(dragon.read_bytes()).hexdigest()


def test_review_cli_records_final_capacity_and_consumer_dependencies_without_filling_unknowns(tmp_path):
    from hashlib import sha256
    _,dragon,overlay=inputs(tmp_path);bundle=tmp_path/'bundle.json';bundle.write_text('{}')
    destination=tmp_path/'review'
    assert main(['prepare-review','test.1','--set','18','--review-dir',str(destination),
        '--cdragon-file',str(dragon),'--ddragon-file',str(bundle)])==0
    requirements=json.loads((destination/'requirements.json').read_text())
    assert len(requirements['static'])==25 and len(requirements['tunables'])==59
    coverage=json.loads((destination/'unit-capacity-coverage.json').read_text())
    assert len(coverage['rows'])==2
    assert all(row['team_slot_cost'] is None for row in coverage['rows'])
    assert all(row['qualification_status']=='slot_certificate_unavailable' for row in coverage['rows'])
    dependencies=json.loads((destination/'consumer-inputs.json').read_text())
    by_path={row['path']:row for row in dependencies['rows']}
    assert by_path['static.team_capacity']['value'] is None
    assert by_path['static.capture_unit_counter']['value'] is None
    assert by_path['fields.lobby_complete']['producer']=='capture_runtime'
    assert by_path['TraitSighting.team_slot_budget']['producer']=='remote_capture_unavailable'
    assert by_path['owned_active_form']['producer']=='capture_resolution_unavailable'
    assert by_path['static.rules_flags.wisp_purchase_shop_slots_delta']['value'] is None
    manifest=json.loads((destination/'manifest.json').read_text())
    assert manifest['consumer_code']['entity_overlay.py']
    for name in ('consumer-inputs.json','unit-capacity-coverage.json'):
        assert sha256((destination/name).read_bytes()).hexdigest()==manifest['outputs'][name]
    assert not (destination/'static.toml').exists()


def test_review_rejects_a_boolean_slot_declaration_without_publishing_review_files(tmp_path):
    _,dragon,overlay=inputs(tmp_path);bundle=tmp_path/'bundle.json';bundle.write_text('{}')
    raw=json.loads(overlay.read_text());raw['entities']['DA_18_Ornn']['values']['team_slot_cost']['value']=True
    overlay.write_text(json.dumps(raw));destination=tmp_path/'review'
    assert main(['prepare-review','test.1','--set','18','--review-dir',str(destination),
        '--cdragon-file',str(dragon),'--ddragon-file',str(bundle),'--entity-overlay-file',str(overlay)])==2
    assert not destination.exists()


@pytest.mark.parametrize('change',[
    {'trait_grants':{'value':{'not-a-trait':1},'source':'owner','citation':'synthetic invalid grant'}},
    {'trait_grants':{'value':{'DA_18_Ornn':1},'source':'owner','citation':'synthetic wrong-kind grant'}},
    {'category':{'value':'finished','source':'owner','citation':'synthetic category'},'component':{'value':True,'source':'owner','citation':'synthetic conflicting flag'}},
])
def test_bootstrap_rejects_invalid_declared_certificates_without_publishing(tmp_path,change):
    rules,dragon,overlay=inputs(tmp_path)
    raw=json.loads(overlay.read_text());raw['entities']['fixture-item']['values']=change
    overlay.write_text(json.dumps(raw));destination=tmp_path/'candidate'
    assert main(['bootstrap','test.1','--data-dir',str(destination),
        '--static-file',str(rules/'static.toml'),'--tunables-file',str(rules/'tunables.toml'),
        '--cdragon-file',str(dragon),'--entity-overlay-file',str(overlay)])==2
    assert not (destination/'test.1').exists()


@pytest.mark.parametrize('update',[
    {'patch':'another-patch'}, {'set_number':19}, {'schema_version':True},
    {'catalog_sha256':'0'*64}, {'entities':{'not-in-catalog':{'values':{}}}},
    {'entities':{'fixture-item':{'values':{'category':{'value':'finished','source':'owner'}}}}},
    {'entities':{'fixture-item':{'values':{'category':{'value':'finished','source':'owner','citation':42}}}}},
])
def test_review_overlay_must_match_identity_hash_schema_and_citation(tmp_path,update):
    _,dragon,overlay=inputs(tmp_path);bundle=tmp_path/'bundle.json';bundle.write_text('{}')
    raw=json.loads(overlay.read_text());raw.update(update);overlay.write_text(json.dumps(raw))
    destination=tmp_path/'review'
    assert main(['prepare-review','test.1','--set','18','--review-dir',str(destination),
        '--cdragon-file',str(dragon),'--ddragon-file',str(bundle),'--entity-overlay-file',str(overlay)])==2
    assert not destination.exists()
