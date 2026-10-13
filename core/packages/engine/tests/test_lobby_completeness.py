"""Roster-dependent advice requires the capture boundary's positive certificate."""
from dataclasses import replace
from datetime import timedelta

import pytest

from tft_engine import GameHistory, FieldValue, evaluate, snapshot_seed
from .test_planning import patch, snapshot


@pytest.mark.parametrize('certificate', [False, None, 1, 'true', 'missing', 'stale', 'low_confidence', 'low_roster_confidence', 'future'])
def test_incomplete_lobby_cannot_produce_full_roster_placement_or_reuse_qualified_state(certificate):
    data = patch()
    positive = snapshot(lobby_complete=True, pinned_line={'id': 'hold', 'levels': {}, 'rolls': {}})
    qualified = evaluate(positive, GameHistory(), data, 'review')
    assert qualified.line_results and qualified.comp_fits
    fields = dict(positive.fields)
    if certificate == 'missing':
        fields.pop('lobby_complete')
    elif certificate == 'stale':
        fields['lobby_complete'] = FieldValue(True, positive.captured_at-timedelta(seconds=3), 'fixture', .9)
    elif certificate == 'low_confidence':
        fields['lobby_complete'] = FieldValue(True, positive.captured_at, 'fixture', .1)
    elif certificate == 'low_roster_confidence':
        fields['lobby'] = replace(fields['lobby'], confidence=.1)
    elif certificate == 'future':
        fields['lobby_complete'] = FieldValue(True, positive.captured_at+timedelta(seconds=1), 'fixture', .9)
    else:
        fields['lobby_complete'] = FieldValue(certificate, positive.captured_at, 'fixture', .9)
    partial = replace(positive, fields=fields)
    result = evaluate(partial, GameHistory((positive,)), data, 'review')
    assert not result.line_results and not result.comp_fits
    assert any(advice.decision == 'econ' and advice.payload.get('paused')
        and 'lobby_complete' in advice.payload.get('missing', ()) for advice in result.advice)
    assert snapshot_seed(partial, data) != snapshot_seed(positive, data)


def certificate_projection(context):
    from tft_engine import Advice, best_choice_fit
    score, projected = best_choice_fit(context, {'lobby_complete': True}, hooks=())
    return (Advice('certificate_probe', 'Projection checked', 'information', 1, 'public_choice_probe',
        payload={'score': score, 'line_count': sum(len(rows) for rows in projected.line_results.values())}),)


def test_a_hypothetical_choice_cannot_certify_an_incomplete_original_roster():
    from tft_engine import DomainHook, win_probability
    hook = DomainHook('certificate_probe', (), advice=certificate_projection)
    complete = evaluate(snapshot(lobby_complete=True), GameHistory(), patch(), 'review', hooks=(hook,))
    incomplete = evaluate(snapshot(lobby_complete=False), GameHistory(), patch(), 'review', hooks=(hook,))
    complete_probe = next(advice for advice in complete.advice if advice.decision == 'certificate_probe')
    probe = next(advice for advice in incomplete.advice if advice.decision == 'certificate_probe')
    assert complete_probe.payload['score'] is not None
    assert complete_probe.payload['line_count'] > 0
    assert probe.payload == {'score': None, 'line_count': 0}
    assert win_probability(3, 3, 3, patch()) == .5  # Valid observed pairwise model remains available.


def test_uncertified_roster_preserves_qualified_static_tiers_and_base_own_layout():
    from .test_decisions import item_patch
    from .test_planning import tag
    from tft_engine import Board, Unit
    data = item_patch()
    data = replace(data, guides={key: replace(guide, positions={'a': 27}, source='owner')
        for key, guide in data.guides.items()}, augment_tiers={'x': 'S', 'y': 'A', 'z': 'B'},
        static=dict(data.static)|{'econ_augments': tag({})},
        tunables=dict(data.tunables)|{'augment_tier_delta': tag({'S': -.3, 'A': -.15, 'B': 0, 'silver': 0}),
            'augment_prior_strength': tag(100), 'augment_flag_prior_multiplier': tag(2), 'board_settle_seconds': tag(2)})
    state = snapshot(board=Board((Unit('a', position=0),)), bench=(), level=1,
        lobby_complete=False, comp_lock='A', board_settled_since=(snapshot().captured_at-timedelta(seconds=3)).isoformat())
    report = evaluate(state, GameHistory(), data, 'review')
    layout = next(advice for advice in report.advice if advice.decision == 'positioning'
        and advice.payload.get('operation') == 'layout')
    assert layout.payload['layout'][0]['cell'] == 27
    assert layout.payload['threats_available'] is False and layout.payload['threat_shares'] == {}
    offered = snapshot(phase='augment', planning_phase=False, lobby_complete=False,
        augment_tier='silver', augment_offers_complete=True,
        augments=tuple({'slot': index, 'augment_id': identity, 'reroll_available': False}
            for index, identity in enumerate(('x', 'y', 'z'))))
    choice = evaluate(offered, GameHistory(), data, 'review')
    assert not choice.line_results
    tiers = next(advice for advice in choice.advice if advice.payload.get('operation') == 'tiers')
    assert len(tiers.options) == 3
    assert all(option.expected_placement is None for option in tiers.options)


def test_direct_line_and_survival_probability_paths_cannot_treat_partial_rows_as_a_roster():
    from tft_data.models import DataError
    from tft_engine import Line, simulate_lines
    from tft_engine.comp_fit import rounds_left_to_live
    partial = snapshot(lobby_complete=False)
    with pytest.raises(DataError, match='lobby_complete'):
        simulate_lines(partial, GameHistory(), patch(), 'A', (Line('hold'),))
    with pytest.raises(DataError, match='lobby_complete'):
        rounds_left_to_live(partial, patch())
