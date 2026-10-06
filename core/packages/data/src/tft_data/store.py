"""Atomically publish content-addressed snapshots; games retain their object."""
import hashlib,json,os,tempfile
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
from .config import load_patch
from .adapters import merge_entities
from .models import DataError,DataSnapshot,RefreshResult,plain

class DataStore:
 def __init__(self,root): self.root=Path(root);self.current=None;self.last_good_at=None
 def refresh(self,patch_dir,*,now=None,in_game=False,trigger='startup',entity_adapters=(),**kwargs):
  now=now or datetime.now(timezone.utc)
  if in_game or trigger not in {'startup','Lobby','end-of-game'}: return RefreshResult(self.current,deferred=True)
  try:
   patch,set_number,static,tunables,entities,changed_ids=load_patch(patch_dir)
   for adapter in entity_adapters: entities=merge_entities(entities,adapter.entities())
   for e in entities.values():
    if e.kind=='wisp' and e.id not in static['wisps'].value: raise DataError(f'New Wisp {e.id} needs a static effect entry')
   keywords=static['threat_keywords'].value
   entities={id:replace(e,threat_tags=tuple(tag for tag,words in keywords.items() if any(word.lower() in e.text.lower() for word in words))) for id,e in entities.items()}
   warnings=tuple(f'Low confidence: {name} uses {v.source}' for name,v in static.items() if v.source in {'default','carried'})
   payload={'patch':patch,'set_number':set_number,'static':{k:vars(v) for k,v in static.items()},'tunables':{k:vars(v) for k,v in tunables.items()},'entities':{k:vars(v) for k,v in entities.items()},'changed_ids':changed_ids}
   content=json.dumps(plain(payload),sort_keys=True,default=lambda o:plain(vars(o))).encode();id=hashlib.sha256(content).hexdigest()
   if self.current and self.current.snapshot_id==id: return RefreshResult(self.current,warnings=warnings)
   self.root.mkdir(parents=True,exist_ok=True);destination=self.root/id
   if not destination.exists():
    with tempfile.TemporaryDirectory(dir=self.root) as temp:
     folder=Path(temp)/id;folder.mkdir();(folder/'snapshot.json').write_bytes(content);os.replace(folder,destination)
   self.current=DataSnapshot(id,patch,set_number,static,tunables,entities,warnings=warnings,changed_ids=changed_ids);self.last_good_at=now
   return RefreshResult(self.current,True,warnings)
  except (DataError,OSError,TypeError,ValueError) as exc:
   since=self.last_good_at.isoformat() if self.last_good_at else 'unavailable'
   return RefreshResult(self.current,warnings=(f'Data stale since {since}: {exc}',))
