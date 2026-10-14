"""Protected owner routes over immutable, authenticated review evidence."""
from tft_engine.evidence import EvidenceGraph
from datetime import datetime
import re

from .contracts import json_value
from .identity import digest, replay_identity
from .policy import ReviewPolicy
from .replay import ReplayProducer, validate_events


def surface_summary(report):
    summary = json_value(report.summary)
    indices = {row['moment_id']: index for index, row in enumerate(report.moments)}
    top5 = []
    for row in summary['top5']:
        item = {key: row[key] for key in ('moment_id', 'engine_decision_id',
            'round_id', 'category', 'cost', 'close_call', 'shown', 'reason')}
        item['moment_path'] = ['moments', indices[row['moment_id']]]
        for key in ('engine_choice', 'player_choice'):
            choice = row[key]
            item[key] = ({name: choice[name] for name in ('option_id', 'action',
                'expected_placement', 'standard_error')} if choice is not None else None)
        item['unavailable'] = row['unavailable']
        context = next(context for context in report.evidence['replay']['contexts']
            if context['log_seq'] == row['log_seq'])
        frames = [event for event in report.evidence['replay']['observations']
            if event['kind'] == 'keyframe' and event['seq'] <= row['log_seq']
            and datetime.fromisoformat(event['timestamp']) <= datetime.fromisoformat(context['snapshot']['captured_at'])
            and isinstance(event['payload'].get('path'),str)
            and re.fullmatch(r'media/[0-9a-f]{32}\.webp',event['payload']['path'])]
        if frames:
            frame = frames[-1]
            item['keyframe'] = {'media_name':frame['payload']['path'],'reason':None,
                'logged_reason':frame['payload'].get('reason'),'timestamp':frame['timestamp'],'log_seq':frame['seq']}
        else:
            item['keyframe'] = {'media_name': None, 'reason': 'logged_keyframe_unavailable'}
        top5.append(item)
    summary['top5'] = top5
    summary['section_paths'] = {name: ['surface', name] for name in report.surface}
    summary['section_paths']['debug'] = ['debug']
    return summary


class ReviewService:
    def __init__(self, sessions, data_store, *, repository, hooks=None, hook_version='default'):
        self.sessions, self.data_store = sessions, data_store
        self.producer = ReplayProducer(sessions, data_store, repository=repository,
            hooks=hooks, hook_version=hook_version, decision_segmentation='semantic')

    def job_identity(self, game_id):
        """Name one finished historical input and the actual running review code."""
        events = validate_events(self.sessions.read_events(game_id), game_id)
        events = [event for event in events if event['kind'] != 'replay_cache']
        data = self.data_store.get(events[0]['payload']['data_snapshot_id'])
        identity = replay_identity(self.producer.repository, events, data,
            self.producer.hooks, self.producer.hook_version)
        if not identity['finished']:
            raise ValueError('Review job requires a finished game log')
        return {'job_id': digest({'game_id': str(game_id), 'identity': identity,
                'report_schema_version': 1}),
            'game_id': str(game_id), 'engine_version': identity['commit'],
            'data_snapshot_id': data.snapshot_id, 'log_hash': identity['log_hash'],
            'schema_version': 1, 'identity': identity}

    def produce(self, game_id, *, expected_job_id=None):
        """Compute private evidence; return only the currently permitted summary."""
        job = self.job_identity(game_id)
        if expected_job_id is not None and job['job_id'] != expected_job_id:
            raise ValueError('Review job identity changed before evaluation')
        batch = self.producer.produce(game_id)
        if not batch.identity['finished']:
            raise ValueError('Post-game review requires a finished game log')
        data = self.data_store.get(batch.identity['data_snapshot_id'])
        report = ReviewPolicy(min_cost=data.tunables['review_min_cost'].value).build(batch, data=data)
        document = report.to_dict()
        document['summary'] = surface_summary(report)
        graph = EvidenceGraph.factor(document)
        if self.job_identity(game_id) != job:
            raise ValueError('Review job identity changed during evaluation')
        self.sessions.write_review(str(game_id), {'schema_version': 1,
            'report_id': graph.root_id, 'evidence_graph': graph.to_dict(),
            'decision_ids': [row['moment_id'] for row in report.moments]},
            engine_version=batch.identity['commit'], data_snapshot_id=batch.identity['data_snapshot_id'],
            expected_log_hash=batch.identity['log_hash'])
        return self.summary(str(game_id))

    def _read_graph(self, game_id):
        stored = self.sessions.read_review(str(game_id))  # Authoritative lock and log-hash check on every route.
        if stored is None:
            raise ValueError('Review is not ready')
        body = stored['review']
        if body.get('schema_version') != 1:
            raise ValueError('Review report schema unavailable; regenerate')
        graph = EvidenceGraph.from_dict(body['evidence_graph'])
        if graph.root_id != body['report_id']:
            raise ValueError('Review evidence identity mismatch')
        if graph.resolve(path=('game_id',)) != str(game_id):
            raise ValueError('Review belongs to another game')
        return graph

    def summary(self, game_id):
        game_id = str(game_id)
        game = next((row for row in self.sessions.list_games() if row['game_id'] == game_id), None)
        if game is None:
            raise ValueError('Review requires a game log')
        if game['review_locked']:
            return {'schema_version': 1, 'game_id': game_id, 'locked': True,
                'report_id': None, 'evidence_id': None, 'finished': game['finished'],
                'placement': {'value': None, 'reason': 'review_locked'},
                'category_costs': {'value': None, 'reason': 'review_locked'},
                'follow_rate': {'value': None, 'reason': 'review_locked'}, 'top5': []}
        graph = self._read_graph(game_id)
        return graph.resolve(path=('summary',)) | {'schema_version': 1,
            'game_id': game_id, 'locked': False, 'finished': game['finished'],
            'report_id': graph.root_id, 'evidence_id': graph.root_id}

    def detail(self, game_id, *, path=(), cursor=0, limit=32, max_bytes=65536):
        graph = self._read_graph(game_id)
        return graph.page(path=path, cursor=cursor, limit=limit, max_bytes=max_bytes)

    def what_if(self, game_id, moment_id, option_id):
        graph = self._read_graph(game_id)
        count = graph.page(path=('moments',), limit=1)['total']
        for index in range(count):
            if graph.resolve(path=('moments', index, 'moment_id')) != moment_id:
                continue
            path = graph.resolve(path=('moments', index, 'evidence_path'))
            option_path = tuple(path)+('options',)
            option_count = graph.page(path=option_path, limit=1)['total']
            for option_index in range(option_count):
                member = option_path+(option_index,)
                if graph.resolve(path=member+('option_id',)) == option_id:
                    return {'option_id': option_id,
                        'expected_placement': graph.resolve(path=member+('expected_placement',)),
                        'standard_error': graph.resolve(path=member+('standard_error',)),
                        'evidence_id': graph.root_id, 'path': list(member), 'simulation': 'already_scored'}
            raise ValueError('What-if requires an already scored option')
        raise ValueError('Unknown review moment')

    def tag(self, game_id, moment_id, tag):
        self._read_graph(game_id)
        self.sessions.set_review_tag(str(game_id), moment_id, tag)
