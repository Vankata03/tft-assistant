"""External source schemas; unknown versions fail instead of producing advice."""
from dataclasses import replace
from typing import Any
from .models import DataError, Entity, TaggedValue

class CommunityDragon:
    def __init__(self, payload: dict, set_number: int):
        self.payload = payload
        self.set_number = set_number
    def entities(self) -> dict[str, Entity]:
        try:
            sets = self.payload['setData']
            matching = [s for s in sets if s['number'] == self.set_number]
            if not matching: raise DataError(f'CommunityDragon has no set {self.set_number}')
            entities = {}
            for dataset in matching:
                for kind, rows in [('unit',dataset['champions']),('trait',dataset['traits'])]:
                    for row in rows:
                        id = row['apiName']
                        text = row.get('ability',{}).get('desc',row.get('desc',''))
                        cost = row.get('cost',0)
                        values = {k:TaggedValue(v,'cdragon') for k,v in {'name':row['name'],'cost':cost,'text':text,
                            'ability':row.get('ability',{}),'effects':row.get('effects',[])}.items()}
                        entities[id] = Entity(id,kind,row['name'],cost,tuple(row.get('traits',[])),text,
                            row.get('squareIcon',row.get('icon','')),values)
            for row in self.payload['items']:
                id = row['apiName']
                kind = 'augment' if 'Augment' in id else 'wisp' if 'Wisp' in id else 'item'
                values = {k:TaggedValue(v,'cdragon') for k,v in {'name':row['name'],'text':row.get('desc',''),
                    'effects':row.get('effects',{}),'recipe':row.get('from',[])}.items()}
                entities[id] = Entity(id,kind,row['name'],text=row.get('desc',''),icon=row.get('icon',''),values=values)
            if not entities: raise DataError('CommunityDragon has no entities')
            return entities
        except (KeyError,TypeError,ValueError) as exc:
            raise DataError(f'CommunityDragon schema changed: {exc}') from None

class DataDragon:
    def __init__(self,payload:dict,version:str,kind:str):
        self.payload,self.version,self.kind = payload,version,kind
    def entities(self) -> dict[str,Entity]:
        try:
            result = {}
            for key,row in self.payload['data'].items():
                id = row.get('id',key)
                icon = f'https://ddragon.leagueoflegends.com/cdn/{self.version}/img/tft-{self.kind}/{row["image"]["full"]}'
                values = {'name':TaggedValue(row['name'],'ddragon'),'icon':TaggedValue(icon,'ddragon')}
                cost = row.get('tier',0)
                if cost: values['cost'] = TaggedValue(cost,'ddragon')
                result[id] = Entity(id,'unit' if self.kind=='champion' else self.kind,row['name'],cost,icon=icon,values=values)
            if not result: raise DataError('Data Dragon has no entities')
            return result
        except (KeyError,TypeError,ValueError) as exc:
            raise DataError(f'Data Dragon schema changed: {exc}') from None


def merge_entities(current:dict[str,Entity],incoming:dict[str,Entity]) -> dict[str,Entity]:
    result = dict(current)
    for id,new in incoming.items():
        old = result.get(id)
        if old:
            new = replace(old,name=new.name,cost=new.cost or old.cost,icon=new.icon or old.icon,
                text=new.text or old.text,traits=new.traits or old.traits,values={**old.values,**new.values})
        result[id] = new
    return result
