"""Protected review transport; policy and valuation remain in ReviewService."""
import base64
from tft_review import ReviewAccess


class ReviewTransport:
    def __init__(self,sessions,service=None):
        self.sessions,self.service=sessions,service
        self.enqueue = None

    def permitted(self,game_id):
        if not self.sessions:
            raise ValueError('Review storage unavailable')
        if self.sessions.active_game_id and self.sessions.mode.value=='silent':
            raise ValueError('Silent games suppress review surfaces until the game finishes')
        rows=[row for row in self.sessions.list_games() if row['game_id']==game_id]
        if not rows:
            raise ValueError('Unknown logged game')
        if not rows[0]['finished']:
            raise ValueError('Post-game review requires a confirmed finished game')
        return rows[0]

    def ready(self,game_id):
        """Inspect a finished report without exposing or recomputing private values."""
        from tft_engine.evidence import EvidenceGraph
        self.permitted(game_id)
        events=self.sessions.read_events(game_id)
        end=next(event for event in reversed(events) if event['kind']=='game_end')
        modes=[event['payload']['mode'] for event in events if event['seq']<=end['seq']
               and event['kind'] in {'game_start','mode_change'}]
        mode=modes[-1]
        if mode=='silent':return None
        stored=self.sessions.read_review(game_id)
        if stored is None:raise ValueError('Review is not ready')
        body=stored['review']
        if body.get('schema_version')!=1:raise ValueError('Review report schema unavailable; regenerate')
        graph=EvidenceGraph.from_dict(body['evidence_graph'])
        if graph.root_id!=body['report_id'] or graph.resolve(path=('game_id',))!=str(game_id):
            raise ValueError('Review belongs to another game or evidence identity')
        from tft_review.identity import digest
        job_id = body.get('job_id') or digest({'report_id':graph.root_id,
            'engine_version':stored['engine_version'],'data_snapshot_id':stored['data_snapshot_id'],
            'log_hash':stored.get('log_hash')})
        return {'game_id':str(game_id),'mode':mode,'report_id':graph.root_id,'job_id':job_id,
                'evidence_id':graph.root_id,'ended_at':end['timestamp']}

    def call(self,operation,game_id,**arguments):
        game = self.permitted(game_id)
        if operation=='regenerate':
            if game['review_locked']:
                raise ValueError('Review remains locked until the Live-mode run starts')
            if self.enqueue is None:
                raise ValueError('Review supervisor unavailable')
            self.enqueue(game_id, regenerate=True)
            return {'state': 'queued', 'game_id': str(game_id)}
        if operation=='media':
            content=ReviewAccess(self.sessions).read_media(game_id,arguments['name'])
            if content is None:
                raise ValueError('Logged media was evicted or unavailable')
            offset,limit=arguments['cursor'],arguments['limit']
            if offset>len(content):raise ValueError('Media cursor exceeds retained bytes')
            chunk=content[offset:offset+limit]
            return {'name':arguments['name'],'offset':offset,'total_bytes':len(content),
                'next_cursor':offset+len(chunk) if offset+len(chunk)<len(content) else None,
                'content_type':'image/webp' if arguments['name'].endswith('.webp') else 'video/mp4',
                'base64':base64.b64encode(chunk).decode('ascii')}
        if self.service is None:
            raise ValueError('Review policy service is not connected; wait for the post-game job')
        if operation=='summary':return self.service.summary(game_id)
        summary=self.service.summary(game_id)
        if summary.get('locked'):raise ValueError('Review remains locked until the Live-mode run starts')
        if (summary.get('report_id'),summary.get('evidence_id'))!=(arguments.pop('report_id'),arguments.pop('evidence_id')):
            raise ValueError('Review report was superseded; reload its protected summary')
        if operation=='page':return self.service.detail(game_id,**arguments,max_bytes=60*1024)
        if operation=='what_if':return self.service.what_if(game_id,arguments['moment_id'],arguments['option_id'])
        if operation=='tag':
            self.service.tag(game_id,arguments['moment_id'],arguments['tag'])
            return {'moment_id':arguments['moment_id'],'tag':arguments['tag']}
        raise ValueError('Unknown review operation')
