"""Chronological outcome metrics from frozen historical replay contexts."""
from collections import Counter
from datetime import datetime
from math import ceil, log

from tft_data.models import DataError
from tft_review import ReplayProducer
from tft_review.predictions import fight_forecast

from .report import HarnessReport
from .measurement import mean_by_game
from .measurement import paired_game_comparison
from .overlay import TunableOverlay


def chronological_split(games):
    ordered = sorted(games, key=lambda game: (datetime.fromisoformat(game['date']), int(game['game_id'])))
    if len(ordered) < 2:
        return tuple(game['game_id'] for game in ordered), ()
    holdout = ceil(len(ordered)*.2)
    return (tuple(game['game_id'] for game in ordered[:-holdout]),
        tuple(game['game_id'] for game in ordered[-holdout:]))


class EvaluationHarness:
    def __init__(self, sessions, data_store, *, repository, hooks=None):
        self.sessions, self.data_store, self.repository, self.hooks = sessions, data_store, repository, hooks

    def fit(self, parameter_grid, *, metric='fight_log_loss', bootstrap_seed=0, bootstrap_draws=2000,
            max_candidates=256):
        from .fitting import fit
        return fit(self,parameter_grid,metric=metric,bootstrap_seed=bootstrap_seed,
            bootstrap_draws=bootstrap_draws,max_candidates=max_candidates)

    def evaluate(self, game_ids=None, *, candidate=None, bootstrap_seed=0, bootstrap_draws=2000):
        accepted, rows = self._evaluate(game_ids, self.data_store)
        if candidate is None:
            return accepted
        from dataclasses import replace
        overlay = TunableOverlay(self.data_store, candidate)
        proposed, proposed_rows = self._evaluate(game_ids, overlay, hook_version='candidate:'+overlay.identity)
        holdout = set(accepted.provenance['holdout_game_ids'])
        gates = {}
        for metric in accepted.metrics:
            original = [row for row in rows if row['metric'] == metric and row['game_id'] in holdout]
            changed = [row for row in proposed_rows if row['metric'] == metric and row['game_id'] in holdout]
            identity = lambda row: (row['game_id'], row['observation_seq'])
            old = {identity(row): row for row in original}
            new = {identity(row): row for row in changed}
            if old.keys() != new.keys():
                gates[metric] = {'status': 'unavailable', 'reason': 'candidate_changed_eligible_truth',
                    'accepted_rows': len(old), 'candidate_rows': len(new)}
                continue
            against = paired_game_comparison([(row['game_id'], new[key]['loss'], row['loss'])
                for key, row in old.items()], seed=bootstrap_seed, draws=bootstrap_draws)
            naive_rows = [(row['game_id'], new[key]['loss'], self._loss(metric, row['naive_prediction'], row['truth']))
                for key, row in old.items() if row['naive_prediction'] is not None]
            naive = paired_game_comparison(naive_rows, seed=bootstrap_seed, draws=bootstrap_draws)
            comparable = against['reason'] is None and naive['reason'] is None
            regression = {'status': 'unavailable', 'reason': against['reason']} if against['reason'] else {
                'status': 'fail' if against['lower'] > 0 else 'pass', 'reason': None}
            beats_naive = {'status': 'unavailable', 'reason': naive['reason']} if naive['reason'] else {
                'status': 'pass' if naive['upper'] < 0 else 'fail', 'reason': None}
            gates[metric] = {'status': ('fail' if against['lower'] > 0 or naive['upper'] >= 0 else 'pass')
                if comparable else 'unavailable',
                'reason': None if comparable else against['reason'] or naive['reason'],
                'sample_unit': 'game', 'eligible_game_ids': tuple(sorted({row['game_id'] for row in original})),
                'bootstrap_seed': bootstrap_seed, 'bootstrap_draws': bootstrap_draws,
                'interval_convention': 'percentile95; nearest-rank2.5/97.5',
                'no_regression': regression, 'beats_naive': beats_naive,
                'candidate_minus_accepted': against, 'candidate_minus_naive': naive}
        return replace(proposed, gates=gates, provenance=dict(proposed.provenance)|{
            'candidate': candidate, 'candidate_id': overlay.identity,
            'comparison_reference': 'historical effective tunables; immutable static/source pins retained',
            'gate_policy': 'no significant regression versus accepted; upper95 loss difference below zero versus naive'})

    def _evaluate(self, game_ids, data_store, *, hook_version='default'):
        games = [game for game in self.sessions.list_games()
            if game_ids is None or game['game_id'] in set(map(str, game_ids))]
        training, holdout = chronological_split([game for game in games if game['finished']])
        producer = ReplayProducer(self.sessions, data_store, repository=self.repository,
            hooks=self.hooks, hook_version=hook_version, decision_segmentation='semantic')
        rows, exclusions, manifest, examples = [], Counter(), [], []
        counts = Counter(total_games=len(games), finished_games=sum(game['finished'] for game in games),
            train_games=len(training), holdout_games=len(holdout),
            locked_games=sum(game['review_locked'] for game in games), known_rounds=0, gap_rounds=0, partial_games=0)
        for game in games:
            try:
                batch = producer.produce(game['game_id'])
                data = data_store.get(batch.identity['data_snapshot_id'])
            except (DataError, ValueError, OSError) as error:
                counts['missing_or_corrupt_data_games'] += 1
                manifest.append({'game_id': game['game_id'], 'eligible': False, 'reason': str(error)})
                continue
            known_rounds = {context.snapshot['round_id'] for context in batch.contexts}
            gap_rounds = {context.snapshot['round_id'] for context in batch.contexts
                if 'capture_gap' in context.unavailable or any(reason.startswith('stale_field:') for reason in context.unavailable)}
            gap_share = len(gap_rounds)/len(known_rounds) if known_rounds else None
            partial = gap_share is None or gap_share > .25
            counts['known_rounds'] += len(known_rounds)
            counts['gap_rounds'] += len(gap_rounds)
            counts['partial_games'] += partial
            manifest.append({'game_id': game['game_id'], 'date': game['date'], 'finished': game['finished'],
                'highest_mode': game['mode'], 'review_locked': game['review_locked'], 'patch': game['patch'],
                'set_id': game['set_id'], 'data_snapshot_id': data.snapshot_id, 'partial': partial,
                'gap_share': gap_share, 'split': 'holdout' if game['game_id'] in holdout else 'train',
                'truth_sources': ['capture_log'], 'eligible': True})
            game_rows, game_excluded = self._fight_rows(batch, data)
            rows.extend(game_rows)
            exclusions.update(game_excluded)
            if not game['review_locked']:
                examples.extend(row for row in game_rows)
        stage_wins = {}
        for row in rows:
            if row['metric'] == 'fight_brier' and row['game_id'] in training:
                stage_wins.setdefault(row['stage'], []).append(row['truth'])
        for row in rows:
            if row['metric'] in {'fight_brier', 'fight_log_loss'}:
                outcomes = stage_wins.get(row['stage'], [])
                row['naive_prediction'] = sum(outcomes)/len(outcomes) if outcomes else None
        metrics = {}
        for name in ('fight_brier', 'fight_log_loss', 'damage_mae'):
            selected = [row for row in rows if row['metric'] == name]
            losses = [row['loss'] for row in selected]
            naive = [(row['game_id'], self._loss(name, row['naive_prediction'], row['truth']))
                for row in selected if row['naive_prediction'] is not None]
            hard_misses = sum(loss is None for loss in losses)
            naive_hard_misses = sum(loss is None for _, loss in naive)
            metrics[name] = {'value': mean_by_game((row['game_id'], row['loss']) for row in selected),
                'reason': 'infinite_log_loss' if hard_misses else None if losses else 'no_eligible_truth',
                'hard_misses': hard_misses, 'eligible_rows': len(selected),
                'eligible_games': len({row['game_id'] for row in selected}),
                'excluded': {reason: count for (metric, reason), count in exclusions.items() if metric == name},
                'naive': {'value': mean_by_game(naive),
                    'eligible_rows': len(naive), 'hard_misses': naive_hard_misses,
                    'reason': 'infinite_log_loss' if naive_hard_misses else None if naive else 'no_training_baseline'}}
        gates = {name: {'status': 'unavailable', 'reason': 'insufficient_holdout_games'} for name in metrics}
        return HarnessReport(metrics, gates, counts, tuple(examples), tuple(manifest), {
            'chronological_policy': 'oldest80/newest20; holdout_count=ceil(N*.2); timestamp,numeric_id tie-break',
            'training_game_ids': training, 'holdout_game_ids': holdout,
            'evaluation_scope': 'all eligible rows; gates use holdout only',
            'metric_weighting': 'equal games; mean eligible rows within each game',
            'outcome_policy': 'win/loss Bernoulli; draw is explicitly excluded'}), rows

    @staticmethod
    def _loss(metric, prediction, truth):
        if metric == 'fight_brier':
            return (prediction-truth)**2
        if metric == 'fight_log_loss':
            probability = prediction if truth else 1-prediction
            return -log(probability) if probability > 0 else None
        return abs(prediction-truth)

    def _fight_rows(self, batch, data):
        rows, excluded = [], Counter()
        metrics = ('fight_brier', 'fight_log_loss', 'damage_mae')
        for start in (event for event in batch.observations if event['kind'] == 'fight_start'):
            payload = start['payload']
            candidates = [context for context in batch.contexts if context.log_seq < start['seq']
                and context.snapshot['round_id'] == payload['round_id']
                and datetime.fromisoformat(context.timestamp) <= datetime.fromisoformat(start['timestamp'])]
            context = candidates[-1] if candidates else None
            results = [event for event in batch.observations if event['seq'] > start['seq']
                and event['kind'] in {'fight_result', 'fight_incomplete'}
                and event['payload'].get('round_id') == payload['round_id']
                and event['payload'].get('opponent_id') == payload['opponent_id']]
            reason = ('capture_gap' if context and 'capture_gap' in context.unavailable else
                'missing_prefight_snapshot' if context is None else
                'unknown_fight' if len(results) != 1 or results[0]['kind'] == 'fight_incomplete' else
                'draw_not_bernoulli' if results[0]['payload'].get('result') == 'draw' else None)
            if reason:
                excluded.update((metric, reason) for metric in metrics)
                continue
            outcome = results[0]['payload']
            try:
                forecast = fight_forecast(batch, context, data, opponent_id=payload['opponent_id'],
                    at=datetime.fromisoformat(start['timestamp']))
                stage = int(context.snapshot['round_id'].split('-')[0])
                probability = forecast['win_probability']
                truth = {'win': 1, 'loss': 0}.get(outcome.get('result'))
                if truth is None:
                    raise DataError('unknown_fight')
                for metric in ('fight_brier', 'fight_log_loss'):
                    rows.append({'game_id': batch.game_id, 'log_seq': context.log_seq, 'observation_seq': start['seq'], 'stage': stage,
                        'metric': metric, 'prediction': probability, 'truth': truth,
                        'loss': self._loss(metric, probability, truth), 'naive_prediction': None,
                        'data_snapshot_id': data.snapshot_id, 'seed': context.seed,
                        'own_power': forecast['own_power'], 'opponent_power': forecast['opponent_power'],
                        'opponent_warning': forecast['opponent_warning']})
                if truth == 0 and type(outcome.get('hp_lost')) in (int, float) and outcome['hp_lost'] >= 0:
                    base = forecast['naive_damage']
                    prediction = forecast['predicted_hp_loss']
                    rows.append({'game_id': batch.game_id, 'log_seq': context.log_seq, 'observation_seq': start['seq'], 'stage': stage,
                        'metric': 'damage_mae', 'prediction': prediction, 'truth': outcome['hp_lost'],
                        'loss': abs(prediction-outcome['hp_lost']), 'naive_prediction': base,
                        'data_snapshot_id': data.snapshot_id, 'seed': context.seed})
                else:
                    excluded[('damage_mae', 'not_a_known_hp_loss')] += 1
            except (DataError, KeyError, ValueError, TypeError) as error:
                excluded.update((metric, str(error)) for metric in metrics)
        return rows, excluded
