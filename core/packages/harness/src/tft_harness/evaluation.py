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
from .metrics import FITTED_METRICS, REPORT_METRICS, placement_rows, line_rows, hit_rows, opponent_board_rows


def chronological_split(games):
    ordered = sorted(games, key=lambda game: (datetime.fromisoformat(game['date']), int(game['game_id'])))
    if len(ordered) < 2:
        return tuple(game['game_id'] for game in ordered), ()
    holdout = ceil(len(ordered)*.2)
    return (tuple(game['game_id'] for game in ordered[:-holdout]),
        tuple(game['game_id'] for game in ordered[-holdout:]))


class EvaluationHarness:
    def __init__(self, sessions, data_store, *, repository, hooks=None, current_set=None):
        self.sessions, self.data_store, self.repository, self.hooks = sessions, data_store, repository, hooks
        current = getattr(data_store, 'current', None)
        self.current_set = str(current_set if current_set is not None else current.set_number) if current_set is not None or current else None

    def advice_diff(self, candidate, game_ids=None, *, limit=20):
        from .diagnostics import advice_diff
        return advice_diff(self, candidate, game_ids, limit=limit)

    def _games(self, game_ids=None, *, filter_set=True):
        selected = None if game_ids is None else set(map(str, game_ids))
        games = [game for game in self.sessions.list_games()
            if selected is None or game['game_id'] in selected]
        if not filter_set or self.current_set is None:
            return games
        result = []
        for game in games:
            set_id = game.get('set_id')
            if set_id is None:
                try:
                    set_id = self.data_store.get(game['data_snapshot_id']).set_number
                except (DataError, ValueError, OSError):
                    # Retain missing pins for the existing explicit data exclusion.
                    result.append(game)
                    continue
            if str(set_id) == self.current_set:
                result.append(game)
        return result

    def flip_rates(self, game_ids=None, *, candidate=None, limit=20):
        from .flips import flip_rates
        return flip_rates(self, game_ids, candidate=candidate, limit=limit)

    def hand_set_checks(self, game_ids=None, *, limit=20):
        from .checks import hand_set_checks
        return hand_set_checks(self, game_ids, limit=limit)

    def fit(self, parameter_grid, *, metric='fight_log_loss', bootstrap_seed=0, bootstrap_draws=2000,
            max_candidates=256):
        if metric not in FITTED_METRICS:
            raise ValueError('Report-only metrics cannot be fitted')
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
        for metric in FITTED_METRICS:
            original = [row for row in rows if row['metric'] == metric and row['game_id'] in holdout]
            changed = [row for row in proposed_rows if row['metric'] == metric and row['game_id'] in holdout]
            identity = lambda row: (row['game_id'], row['observation_seq'])
            old = {identity(row): row for row in original}
            new = {identity(row): row for row in changed}
            if old.keys() != new.keys():
                gates[metric] = {'status': 'unavailable', 'reason': 'candidate_changed_eligible_truth',
                    'accepted_rows': len(old), 'candidate_rows': len(new)}
                continue
            if any(old[key]['seed'] != new[key]['seed'] for key in old):
                raise ValueError('Candidate cannot preserve original replay seeds; evaluation gates unavailable')
            if any(old[key]['truth'] != new[key]['truth'] for key in old):
                gates[metric] = {'status': 'unavailable', 'reason': 'candidate_changed_eligible_truth'}
                continue
            against = paired_game_comparison([(row['game_id'], new[key]['loss'], row['loss'])
                for key, row in old.items()], seed=bootstrap_seed, draws=bootstrap_draws)
            naive_rows = [(row['game_id'], new[key]['loss'], self._naive_loss(row))
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
        if holdout:
            flips = self.flip_rates(holdout, candidate=candidate)
            gates.update({'flip_rate:'+domain: dict(value['gate'])|{'sample_unit': 'game', 'scope': 'chronological_holdout'}
                for domain, value in flips['domains'].items()})
        else:
            gates.update({'flip_rate:'+domain: {'status': 'unavailable', 'reason': 'insufficient_holdout_games'}
                for domain in proposed.metrics['flip_rates']})
        return replace(proposed, gates=gates, provenance=dict(proposed.provenance)|{
            'candidate': candidate, 'candidate_id': overlay.identity,
            'comparison_reference': 'historical effective tunables; immutable static/source pins retained',
            'gate_policy': 'no significant regression versus accepted; upper95 loss difference below zero versus naive'})

    def _evaluate(self, game_ids, data_store, *, hook_version='default'):
        games = self._games(game_ids)
        training, holdout = chronological_split([game for game in games if game['finished']])
        producer = ReplayProducer(self.sessions, data_store, repository=self.repository,
            hooks=self.hooks, hook_version=hook_version, decision_segmentation='semantic')
        rows, exclusions, manifest, examples = [], Counter(), [], []
        diagnostic_reports, check_reports, flip_games = [], [], {}
        from .diagnostics import report_diagnostics, combine_diagnostics
        from .checks import observational_checks, combine_checks
        from .flips import measure_flips, summarize_flips
        from tft_engine.registry import default_hooks
        hooks = default_hooks() if self.hooks is None else tuple(self.hooks)
        counts = Counter(total_games=len(games), finished_games=sum(game['finished'] for game in games),
            excluded_other_set_games=len(self._games(game_ids, filter_set=False))-len(games), previous_patch_games=0,
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
            outcome, outcome_reason = self._outcome(game['game_id'])
            if outcome_reason:
                counts[outcome_reason+'_games'] += 1
            known_rounds = {context.snapshot['round_id'] for context in batch.contexts}
            gap_rounds = {context.snapshot['round_id'] for context in batch.contexts
                if 'capture_gap' in context.unavailable or any(reason.startswith('stale_field:') for reason in context.unavailable)}
            gap_share = len(gap_rounds)/len(known_rounds) if known_rounds else None
            partial = gap_share is None or gap_share > .25
            previous_patch = batch.observations[0]['payload'].get('previous_patch', False) is True
            counts['previous_patch_games'] += previous_patch
            counts['known_rounds'] += len(known_rounds)
            counts['gap_rounds'] += len(gap_rounds)
            counts['partial_games'] += partial
            manifest.append({'game_id': game['game_id'], 'date': game['date'], 'finished': game['finished'],
                'highest_mode': game['mode'], 'review_locked': game['review_locked'], 'patch': game['patch'],
                'set_id': game['set_id'], 'data_snapshot_id': data.snapshot_id, 'partial': partial,
                'previous_patch': previous_patch,
                'replay_identity': dict(batch.identity),
                'gap_share': gap_share, 'split': 'holdout' if game['game_id'] in holdout else 'train',
                'truth_sources': ['capture_log']+(['riot_match'] if outcome else []),
                'outcome_status': outcome_reason or 'confirmed', 'eligible': True})
            game_rows, game_excluded = self._fight_rows(batch, data)
            sighting_rows, sighting_excluded = self._sighting_rows(batch, data)
            game_rows.extend(sighting_rows)
            game_excluded.update(sighting_excluded)
            placement, placement_excluded = placement_rows(batch, data, partial=partial, outcome=outcome)
            game_rows.extend(placement)
            game_excluded.update(placement_excluded)
            lines, line_excluded = line_rows(batch, data)
            game_rows.extend(lines)
            game_excluded.update(line_excluded)
            boards, board_excluded = opponent_board_rows(batch, data, outcome)
            game_rows.extend(boards)
            game_excluded.update(board_excluded)
            hits, hit_excluded = hit_rows(batch, data)
            game_rows.extend(hits)
            game_excluded.update(hit_excluded)
            for row in game_rows:
                row['previous_patch'] = previous_patch
            rows.extend(game_rows)
            exclusions.update(game_excluded)
            from tft_review import ReviewPolicy
            from .metrics import placement_truth
            review = ReviewPolicy(min_cost=float(data.tunables['review_min_cost'].value)).build(batch, data=data)
            try:
                saved = self.sessions.read_review(game['game_id'])
                tags = saved.get('tags', {}) if saved else None
            except (PermissionError, ValueError, OSError):
                tags = None
            diagnostic_game = {'batch': batch, 'data': data, 'review': review,
                'placement': placement_truth(batch, outcome)[0], 'tags': tags, 'outcome': outcome}
            diagnostic_reports.append((batch.game_id, report_diagnostics(game_rows, (diagnostic_game,), {
                'gap_rounds': len(gap_rounds), 'known_rounds': len(known_rounds)})))
            check_reports.append((batch.game_id, observational_checks((diagnostic_game,), game_rows)))
            measured, _ = measure_flips(batch, data, hooks)
            for domain, value in measured.items():
                flip_games.setdefault(domain, []).append((batch.game_id, value))
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
        for name in FITTED_METRICS+REPORT_METRICS:
            selected = [row for row in rows if row['metric'] == name]
            losses = [row['loss'] for row in selected]
            naive = [(row['game_id'], self._naive_loss(row))
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
            if name in REPORT_METRICS:
                metrics[name]['status'] = 'report_only'
        gates = {name: {'status': 'unavailable', 'reason': 'insufficient_holdout_games'} for name in FITTED_METRICS}
        metrics['report_only'] = combine_diagnostics(rows, diagnostic_reports, counts)
        metrics['hand_set_checks'] = combine_checks(check_reports, rows)
        # Field age is reported inside the capture-gap report, never as a gate.
        metrics['hand_set_checks']['field_age'] = {name: metrics['report_only'][name]
            for name in ('stale_fields', 'gap_share', 'gap_rounds', 'known_rounds')}
        metrics['flip_rates'] = {domain: summarize_flips(values) for domain, values in flip_games.items()}
        metrics['previous_patch_split'] = {label: {name: {
            'value': mean_by_game((row['game_id'], row['loss']) for row in rows
                if row['metric'] == name and row['previous_patch'] is flag),
            'eligible_rows': sum(row['metric'] == name and row['previous_patch'] is flag for row in rows)}
            for name in FITTED_METRICS+REPORT_METRICS}
            for label, flag in (('current_patch_static', False), ('previous_patch_static', True))}
        return HarnessReport(metrics, gates, counts, tuple(examples), tuple(manifest), {
            'current_set': self.current_set,
            'set_filter': 'current set only; missing legacy set metadata uses historical data pin',
            'chronological_policy': 'oldest80/newest20; holdout_count=ceil(N*.2); timestamp,numeric_id tie-break',
            'training_game_ids': training, 'holdout_game_ids': holdout,
            'evaluation_scope': 'all eligible rows; gates use holdout only',
            'metric_weighting': 'equal games; mean eligible rows within each game',
            'outcome_policy': 'win/loss Bernoulli; draw is explicitly excluded',
            'placement_naive': 'fresh positively complete alive lobby; average rank for tied HP',
            'report_only_policy': 'only FITTED_METRICS enter fitting/generic loss gates; flips have their own nonincrease gate',
            'sighting_naive': 'same joint support; persistence disabled'}), rows

    def _outcome(self, game_id):
        """Late match truth lives outside the log; absent or invalid truth is never inferred."""
        reader = getattr(self.sessions, 'read_outcome', None)
        if reader is None:
            return None, 'outcome_store_unavailable'
        try:
            outcome = reader(game_id)
        except (ValueError, OSError):
            return None, 'outcome_invalid'
        return (outcome, None) if outcome is not None else (None, 'outcome_unavailable')

    @classmethod
    def _naive_loss(cls, row):
        if 'naive_loss' in row:
            return row['naive_loss']
        return cls._loss(row['metric'], row['naive_prediction'], row['truth'])

    @staticmethod
    def _loss(metric, prediction, truth):
        if metric == 'fight_brier':
            return (prediction-truth)**2
        if metric in ('fight_log_loss', 'next_sighting_log_loss', 'hit_log_loss'):
            probability = prediction if truth else 1-prediction
            return -log(probability) if probability > 0 else None
        return abs(prediction-truth)

    def _sighting_rows(self, batch, data):
        from tft_engine import TraitSighting
        from tft_engine.opponents import infer_opponent
        from tft_review.sighting_forecast import forecast_sighting
        from tft_review.contracts import history_prefix
        from tft_data.capacity import integral

        rows, excluded = [], Counter()
        metric = 'next_sighting_log_loss'
        for event in (row for row in batch.observations if row['kind'] == 'sighting'):
            at = datetime.fromisoformat(event['timestamp'])
            candidates = [context for context in batch.contexts if context.log_seq < event['seq']
                and datetime.fromisoformat(context.snapshot['captured_at']) <= at]
            context = candidates[-1] if candidates else None
            try:
                if context is None:
                    raise DataError('no_causal_previous_sighting')
                if 'capture_gap' in context.unavailable:
                    raise DataError('capture_gap')
                # Gap intervals qualify capture validity retrospectively; they
                # never become extra information in the causal inference below.
                if any(row['kind'] == 'capture_gap'
                    and at < datetime.fromisoformat(row['payload']['end'])
                    and (row['payload']['start'] is None
                        or datetime.fromisoformat(row['payload']['start']) <= at)
                    for row in batch.observations):
                    raise DataError('capture_gap')
                previous = None
                history = history_prefix(batch.observations, through_seq=event['seq']-1,
                    captured_at=event['timestamp'])
                for sighting in history.sightings:
                    if sighting.opponent_id != event['payload']['opponent_id']:
                        continue
                    integral(sighting.level, 'prior sighting level', 1)
                    integral(sighting.hidden_traits, 'prior hidden trait count')
                    for count in sighting.traits.values():
                        integral(count, 'prior visible trait count', 1)
                    previous = infer_opponent(sighting, data, previous=previous)
                    if previous.fallback_reason:
                        raise DataError('previous_inference_unavailable: '+previous.fallback_reason)
                if previous is None:
                    raise DataError('no_causal_previous_sighting')
                target = TraitSighting.from_dict(dict(event['payload'])|{'read_at':event['timestamp']})
                predicted = forecast_sighting(target, data, previous=previous)
                naive = forecast_sighting(target, data, previous=previous, persistence=False)
                if predicted.reason or naive.reason:
                    raise DataError(predicted.reason or naive.reason)
                rows.append({'game_id':batch.game_id, 'log_seq':context.log_seq,
                    'observation_seq':event['seq'], 'stage':int(target.round_id.split('-')[0]),
                    'metric':metric, 'prediction':predicted.probability,
                    'log_probability':predicted.log_probability, 'truth':True,
                    'loss':-predicted.log_probability if predicted.log_probability is not None else None,
                    'naive_prediction':naive.probability,
                    'naive_loss':-naive.log_probability if naive.log_probability is not None else None,
                    'naive_log_probability':naive.log_probability,
                    'data_snapshot_id':data.snapshot_id, 'seed':context.seed,
                    'source':predicted.source, 'prefix_through_seq':event['seq']-1,
                    'previous_round_id':previous.round_id,
                    'conditioning':{'round_id':target.round_id, 'level':target.level},
                    'target':dict(event['payload'])})
            except (DataError, KeyError, ValueError, TypeError) as error:
                excluded[(metric,str(error))] += 1
        return rows, excluded

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
                        'confidence': forecast['confidence'],
                        'confidence_band': ('high' if forecast['confidence'] >= data.tunables['confidence_high_min'].value else
                            'medium' if forecast['confidence'] >= data.tunables['confidence_medium_min'].value else 'low'),
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
