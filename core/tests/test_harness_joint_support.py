"""Public whole-board frequencies become the qualified joint-support declaration."""
from dataclasses import replace

import pytest

from tft_data import DataError
from tft_engine import Board, TraitSighting, Unit
from tests.test_sighting_forecast import PUBLISHED, support_data


def unsupported(tmp_path):
    data = support_data(tmp_path)
    static = dict(data.static)
    static.pop('opponent_joint_support')
    return replace(data, static=static)


def population(data):
    return {'population': 'all_alive_boards_by_round_level', 'sampling': 'target_independent',
        'whole_boards': True, 'disjoint_observations': True, 'provider': 'public-fixture',
        'patch': data.patch, 'cohort': dict(data.sources['public-fixture'].cohort),
        'source_updated_at': PUBLISHED.isoformat()}


def board_rows():
    return [{'round_id': '3-2', 'level': 1, 'count': 150, 'board': Board((Unit('unit'),)).to_dict()},
        {'round_id': '3-2', 'level': 1, 'count': 450, 'board': Board((Unit('ice-unit'),)).to_dict()},
        {'round_id': '4-1', 'level': 2, 'count': 10, 'board': Board((Unit('unit'), Unit('ice-unit'))).to_dict()}]


def test_builder_declares_counted_boards_bound_to_the_qualified_provider(tmp_path):
    from tft_harness.joint_support import build_joint_support
    from tft_review.sighting_forecast import forecast_sighting

    data = unsupported(tmp_path)
    support, report = build_joint_support(board_rows(), data, provider='public-fixture',
        citation='Fixture public board export, 610 boards', qualification=population(data))
    declaration = support.value
    assert declaration['patch'] == data.patch
    assert declaration['source_updated_at'] == PUBLISHED.isoformat()
    assert set(declaration['rounds']) == {'3-2'}
    assert report['contexts'] == {'3-2/1': 600}
    assert report['thin_contexts'] == {'4-1/2': 10}
    supported = replace(data, static=dict(data.static) | {'opponent_joint_support': support})
    fire = forecast_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}), supported)
    assert fire.reason is None and fire.probability == pytest.approx(.25)
    missing = forecast_sighting(TraitSighting('rival', '4-1', 2, {'fire': 1, 'ice': 1}), supported)
    assert missing.reason == 'joint_sighting_support_context_unavailable'


@pytest.mark.parametrize('change', [
    lambda rows, data: (rows, replace(data, sources={})),
    lambda rows, data: (rows, replace(data, sources={name: replace(state, qualified=False)
        for name, state in data.sources.items()})),
    lambda rows, data: (rows, replace(data, sources={name: replace(state, patch='other')
        for name, state in data.sources.items()})),
    lambda rows, data: ([dict(rows[0], count=0)], data),
    lambda rows, data: ([dict(rows[0], board=Board((Unit('invented'),)).to_dict())], data),
])
def test_builder_rejects_unqualified_providers_and_invalid_board_rows(tmp_path, change):
    from tft_harness.joint_support import build_joint_support

    original = unsupported(tmp_path)
    qualification = population(original)
    rows, data = change(board_rows(), original)
    with pytest.raises(DataError):
        build_joint_support(rows, data, provider='public-fixture', citation='Fixture export', qualification=qualification)


def test_overlay_adds_support_only_to_snapshots_of_its_patch(tmp_path):
    from tft_harness.joint_support import JointSupportOverlay, build_joint_support

    data = unsupported(tmp_path)
    other = replace(data, snapshot_id='other-patch', patch='previous')
    support, _ = build_joint_support(board_rows(), data, provider='public-fixture', citation='Fixture export', qualification=population(data))

    class Store:
        def get(self, snapshot_id):
            return {data.snapshot_id: data, other.snapshot_id: other}[snapshot_id]

    overlay = JointSupportOverlay(Store(), {data.patch: support})
    assert overlay.get(data.snapshot_id).static['opponent_joint_support'] == support
    assert 'opponent_joint_support' not in overlay.get('other-patch').static
    assert overlay.identity == JointSupportOverlay(Store(), {data.patch: support}).identity


def test_final_board_statistics_do_not_qualify_an_all_alive_round_population(tmp_path):
    from tft_harness.joint_support import build_joint_support
    data = unsupported(tmp_path)
    for qualification in (None, population(data) | {'population': 'final_boards'},
            population(data) | {'sampling': 'target_trait_filtered'},
            population(data) | {'source_updated_at': 'older'}):
        with pytest.raises(DataError, match='population'):
            build_joint_support(board_rows(), data, provider='public-fixture',
                citation='Fixture export', qualification=qualification)
