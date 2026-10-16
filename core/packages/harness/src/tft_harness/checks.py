"""Hand-set diagnostics are observational reports, never fitted objectives/gates."""
from collections import Counter, defaultdict
from datetime import datetime
from dataclasses import replace

from tft_engine.classifier import classify
from tft_engine.planning import owned_board, read, required
from tft_review.contracts import frozen_json

from .diagnostics import aggregate, combine_aggregates


def confidence_checks(rows):
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get('confidence_band'):
            grouped[row['metric']][row['confidence_band']].append((row['game_id'], row['loss']))
    metrics = {}
    for metric, bands in grouped.items():
        samples = {band: aggregate(bands[band]) for band in ('low', 'medium', 'high')}
        values = [samples[band]['value'] for band in ('low', 'medium', 'high')]
        available = all(value is not None for value in values)
        metrics[metric] = {'bands': samples, 'ordering': {
            'status': ('pass' if values[0] >= values[1] >= values[2] else 'fail') if available else 'unavailable',
            'reason': None if available else 'missing_band_or_nonfinite_loss'}}
    available = bool(metrics) and all(row['ordering']['status'] != 'unavailable' for row in metrics.values())
    return {'by_metric': metrics, 'ordering': {'status': (
        'fail' if any(row['ordering']['status'] == 'fail' for row in metrics.values()) else 'pass') if available else 'unavailable',
        'reason': None if available else 'qualified_low_medium_high_bands_required'},
        'accuracy': 'equal-game mean loss within metric; lower loss is more accurate'}


def combine_checks(reports, rows):
    result = {'status': 'report_only', 'confidence_bands': confidence_checks(rows)}
    for name in ('classifier', 'board_reader_identity'):
        exclusions = Counter()
        for _, report in reports:
            exclusions.update(report[name]['excluded'])
        result[name] = combine_aggregates((game, report[name]) for game, report in reports)|{'excluded': dict(exclusions)}
    stages = {stage for _, report in reports for stage in report['classifier']['by_stage']}
    result['classifier']['by_stage'] = {stage: combine_aggregates(
        (game, report['classifier']['by_stage'][stage]) for game, report in reports
        if stage in report['classifier']['by_stage']) for stage in stages}
    result['classifier']['truth_sources'] = tuple(sorted({source for _, report in reports
        for source in report['classifier']['truth_sources']}))
    return result


def observational_checks(games, rows):
    classifier, classifier_excluded = [], Counter()
    stages, sources = defaultdict(list), set()
    reader, reader_excluded = [], Counter()
    for game in games:
        batch, data = game['batch'], game['data']
        # These checks require qualified terminal identity, not an arbitrary
        # last captured board. Outcome adapters own that qualification.
        outcome = game.get('outcome')
        terminal = own_terminal_board(batch, data)
        if terminal is not None:
            final_label = classify(terminal, data, limit=1)
            final_label = final_label[0].label if final_label else None
            seen = {}
            for context in batch.contexts:
                snapshot = batch.snapshot_for(context)
                if read(snapshot, data, 'phase') == 'end' or required(snapshot, data, ('board', 'bench')):
                    continue
                seen[snapshot.round_id.split('-')[0]] = snapshot
            for stage, snapshot in seen.items():
                labels = classify(owned_board(snapshot, data), data, limit=1)
                if labels and final_label is not None:
                    sample = (batch.game_id, int(labels[0].label == final_label))
                    classifier.append(sample)
                    stages[stage].append(sample)
                    sources.add('own_terminal_capture')
                else:
                    classifier_excluded['classifier_vocabulary_unavailable'] += 1
        elif not outcome:
            classifier_excluded['terminal_boards_unavailable'] += 1
        disagreements = [event for event in batch.observations
            if event['kind'] in ('reader_disagreement', 'reader_tracker_disagreement', 'board_read_disagreement')]
        if not disagreements:
            reader_excluded['no_reader_disagreement_observations'] += 1
        elif not outcome:
            reader_excluded['qualified_terminal_identity_unavailable'] += len(disagreements)
    return {'status': 'report_only', 'classifier': aggregate(classifier)|{'excluded': dict(classifier_excluded),
        'by_stage': {stage: aggregate(values) for stage, values in stages.items()}, 'truth_sources': tuple(sorted(sources))},
        'board_reader_identity': aggregate(reader)|{'excluded': dict(reader_excluded)},
        'confidence_bands': confidence_checks(rows)}


def own_terminal_board(batch, data):
    """An explicit fresh end-phase capture is final; an arbitrary last board is not."""
    ends = [event for event in batch.observations if event['kind'] == 'game_end']
    if not ends:
        return None
    end = ends[-1]
    candidates = [context for context in batch.contexts if context.log_seq < end['seq']
        and 'capture_gap' not in context.unavailable
        and datetime.fromisoformat(context.snapshot['captured_at']) <= datetime.fromisoformat(end['timestamp'])]
    if not candidates:
        return None
    snapshot = batch.snapshot_for(candidates[-1])
    if read(snapshot, data, 'phase') != 'end':
        return None
    snapshot = replace(snapshot, captured_at=datetime.fromisoformat(end['timestamp']))
    if required(snapshot, data, ('board', 'bench', 'inventory_complete')):
        return None
    return owned_board(snapshot, data)


def hand_set_checks(harness, game_ids=None, *, limit=20):
    report, _ = harness._evaluate(game_ids, harness.data_store)
    games = harness._games(game_ids)
    maximum_gold, maximum_caps, maximum_guides = 50, defaultdict(int), 1
    for game in games:
        data = harness.data_store.get(game['data_snapshot_id'])
        maximum_guides = max(maximum_guides, len(data.guides))
        for name in ('line_candidate_cap', 'challengers_simulated', 'slam_candidate_cap', 'open_candidate_count'):
            maximum_caps[name] = max(maximum_caps[name], int(data.tunables[name].value))
        for event in harness.sessions.read_events(game['game_id']):
            if event['kind'] == 'snapshot':
                gold = event['payload']['fields'].get('gold', {}).get('value')
                if type(gold) in (int, float):
                    maximum_gold = max(maximum_gold, int(gold))
    parameters = {'gold_floors': list(range(0, maximum_gold//10*10+1, 10)),
        'all_in_rounds_left': 1_000_000, 'stabilize_rounds_left': 1_000_000,
        'line_candidate_cap': max(10000, maximum_caps['line_candidate_cap']+1),
        'challengers_simulated': max(maximum_guides, maximum_caps['challengers_simulated']+1),
        'open_candidate_count': max(maximum_guides, maximum_caps['open_candidate_count']+1),
        'slam_candidate_cap': max(10000, maximum_caps['slam_candidate_cap']+1)}
    widened = dict(harness.advice_diff(parameters, game_ids, limit=limit))
    widened['parameters'] = parameters
    widened['budget'] = 'offline widened replay; no 100 ms budget; reported caps are explicit'
    widened['changed_share'] = widened['game_weighted_changed_share']
    return frozen_json(dict(report.metrics['hand_set_checks'])|{'widened_candidates': widened})
