"""Reviewed source-tagged certificates for existing primary catalog identities."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from .config import tagged
from .models import DataError, plain


def render(value):
    return json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n'


def entities_payload(entities):
    return {'entities':[{
        **plain(vars(entity)),
        'values':{key:plain(vars(value)) for key,value in entity.values.items()},
    } for _,entity in sorted(entities.items())]}


def apply_entity_overlay(entities, overlay_file, patch, set_number):
    from collections.abc import Mapping
    if overlay_file is None:
        return entities, []
    path=Path(overlay_file)
    raw=json.loads(path.read_text())
    if not isinstance(raw,dict) or set(raw)-{'schema_version','patch','set_number','catalog_sha256','entities'} or type(raw.get('schema_version')) is not int or raw['schema_version']!=1:
        raise DataError('Unknown entity overlay schema')
    if raw.get('patch')!=patch or raw.get('set_number')!=set_number:
        raise DataError('Entity overlay patch/set differs from candidate')
    catalog_hash=sha256(render(entities_payload(entities)).encode()).hexdigest()
    if raw.get('catalog_sha256') is not None and raw['catalog_sha256']!=catalog_hash:
        raise DataError('Entity overlay catalog hash differs from checked inputs')
    rows=raw.get('entities')
    if not isinstance(rows,dict):
        raise DataError('Entity overlay requires an entities table')
    result=dict(entities)
    report=[f'Entity overlay SHA-256: {sha256(path.read_bytes()).hexdigest()}.',
        f'Base catalog SHA-256: {catalog_hash}.',
        'Overlay tags and citations are review declarations, not independent source or fit qualification.']
    for id,row in sorted(rows.items()):
        if id not in entities or not isinstance(row,dict) or set(row)!={'values'}:
            raise DataError(f'Unknown entity or unsupported overlay fields: {id}')
        changes=tagged(row['values'],f'overlay.{id}')
        if set(changes)&{'id','kind','name','cost','traits','canonical_id','pool_id'}:
            raise DataError(f'Entity overlay cannot change canonical identity fields: {id}')
        if 'team_slot_cost' in changes and entities[id].kind not in ('unit','unit_form'):
            raise DataError(f'Team slot certificate requires a playable unit identity: {id}')
        if set(changes)&{'trait_grants','category','component','tool_kind'} and entities[id].kind!='item':
            raise DataError(f'Item certificates require an item identity: {id}')
        if any(not isinstance(value.citation,str) or not value.citation.strip() for value in changes.values()):
            raise DataError(f'Entity overlay values require explicit evidence citations: {id}')
        values=dict(entities[id].values)|changes
        grants=values.get('trait_grants')
        if grants is not None and (not isinstance(grants.value,Mapping) or any(
            trait not in entities or entities[trait].kind!='trait' or isinstance(count,bool)
            or not isinstance(count,int) or count<=0 for trait,count in grants.value.items())):
            raise DataError(f'Entity overlay has an invalid trait-grant certificate: {id}')
        category=values.get('category');component=values.get('component')
        if category is not None and category.value not in ('component','finished','tool'):
            raise DataError(f'Entity overlay has an invalid item category: {id}')
        if component is not None and (not isinstance(component.value,bool) or
            (category is not None and component.value!=(category.value=='component'))):
            raise DataError(f'Entity overlay has conflicting item category certificates: {id}')
        for key,value in sorted(changes.items()):
            before=entities[id].values.get(key)
            report.append(f'Changed {id}.{key}: {plain(vars(before)) if before else "absent"!r} -> {plain(vars(value))!r}.')
        result[id]=replace(entities[id],values=values)
    return result,report
