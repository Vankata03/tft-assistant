"""Full capture behavior through snapshots and durable logs."""
from datetime import datetime, timedelta, timezone

from PIL import Image
import pytest

from tft_capture.ocr import NameCatalog, TextLine
from tft_capture.pipeline import CapturePipeline
from tft_capture.vision import VisionRead
from tft_core.storage import SessionStore


class OCRFrames:
    source = "recorded-external-ocr"

    def __init__(self, values):
        self.values = values

    def read(self, image, *, region):
        return self.values.get(region, [])


class VisualFrames:
    """Recorded external recognizer observations, never application collaborators."""
    source = "recorded-external-vision"

    def __init__(self, values, complete=False):
        self.values, self.complete = values, complete

    def read(self, image, *, regions, own_view):
        return VisionRead(self.values, self.source, .95, self.complete)


def capture(tmp_path, values, *, visual=None, catalog=None, extra=(), **kwargs):
    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    logs.start_game("900")
    ocr = OCRFrames(values)
    pipeline = CapturePipeline(
        "900", ocr=ocr, sink=logs, catalog=catalog or NameCatalog(),
        own_player_name="Owner", visual_reader=visual,
        regions={name: (0, 0, 1, 1) for name in (*values, *extra)}, **kwargs,
    )
    return pipeline, logs, ocr


NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)
WHITE = Image.new("RGB", (100, 100), "white")
BLACK = Image.new("RGB", (100, 100), "black")


def test_own_traits_and_lux_origin_remain_separate_from_base_classifier_identity(tmp_path):
    visual = VisualFrames({"board": {"units": [{"unit_id": "lux-base", "stars": 1,
        "items": [], "position": 3}], "bench": []}}, complete=True)
    values = {"stage": [TextLine("4-2")], "scouted": [TextLine("Owner Level 8")],
              "traits": [TextLine("Inferno 4"), TextLine("Avatar 1"), TextLine("0+")],
              "origin": [TextLine("Origin: Inferno")]}
    pipeline, logs, ocr = capture(tmp_path, values, visual=visual, extra=("board",),
        catalog=NameCatalog({"traits": {"inferno": "Inferno", "avatar": "Avatar"}}))
    first = pipeline.tick(WHITE, timestamp=NOW)
    assert first["fields"]["own_trait_counts"]["value"] == {"inferno": 4, "avatar": 1}
    assert first["fields"]["lux_origin"]["value"] == "inferno"
    assert first["fields"]["board"]["value"]["trait_counts"] == {"inferno": 4, "avatar": 1}
    assert first["fields"]["board"]["value"]["units"][0]["unit_id"] == "lux-base"
    ocr.values["scouted"] = [TextLine("Opponent Level 8")]
    ocr.values["traits"] = [TextLine("Inferno 2"), TextLine("0+")]
    second = pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=3))
    assert second["fields"]["own_trait_counts"]["read_at"] == NOW.isoformat()
    assert second["fields"]["lux_origin"]["read_at"] == NOW.isoformat()
    assert "own_trait_counts" in second["stale_fields"]
    assert second["fields"]["sighting"]["value"]["traits"] == {"inferno": 2}
    assert not any(e["kind"] == "sighting" for e in logs.read_events("900") if e["timestamp"] == NOW.isoformat())


def test_capture_phase_requires_positive_current_evidence_and_preserves_failure_timestamp(tmp_path):
    pipeline, _, ocr = capture(tmp_path, {"phase": [TextLine("Planning", .9)]})
    first = pipeline.tick(WHITE, timestamp=NOW)
    assert first["phase"] == "planning"
    assert first["fields"]["planning_phase"]["value"] is True
    ocr.values["phase"] = []
    failed = pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=3))
    assert failed["phase"] == "unknown"
    assert failed["fields"]["planning_phase"]["read_at"] == NOW.isoformat()
    ocr.values["phase"] = [TextLine("Combat", .85)]
    combat = pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=4))
    assert combat["phase"] == "combat"
    assert combat["fields"]["planning_phase"]["value"] is False


def test_complete_player_rows_publish_lobby_alive_and_own_hp_without_guessing_missing_rows(tmp_path):
    lines = [TextLine(f'{name} {hp}', box=(0, i/8, 1, (i+.7)/8))
        for i, (name, hp) in enumerate([('Owner', 73), ('Alpha', 84), ('Beta', 66),
            ('Gamma', 51), ('Delta', 40), ('Echo', 31), ('Foxtrot', 12), ('Gone', 0)])]
    pipeline, _, ocr = capture(tmp_path, {"players": lines, "streak": [TextLine("-3")]})
    first = pipeline.tick(WHITE, timestamp=NOW)
    lobby = first["fields"]["lobby"]["value"]
    assert first["fields"]["lobby_complete"]["value"] is True
    assert lobby["Owner"]["hp"] == 73
    assert lobby["Gone"]["alive"] is False
    assert first["fields"]["hp"]["value"] == 73
    assert first["fields"]["streak"]["value"] == -3
    ocr.values["players"] = lines[:-1]
    partial = pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=3))
    assert partial["fields"]["lobby_complete"]["value"] is False
    assert partial["fields"]["lobby"]["read_at"] == NOW.isoformat()
    assert "lobby" in partial["stale_fields"]


def test_augment_offer_requires_read_tier_and_each_reroll_flag_and_dismissal_is_not_pick(tmp_path):
    names = {'a': 'First Choice', 'b': 'Second Choice', 'c': 'Third Choice'}
    rows = [TextLine(name, box=(i/3+.01, .4, (i+1)/3-.01, .5))
        for i, name in enumerate(names.values())]
    rows += [TextLine('Gain power', box=(.02, .55, .31, .7))]
    visual = VisualFrames({'augment_tier': 'gold', 'augment_rerolls': {'0': True, '1': False, '2': True}})
    pipeline, logs, ocr = capture(tmp_path, {'cards': rows}, visual=visual,
        catalog=NameCatalog({'augments': names}))
    first = pipeline.tick(WHITE, timestamp=NOW)
    assert first['fields']['augment_offers_complete']['value'] is True
    assert first['fields']['augments']['value'] == [
        {'slot': 0, 'augment_id': 'a', 'name': 'First Choice', 'text': 'Gain power', 'tier': 'gold', 'reroll_available': True},
        {'slot': 1, 'augment_id': 'b', 'name': 'Second Choice', 'text': '', 'tier': 'gold', 'reroll_available': False},
        {'slot': 2, 'augment_id': 'c', 'name': 'Third Choice', 'text': '', 'tier': 'gold', 'reroll_available': True},
    ]
    ocr.values['cards'] = []
    visual.values = {}
    second = pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=3))
    assert second['fields']['augments']['read_at'] == NOW.isoformat()
    assert 'held_augments' not in second['fields']
    assert [e['kind'] for e in logs.read_events('900')].count('augment_offer') == 1
    assert not any(e['kind'] == 'augment_pick' for e in logs.read_events('900'))


def test_real_visual_templates_confirm_rerolls_and_complete_item_slots_and_omit_failed_slots(tmp_path):
    import numpy as np
    from tft_capture.reader_assets import TemplateBank
    from tft_capture.surfaces import SurfaceReader, Signal

    patterns = {name: np.random.default_rng(seed).integers(0, 255, (20, 20, 3), dtype=np.uint8)
        for name, seed in [('gold', 1), ('ready', 2), ('used', 3), ('component', 4), ('_empty', 5)]}
    image = Image.new('RGB', (100, 100), 'black')
    for x, label in [(0, 'gold'), (20, 'ready'), (40, 'used'), (60, 'component'), (80, '_empty')]:
        image.paste(Image.fromarray(patterns[label][:, :, ::-1]), (x, 0))
    visual = SurfaceReader(
        signals=[Signal('cards', (0, 0, .2, .2), 'augment_tier', {'gold': patterns['gold']}),
                 Signal('cards', (.2, 0, .4, .2), 'augment_rerolls', {'true': patterns['ready'], 'false': patterns['used']}, index=0),
                 Signal('cards', (.4, 0, .6, .2), 'augment_rerolls', {'true': patterns['ready'], 'false': patterns['used']}, index=1)],
        items=TemplateBank({key: patterns[key] for key in ('component', '_empty')}),
        item_slots=[(.6, 0, .8, .2), (.8, 0, 1, .2)],
        item_categories={'component': 'component'},
    )
    pipeline, _, _ = capture(tmp_path, {'scouted': [TextLine('Owner Level 4')]},
        visual=visual, extra=('cards', 'item_bench'))
    first = pipeline.tick(image, timestamp=NOW)
    assert first['fields']['augment_tier']['value'] == 'gold'
    assert first['fields']['augment_rerolls']['value'] == {'0': True, '1': False}
    assert first['fields']['item_bench']['value'] == ['component']
    assert first['fields']['components']['value'] == ['component']
    assert first['fields']['item_inventory_complete']['value'] is True
    image.paste('black', (80, 0, 100, 20))
    failed = pipeline.tick(image, timestamp=NOW + timedelta(seconds=3))
    assert failed['fields']['item_inventory_complete']['value'] is False
    assert failed['fields']['item_bench']['read_at'] == NOW.isoformat()


def test_item_choice_icons_are_read_only_under_positive_choice_surface(tmp_path):
    import numpy as np
    from tft_capture.reader_assets import TemplateBank
    from tft_capture.surfaces import SurfaceReader, Signal

    patterns = {name: np.random.default_rng(seed).integers(0, 255, (20, 20, 3), dtype=np.uint8)
        for name, seed in [('item', 20), ('sword', 21), ('cape', 22)]}
    image = Image.new('RGB', (100, 100), 'black')
    for x, name in [(0, 'item'), (20, 'sword'), (40, 'cape')]:
        image.paste(Image.fromarray(patterns[name][:, :, ::-1]), (x, 0))
    reader = SurfaceReader(signals=[Signal('cards', (0, 0, .2, .2), 'choice_kind', {'item': patterns['item']})],
        items=TemplateBank({key: patterns[key] for key in ('sword', 'cape')}),
        item_offer_slots=[(.2, 0, .4, .2), (.4, 0, .6, .2)])
    pipeline, logs, _ = capture(tmp_path, {}, visual=reader, extra=('cards',))
    offer = pipeline.tick(image, timestamp=NOW)
    assert offer['fields']['item_offers']['value'] == [{'slot': 0, 'item_id': 'sword'}, {'slot': 1, 'item_id': 'cape'}]
    assert offer['fields']['item_offers_complete']['value'] is True
    assert [e['kind'] for e in logs.read_events('900')].count('item_offer') == 1
    image.paste('black', (0, 0, 20, 20))
    hidden = pipeline.tick(image, timestamp=NOW + timedelta(seconds=3))
    assert hidden['fields']['item_offers']['read_at'] == NOW.isoformat()
    assert 'item_offers' in hidden['stale_fields']


def test_carousel_reads_actual_cpu_classifier_crops_and_item_templates_without_reading_opponents(tmp_path):
    import numpy as np
    from tests.test_board_reader import _constant_onnx
    from tft_capture.board_reader import CPUClassifier
    from tft_capture.reader_assets import TemplateBank
    from tft_capture.surfaces import SurfaceReader, Signal

    _constant_onnx(tmp_path / 'carousel-model', ['Shen'], 'Shen')
    pixels = np.random.default_rng(50).integers(0, 255, (20, 20, 3), dtype=np.uint8)
    marker = np.random.default_rng(51).integers(0, 255, (20, 20, 3), dtype=np.uint8)
    image = Image.new('RGB', (100, 100), 'black')
    image.paste(Image.fromarray(marker[:, :, ::-1]), (0, 0))
    image.paste(Image.fromarray(pixels[:, :, ::-1]), (60, 0))
    reader = SurfaceReader(signals=[Signal('carousel', (0, 0, .2, .2), 'phase', {'carousel': marker})],
        items=TemplateBank({'cape': pixels}),
        carousel_classifier=CPUClassifier(tmp_path / 'carousel-model', 'unit_classifier', set_number=18),
        unit_ids={'Shen': 'shen'}, carousel_slots=[{'unit': (.2, 0, .6, .4), 'item': (.6, 0, .8, .2)}])
    pipeline, logs, _ = capture(tmp_path, {'scouted': [TextLine('Opponent Level 7')]},
        visual=reader, extra=('carousel', 'board'))
    observed = pipeline.tick(image, timestamp=NOW)
    assert observed['fields']['carousel']['value'] == [{'slot': 0, 'unit_id': 'shen', 'item_id': 'cape'}]
    assert observed['fields']['carousel_complete']['value'] is True
    assert observed['phase'] == 'carousel'
    assert 'board' not in observed['fields']
    assert [e['kind'] for e in logs.read_events('900')].count('carousel_offer') == 1


def test_partial_reader_recall_cannot_initialize_ownership_until_independent_slots_count_and_traits_agree(tmp_path):
    observations = [{'zone': 'board', 'position': 0, 'unit_id': 'shen', 'identity_confidence': .99, 'stars': 1, 'items': []}]
    visual = VisualFrames({'board_observations': observations,
        'slot_inventory': {'board_occupied': [0, 1], 'board_empty': list(range(2, 28)),
            'bench_occupied': [], 'bench_empty': list(range(9))}}, complete=True)
    pipeline, logs, _ = capture(tmp_path, {'scouted': [TextLine('Owner Level 2')],
        'unit_count': [TextLine('2/2')], 'traits': [TextLine('Defender 1'), TextLine('0+')]},
        extra=('board',), visual=visual, catalog=NameCatalog({'traits': {'defender': 'Defender'}}),
        unit_traits={'shen': {'defender': 1}})
    partial = pipeline.tick(WHITE, timestamp=NOW)
    assert partial['fields']['inventory_complete']['value'] is False
    assert 'owned_copies' not in partial['fields']
    assert not any(e['kind'] == 'ownership' for e in logs.read_events('900'))
    visual.values['board_observations'] = observations + [{**observations[0], 'position': 1}]
    complete = pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=.25))
    assert complete['fields']['inventory_complete']['value'] is True
    assert complete['fields']['owned_copies']['value'] == {'shen': 2}
    assert complete['fields']['board']['value']['trait_counts'] == {'defender': 1}
    ownership = [e for e in logs.read_events('900') if e['kind'] == 'ownership']
    assert ownership[-1]['payload'] == {'copies': {'shen': 2}, 'complete': True}
    assert any(e['kind'] == 'capture_conflict' for e in logs.read_events('900'))


def test_complete_ownership_sale_uses_pinned_refund_and_unknown_copy_gain_is_not_called_gift(tmp_path):
    board = {'zone': 'board', 'position': 0, 'unit_id': 'shen', 'identity_confidence': .99, 'stars': 1, 'items': []}
    bench = {**board, 'zone': 'bench', 'stars': 2}
    slots = {'board_occupied': [0], 'board_empty': list(range(1, 28)),
             'bench_occupied': [0], 'bench_empty': list(range(1, 9))}
    visual = VisualFrames({'board_observations': [board, bench], 'slot_inventory': slots}, complete=True)
    pipeline, logs, ocr = capture(tmp_path, {'stage': [TextLine('2-3')],
        'scouted': [TextLine('Owner Level 4')], 'gold': [TextLine('20')],
        'phase': [TextLine('Planning')], 'unit_count': [TextLine('1/4')],
        'traits': [TextLine('Defender 1'), TextLine('0+')]}, visual=visual, extra=('board',),
        catalog=NameCatalog({'traits': {'defender': 'Defender'}}), unit_traits={'shen': {'defender': 1}},
        sale_values={'shen': {1: 2, 2: 5, 3: 17}})
    pipeline.tick(WHITE, timestamp=NOW)
    visual.values = {'board_observations': [board], 'slot_inventory': {**slots, 'bench_occupied': [], 'bench_empty': list(range(9))}}
    ocr.values['gold'] = [TextLine('25')]
    pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=.25))
    sales = [e['payload'] for e in logs.read_events('900') if e['kind'] == 'sell']
    assert sales == [{'unit_id': 'shen', 'copies': 3, 'stars': 2, 'gold': 5}]
    visual.values = {'board_observations': [board, {**bench, 'stars': 1}], 'slot_inventory': slots}
    pipeline.tick(WHITE, timestamp=NOW + timedelta(seconds=.5))
    events = logs.read_events('900')
    assert not any(e['kind'] == 'unit_grant' for e in events)
    assert any(e['kind'] == 'tracking_ambiguity' and 'copy' in e['payload']['reason'] for e in events)


def test_opening_zero_ownership_needs_all_37_positive_empty_slots_and_empty_trait_panel(tmp_path):
    import numpy as np
    from tft_capture.surfaces import SurfaceReader, Signal

    empty = np.random.default_rng(77).integers(0, 255, (20, 20, 3), dtype=np.uint8)
    image = Image.new('RGB', (740, 20))
    for slot in range(37):
        image.paste(Image.fromarray(empty[:, :, ::-1]), (slot*20, 0))
    slots = [{'zone': 'board' if i < 28 else 'bench', 'position': i if i < 28 else i-28,
              'box': (i/37, 0, (i+1)/37, 1)} for i in range(37)]
    reader = SurfaceReader(unit_slots=slots, slot_templates={'_empty': empty},
        signals=[Signal('traits', (0, 0, 1/37, 1), 'trait_panel_empty', {'true': empty})])
    pipeline, logs, _ = capture(tmp_path, {'scouted': [TextLine('Owner Level 1')],
        'unit_count': [TextLine('0/1')]}, visual=reader, extra=('board', 'bench', 'traits'))
    known = pipeline.tick(image, timestamp=NOW)
    assert known['fields']['owned_copies']['value'] == {}
    assert known['fields']['inventory_complete']['value'] is True
    assert known['fields']['board']['value'] == {'units': [], 'bench': [], 'trait_counts': {}}
    image.paste('black', (720, 0, 740, 20))
    failed = pipeline.tick(image, timestamp=NOW + timedelta(seconds=3))
    assert failed['fields']['inventory_complete']['value'] is False
    assert failed['fields']['owned_copies']['read_at'] == NOW.isoformat()
    assert [e['kind'] for e in logs.read_events('900')].count('ownership') == 1


def test_confirmed_augment_pick_tracks_held_augments_once_and_restores_from_game_log(tmp_path):
    names = {'a': 'First Choice', 'b': 'Second Choice', 'c': 'Third Choice'}
    rows = [TextLine(name, box=(i/3+.01, .4, (i+1)/3-.01, .5)) for i, name in enumerate(names.values())]
    visual = VisualFrames({'augment_tier': 'gold', 'augment_rerolls': {'0': True, '1': True, '2': True},
        'held_augments': [], 'held_augments_complete': True})
    pipeline, logs, ocr = capture(tmp_path, {'cards': rows, 'scouted': [TextLine('Owner Level 4')],
        'stage': [TextLine('2-1')]}, visual=visual, catalog=NameCatalog({'augments': names}), extra=('board',))
    pipeline.tick(WHITE, timestamp=NOW)
    visual.values = {'confirmed_pick': {'kind': 'augment', 'slot': 1}}
    ocr.values['cards'] = []
    picked = pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=.25))
    assert picked['fields']['held_augments']['value'] == ['b']
    assert picked['fields']['held_augments_complete']['value'] is True
    pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=.5))
    events = logs.read_events('900')
    assert [e['kind'] for e in events].count('augment_pick') == 1
    resumed = CapturePipeline('900', ocr=OCRFrames({}), sink=logs, tracking_events=events, regions={'cards': (0, 0, 1, 1)})
    restored = resumed.tick(None, timestamp=NOW + timedelta(seconds=4))
    assert restored['fields']['held_augments']['value'] == ['b']
    assert restored['fields']['held_augments']['read_at'] == picked['captured_at']
    assert 'held_augments' in restored['stale_fields']


def test_calibrated_pick_confirmation_and_all_held_slots_require_positive_artwork(tmp_path):
    import numpy as np
    from tft_capture.reader_assets import TemplateBank
    from tft_capture.surfaces import Signal, SurfaceReader

    empty, first, picked = [np.random.default_rng(seed).integers(0, 255, (20, 20, 3), dtype=np.uint8) for seed in (8, 9, 10)]
    image = Image.new('RGB', (80, 20))
    for i, pixels in enumerate((first, empty, empty, picked)):
        image.paste(Image.fromarray(pixels[:, :, ::-1]), (i*20, 0))
    reader = SurfaceReader(augment_icons=TemplateBank({'a': first, '_empty': empty}),
        held_augment_slots=[(i/4, 0, (i+1)/4, 1) for i in range(3)],
        signals=[Signal('cards', (.75, 0, 1, 1), 'confirmed_pick', {'augment:1': picked})])
    pipeline, _, ocr = capture(tmp_path, {'scouted': [TextLine('Owner Level 4')]}, visual=reader, extra=('held_augments', 'cards'))
    snapshot = pipeline.tick(image, timestamp=NOW)
    assert snapshot['fields']['held_augments']['value'] == ['a']
    assert snapshot['fields']['held_augments_complete']['value'] is True
    assert snapshot['fields']['confirmed_pick']['value'] == {'kind': 'augment', 'slot': 1}
    image.paste('black', (40, 0, 60, 20))
    failed = pipeline.tick(image, timestamp=NOW + timedelta(seconds=3))
    assert failed['fields']['held_augments_complete']['value'] is False
    assert failed['fields']['held_augments']['read_at'] == NOW.isoformat()
    ocr.values['scouted'] = [TextLine('Opponent Level 5')]
    image.paste('black', (0, 0, 1, 1))
    opponent = pipeline.tick(image, timestamp=NOW + timedelta(seconds=6))
    assert opponent['fields']['held_augments_complete']['read_at'] == failed['captured_at']


def test_augment_reroll_requires_changed_offer_and_observed_consumed_reroll(tmp_path):
    names = {'a': 'First Choice', 'b': 'Second Choice', 'c': 'Third Choice', 'd': 'Fourth Choice'}
    def cards(ids):
        return [TextLine(names[identity], box=(i/3+.01, .4, (i+1)/3-.01, .5)) for i, identity in enumerate(ids)]
    visual = VisualFrames({'augment_tier': 'gold', 'augment_rerolls': {'0': True, '1': True, '2': True}})
    pipeline, logs, ocr = capture(tmp_path, {'cards': cards('abc')}, visual=visual, catalog=NameCatalog({'augments': names}))
    pipeline.tick(WHITE, timestamp=NOW)
    visual.values['augment_rerolls']['1'] = False
    ocr.values['cards'] = cards('adc')
    pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=.25))
    rerolls = [e['payload'] for e in logs.read_events('900') if e['kind'] == 'augment_reroll']
    assert rerolls == [{'slot': 1, 'before': 'b', 'after': 'd'}]
    visual.values['augment_rerolls'].update({'0': False, '2': False})
    ocr.values['cards'] = cards('bda')
    pipeline.tick(WHITE, timestamp=NOW + timedelta(seconds=.5))
    assert [e['payload']['slot'] for e in logs.read_events('900') if e['kind'] == 'augment_reroll'] == [1, 0, 2]
    del visual.values['augment_rerolls']['0']
    ocr.values['cards'] = cards('bdc')
    snapshot = pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=3))
    assert snapshot['fields']['augment_offers_complete']['value'] is False
    assert [e['kind'] for e in logs.read_events('900')].count('augment_reroll') == 3


def test_composed_visual_read_preserves_per_field_source_and_confidence_on_unchanged_pixels_and_gaps(tmp_path):
    class ComposedExternalRecognition:
        source = 'composed-external-recognition'
        def read(self, image, *, regions, own_view):
            return VisionRead({'phase': 'planning', 'planning_phase': True,
                'board': {'units': [], 'bench': [], 'trait_counts': None}}, self.source, .61,
                provenance={'phase': {'source': 'calibrated-phase-template', 'confidence': .98},
                    'board': {'source': 'pinned-unit-and-star-models', 'confidence': .73}})
    pipeline, _, _ = capture(tmp_path, {'scouted': [TextLine('Owner Level 4')]},
        visual=ComposedExternalRecognition(), extra=('board',))
    first = pipeline.tick(WHITE, timestamp=NOW)
    same = pipeline.tick(WHITE, timestamp=NOW + timedelta(seconds=3))
    failed = pipeline.tick(None, timestamp=NOW + timedelta(seconds=6))
    for snapshot in (first, same, failed):
        assert snapshot['fields']['phase']['source'] == 'calibrated-phase-template'
        assert snapshot['fields']['phase']['confidence'] == .98
        assert snapshot['fields']['board']['source'] == 'pinned-unit-and-star-models'
        assert snapshot['fields']['board']['confidence'] == .73
    assert same['fields']['board']['read_at'] == same['captured_at']
    assert failed['fields']['board']['read_at'] == same['captured_at']
    assert failed['phase'] == 'unknown'


def test_fight_logs_positive_opponent_result_and_hp_loss_but_no_result_from_phase_change(tmp_path):
    values = {'stage': [TextLine('3-2')], 'phase': [TextLine('Combat')], 'hp': [TextLine('72')],
        'fight_opponent': [TextLine('Opponent: Rival')], 'fight_result': []}
    pipeline, logs, ocr = capture(tmp_path, values, catalog=NameCatalog({'players': {'rival-id': 'Rival'}}))
    pipeline.tick(WHITE, timestamp=NOW)
    ocr.values.update(phase=[TextLine('Planning')], hp=[TextLine('61')])
    pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=1))
    assert not any(e['kind'] == 'fight_result' for e in logs.read_events('900'))
    ocr.values['fight_result'] = [TextLine('Defeat')]
    done = pipeline.tick(WHITE, timestamp=NOW + timedelta(seconds=1.25))
    outcomes = [e['payload'] for e in logs.read_events('900') if e['kind'] == 'fight_result']
    assert outcomes == [{'round_id': '3-2', 'opponent_id': 'rival-id', 'result': 'loss', 'hp_before': 72, 'hp_after': 61, 'hp_lost': 11}]
    assert done['fields']['last_fight']['value'] == outcomes[0]
    assert done['fields']['recent_opponents']['value'] == ['rival-id']
    assert done['fields']['recent_opponent_fights']['value'] == [{'opponent_id': 'rival-id', 'round_id': '3-2', 'read_at': NOW.isoformat()}]
    pipeline.tick(WHITE, timestamp=NOW + timedelta(seconds=1.5))
    assert [e['kind'] for e in logs.read_events('900')].count('fight_result') == 1
    ocr.values.update(stage=[TextLine('3-3')], phase=[TextLine('Combat')], hp=[TextLine('61')], fight_result=[])
    pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=2))
    pipeline.tick(None, timestamp=NOW + timedelta(seconds=3))
    ocr.values.update(fight_result=[TextLine('Victory')], hp=[])
    pipeline.tick(WHITE, timestamp=NOW + timedelta(seconds=5))
    assert [e['kind'] for e in logs.read_events('900')].count('fight_result') == 1


def test_unit_gift_needs_positive_receipt_and_independent_copy_gain(tmp_path):
    row = {'zone': 'board', 'position': 0, 'unit_id': 'shen', 'identity_confidence': .99, 'stars': 1, 'items': []}
    slots = {'board_occupied': [0], 'board_empty': list(range(1, 28)), 'bench_occupied': [], 'bench_empty': list(range(9))}
    visual = VisualFrames({'board_observations': [row], 'slot_inventory': slots}, complete=True)
    pipeline, logs, _ = capture(tmp_path, {'stage': [TextLine('2-3')], 'scouted': [TextLine('Owner Level 4')],
        'unit_count': [TextLine('1/4')], 'traits': [TextLine('Defender 1'), TextLine('0+')]},
        visual=visual, extra=('board',), catalog=NameCatalog({'traits': {'defender': 'Defender'}}),
        unit_traits={'shen': {'defender': 1}})
    pipeline.tick(WHITE, timestamp=NOW)
    visual.values.update(board_observations=[row, {**row, 'zone': 'bench'}],
        slot_inventory={**slots, 'bench_occupied': [0], 'bench_empty': list(range(1, 9))},
        grant_receipt={'source': 'encounter', 'unit_id': 'shen', 'copies': 1})
    pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=.25))
    grants = [e['payload'] for e in logs.read_events('900') if e['kind'] == 'unit_grant']
    assert grants == [{'source': 'encounter', 'unit_id': 'shen', 'copies': 1}]
    assert not any(e['kind'] == 'tracking_ambiguity' for e in logs.read_events('900'))
    visual.values.update(board_observations=[row, {**row, 'zone': 'bench'}, {**row, 'zone': 'bench', 'position': 1}],
        slot_inventory={**slots, 'bench_occupied': [0, 1], 'bench_empty': list(range(2, 9))})
    pipeline.tick(WHITE, timestamp=NOW + timedelta(seconds=.5))
    assert [e['kind'] for e in logs.read_events('900')].count('unit_grant') == 1
    assert any(e['kind'] == 'tracking_ambiguity' for e in logs.read_events('900'))


def test_visual_gift_receipt_never_appears_from_unmatched_artwork(tmp_path):
    import numpy as np
    from tft_capture.surfaces import Signal, SurfaceReader
    pixels = np.random.default_rng(88).integers(0, 255, (20, 20, 3), dtype=np.uint8)
    reader = SurfaceReader(signals=[Signal('receipt', (0, 0, 1, 1), 'grant_receipt', {'wisp:shen:1': pixels})])
    pipeline, logs, _ = capture(tmp_path, {}, visual=reader, extra=('receipt',))
    first = pipeline.tick(Image.fromarray(pixels[:, :, ::-1]), timestamp=NOW)
    assert first['fields']['grant_receipt']['value'] == {'source': 'wisp', 'unit_id': 'shen', 'copies': 1}
    failed = pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=3))
    assert failed['fields']['grant_receipt']['read_at'] == NOW.isoformat()
    assert 'grant_receipt' in failed['stale_fields']
    assert not any(e['kind'] == 'unit_grant' for e in logs.read_events('900'))


def test_capture_close_flushes_timestamped_real_video_and_open_gap_with_lossless_keyframe(tmp_path):
    import shutil
    import subprocess
    from pathlib import Path
    import pytest
    from tft_capture.media import SegmentRecorder
    if not shutil.which('ffmpeg'):
        pytest.skip('Actual ffmpeg codec qualification requires the installed encoder')
    pipeline, logs, _ = capture(tmp_path, {'phase': [TextLine('Planning')]})
    pipeline.video = SegmentRecorder(logs, executable=shutil.which('ffmpeg'), segment_seconds=5)
    logs.set_media_mode('full_video')
    pipeline.tick(WHITE, timestamp=NOW)
    pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=.25))
    path = logs.write_keyframe(WHITE, reason='check-lossless', timestamp=NOW.isoformat())
    pipeline.tick(None, timestamp=NOW + timedelta(seconds=.5))
    pipeline.close(timestamp=NOW + timedelta(seconds=1))
    pipeline.close(timestamp=NOW + timedelta(seconds=2))
    events = logs.read_events('900')
    videos = [e for e in events if e['kind'] == 'video']
    assert len(videos) == 1
    assert videos[0]['timestamp'] == NOW.isoformat()
    game_directory = logs.log_path('900').parent
    assert Image.open(game_directory / path).convert('RGB').tobytes() == WHITE.tobytes()
    video = game_directory / videos[0]['payload']['path']
    decoded = subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-i', str(video), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True)
    assert len(decoded.stdout) >= 2*100*100*3
    segments = [e['payload'] for e in events if e['kind'] == 'video_segment']
    assert segments[0]['frame_timestamps'] == [NOW.isoformat(), (NOW+timedelta(seconds=.25)).isoformat()]
    gaps = [e['payload'] for e in events if e['kind'] == 'capture_gap']
    assert gaps == [{'reason': 'window_unavailable', 'start': (NOW+timedelta(seconds=.5)).isoformat(), 'end': (NOW+timedelta(seconds=1)).isoformat()}]
    assert [e['kind'] for e in events].count('capture_closed') == 1


def test_pinned_lux_trait_variants_validate_complete_ownership_without_inventing_chosen_origin(tmp_path):
    from tft_data.models import DataSnapshot, Entity, TaggedValue
    data = DataSnapshot('pinned-18', '16.20', 18, static={'trait_rules': TaggedValue({
        'lux': {'replace': [{'avatar': 1, 'inferno': 2}, {'avatar': 1, 'ocean': 2}]}}, 'owner'),
        'sell_values': TaggedValue({'5': {'1': 5, '2': 14, '3': 44}}, 'owner')}, tunables={}, entities={
        'lux': Entity('lux', 'unit', 'Lux', cost=5, traits=('avatar',)),
        'inferno': Entity('inferno', 'trait', 'Inferno'), 'ocean': Entity('ocean', 'trait', 'Ocean'),
        'avatar': Entity('avatar', 'trait', 'Avatar')})
    row = {'zone': 'board', 'position': 0, 'unit_id': 'lux', 'identity_confidence': .99, 'stars': 1, 'items': []}
    visual = VisualFrames({'board_observations': [row], 'slot_inventory': {'board_occupied': [0],
        'board_empty': list(range(1, 28)), 'bench_occupied': [], 'bench_empty': list(range(9))}}, complete=True)
    ocr = OCRFrames({'scouted': [TextLine('Owner Level 8')], 'unit_count': [TextLine('1/8')],
        'traits': [TextLine('Inferno 2'), TextLine('Avatar 1'), TextLine('0+')]})
    logs = SessionStore(tmp_path / 'app', tmp_path / 'config', live_installed=True)
    logs.start_game('900')
    pipeline = CapturePipeline.from_data('900', data=data, ocr=ocr, sink=logs, visual_reader=visual,
        own_player_name='Owner', regions={name: (0, 0, 1, 1) for name in (*ocr.values, 'board')})
    first = pipeline.tick(WHITE, timestamp=NOW)
    assert first['data_snapshot_id'] == 'pinned-18'
    assert first['fields']['inventory_complete']['value'] is True
    assert first['fields']['board']['value']['trait_counts'] == {'inferno': 2, 'avatar': 1}
    assert 'lux_origin' not in first['fields']
    ocr.values['traits'] = [TextLine('Inferno 1'), TextLine('Avatar 1'), TextLine('0+')]
    failed = pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=.25))
    assert failed['fields']['inventory_complete']['value'] is False
    assert any(e['kind'] == 'capture_conflict' for e in logs.read_events('900'))


def equipped_item_capture(tmp_path, item, *, observed_traits=('Defender 1',)):
    from tft_data.models import DataSnapshot, Entity, TaggedValue

    data = DataSnapshot('pinned-items', '16.20', 18,
        static={'trait_rules': TaggedValue({}, 'owner')}, tunables={}, entities={
            'shen': Entity('shen', 'unit', 'Shen', traits=('defender',)),
            'defender': Entity('defender', 'trait', 'Defender'),
            'inferno': Entity('inferno', 'trait', 'Inferno'), item.id: item})
    row = {'zone': 'board', 'position': 0, 'unit_id': 'shen', 'identity_confidence': .99,
        'stars': 1, 'items': [item.id]}
    visual = VisualFrames({'board_observations': [row], 'slot_inventory': {
        'board_occupied': [0], 'board_empty': list(range(1, 28)),
        'bench_occupied': [], 'bench_empty': list(range(9))}}, complete=True)
    ocr = OCRFrames({'scouted': [TextLine('Owner Level 4')], 'unit_count': [TextLine('1/4')],
        'traits': [TextLine(text) for text in (*observed_traits, '0+')]})
    logs = SessionStore(tmp_path / 'app', tmp_path / 'config', live_installed=True)
    logs.start_game('900')
    pipeline = CapturePipeline.from_data('900', data=data, ocr=ocr, sink=logs,
        visual_reader=visual, own_player_name='Owner',
        regions={name: (0, 0, 1, 1) for name in (*ocr.values, 'board')})
    return pipeline.tick(WHITE, timestamp=NOW), logs.read_events('900')


def test_pinned_explicit_no_trait_grant_certifies_equipped_ordinary_item_and_logs_its_source(tmp_path):
    from tft_data.models import Entity, TaggedValue

    snapshot, events = equipped_item_capture(tmp_path, Entity('sword', 'item', 'Sword',
        values={'trait_grants': TaggedValue({}, 'owner', citation='reviewed item ledger', family='item-traits')}))
    assert snapshot['fields']['inventory_complete']['value'] is True
    assert snapshot['fields']['owned_copies']['value'] == {'shen': 1}
    assert 'pinned-item-traits:owner' in snapshot['fields']['inventory_complete']['source']
    read = next(event['payload'] for event in events if event['kind'] == 'board_read')
    assert read['item_trait_provenance'] == {'sword': {'value': {}, 'source': 'owner',
        'citation': 'reviewed item ledger', 'family': 'item-traits', 'data_snapshot_id': 'pinned-items'}}


def test_pinned_emblem_grant_must_agree_with_current_own_traits(tmp_path):
    from tft_data.models import Entity, TaggedValue

    emblem = Entity('emblem', 'item', 'Emblem', values={
        'trait_grants': TaggedValue({'inferno': 1}, 'patch-notes', citation='reviewed patch note')})
    complete, events = equipped_item_capture(tmp_path / 'matching', emblem,
        observed_traits=('Defender 1', 'Inferno 1'))
    assert complete['fields']['inventory_complete']['value'] is True
    read = next(event['payload'] for event in events if event['kind'] == 'board_read')
    assert read['item_trait_provenance']['emblem']['value'] == {'inferno': 1}
    assert read['item_trait_provenance']['emblem']['citation'] == 'reviewed patch note'
    conflict, events = equipped_item_capture(tmp_path / 'conflicting', emblem)
    assert conflict['fields']['inventory_complete']['value'] is False
    assert not any(event['kind'] == 'ownership' for event in events)


@pytest.mark.parametrize(('item_id', 'metadata', 'observed_traits'), [
    ('unknown', None, ('Defender 1',)),
    ('sword', {'defender': 0}, ('Defender 1',)),
    ('sword', {'inferno': True}, ('Defender 1', 'Inferno 1')),
    ('sword', {'defender': -1}, ('Defender 1',)),
    ('sword', {'inferno': 1.0}, ('Defender 1', 'Inferno 1')),
    ('sword', {'inferno': '1'}, ('Defender 1', 'Inferno 1')),
    ('sword', {'missing-trait': 1}, ('Defender 1',)),
    ('sword', {'shen': 1}, ('Defender 1',)),
    ('sword', {'': 1}, ('Defender 1',)),
    ('sword', [], ('Defender 1',)),
    ('sword', 0, ('Defender 1',)),
    ('', {}, ('Defender 1',)),
    (' sword ', {}, ('Defender 1',)),
])
def test_unknown_or_invalid_pinned_item_grants_cannot_certify_ownership(tmp_path, item_id, metadata, observed_traits):
    from tft_data.models import Entity, TaggedValue

    values = {} if metadata is None else {'trait_grants': TaggedValue(metadata, 'owner')}
    snapshot, events = equipped_item_capture(tmp_path, Entity(item_id, 'item', 'Sword', values=values),
        observed_traits=observed_traits)
    assert snapshot['fields']['inventory_complete']['value'] is False
    assert 'owned_copies' not in snapshot['fields']
    assert not any(event['kind'] == 'ownership' for event in events)
    read = next(event['payload'] for event in events if event['kind'] == 'board_read')
    assert read['item_trait_provenance'] == {}


def test_untagged_item_grants_do_not_replace_missing_pinned_provenance(tmp_path):
    from tft_data.models import Entity

    snapshot, events = equipped_item_capture(tmp_path, Entity('sword', 'item', 'Sword',
        values={'trait_grants': {}}))
    assert snapshot['fields']['inventory_complete']['value'] is False
    assert not any(event['kind'] == 'ownership' for event in events)


def test_capture_cli_uses_checked_calibration_artwork_and_logs_automatic_fields(tmp_path, capsys):
    import hashlib
    import json
    import numpy as np
    from tft_core.capture_cli import main
    pixels = np.random.default_rng(92).integers(0, 255, (20, 20, 3), dtype=np.uint8)
    image = tmp_path / 'frame.png'
    Image.fromarray(pixels[:, :, ::-1]).save(image)
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    profile = tmp_path / 'profile.json'
    profile.write_text(json.dumps({'version': 1, 'regions': {'scouted': [0, 0, 1, 1], 'phase': [0, 0, 1, 1]},
        'signals': [{'region': 'phase', 'box': [0, 0, 1, 1], 'field': 'phase',
            'templates': {'planning': {'file': 'frame.png', 'sha256': digest}}}]}))
    ocr = OCRFrames({'scouted': [TextLine('Owner Level 4')]})
    assert main(['inspect', '--profile', str(profile), '--images', str(image), '--game-id', '900',
        '--own-player', 'Owner', '--log-root', str(tmp_path/'logs'), '--start', NOW.isoformat()], ocr=ocr) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['snapshots'][0]['phase'] == 'planning'
    assert result['snapshots'][0]['fields']['scouted_player']['value'] == 'Owner'
    events = [json.loads(line) for line in (tmp_path/'logs/games/900/events.jsonl').read_text().splitlines()]
    assert any(event['kind'] == 'snapshot' for event in events)
    assert events[-1]['kind'] == 'capture_closed'
    previous = (tmp_path/'logs/games/900/events.jsonl').read_bytes()
    profile.write_text(profile.read_text().replace(digest, '0'*64))
    assert main(['inspect', '--profile', str(profile), '--images', str(image), '--game-id', '900',
        '--log-root', str(tmp_path/'logs')], ocr=ocr) == 2
    assert 'integrity' in json.loads(capsys.readouterr().out)['error']
    assert (tmp_path/'logs/games/900/events.jsonl').read_bytes() == previous


def test_reconnected_capture_restores_active_fight_from_log_before_positive_outcome(tmp_path):
    pipeline, logs, _ = capture(tmp_path, {'stage': [TextLine('4-1')], 'phase': [TextLine('Combat')],
        'hp': [TextLine('58')], 'fight_opponent': [TextLine('Opponent: Rival')]})
    pipeline.tick(WHITE, timestamp=NOW)
    resumed_ocr = OCRFrames({'stage': [TextLine('4-1')], 'phase': [TextLine('Planning')],
        'hp': [TextLine('47')], 'fight_result': [TextLine('Defeat')]})
    resumed = CapturePipeline('900', ocr=resumed_ocr, sink=logs, tracking_events=logs.read_events('900'),
        regions={name: (0, 0, 1, 1) for name in resumed_ocr.values})
    resumed.tick(None, timestamp=NOW + timedelta(seconds=.25))
    snapshot = resumed.tick(BLACK, timestamp=NOW + timedelta(seconds=1))
    assert snapshot['fields']['last_fight']['value'] == {'round_id': '4-1', 'opponent_id': 'Rival',
        'result': 'loss', 'hp_before': 58, 'hp_after': 47, 'hp_lost': 11}
    assert [e['kind'] for e in logs.read_events('900')].count('fight_start') == 1


def test_positive_held_augment_gain_confirms_pick_without_dismissal_or_slot_guess(tmp_path):
    names = {'a': 'First Choice', 'b': 'Second Choice', 'c': 'Third Choice'}
    rows = [TextLine(name, box=(i/3+.01, .4, (i+1)/3-.01, .5)) for i, name in enumerate(names.values())]
    visual = VisualFrames({'augment_tier': 'gold', 'augment_rerolls': {'0': True, '1': True, '2': True},
        'held_augments': [], 'held_augments_complete': True})
    pipeline, logs, ocr = capture(tmp_path, {'cards': rows, 'stage': [TextLine('2-1')],
        'scouted': [TextLine('Owner Level 4')]}, visual=visual, catalog=NameCatalog({'augments': names}), extra=('board',))
    pipeline.tick(WHITE, timestamp=NOW)
    visual.values = {'held_augments': ['b'], 'held_augments_complete': True}
    ocr.values['cards'] = []
    picked = pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=.25))
    assert picked['fields']['held_augments']['value'] == ['b']
    picks = [e['payload'] for e in logs.read_events('900') if e['kind'] == 'augment_pick']
    assert [row['augment_id'] for row in picks] == ['b']
    assert picks[0]['evidence'] == 'held_augment_gain'
    pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=.5))
    assert [e['kind'] for e in logs.read_events('900')].count('augment_pick') == 1


def test_positive_item_and_carousel_confirmations_reference_complete_offers_and_log_once(tmp_path):
    visual = VisualFrames({'item_offers': [{'slot': 0, 'item_id': 'sword'}, {'slot': 1, 'item_id': 'cape'}],
        'item_offers_complete': True, 'carousel': [{'slot': 2, 'unit_id': 'shen', 'item_id': 'cape'}],
        'carousel_complete': True})
    pipeline, logs, _ = capture(tmp_path, {'stage': [TextLine('2-4')]}, visual=visual, extra=('cards', 'carousel'))
    pipeline.tick(WHITE, timestamp=NOW)
    visual.values = {'confirmed_pick': {'kind': 'item', 'slot': 0}}
    pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=.25))
    visual.values = {'confirmed_pick': {'kind': 'carousel', 'slot': 2}}
    pipeline.tick(WHITE, timestamp=NOW + timedelta(seconds=.5))
    pipeline.tick(WHITE, timestamp=NOW + timedelta(seconds=.75))
    events = logs.read_events('900')
    assert [e['payload']['item_id'] for e in events if e['kind'] == 'item_pick'] == ['sword']
    assert [(e['payload']['unit_id'], e['payload']['item_id']) for e in events if e['kind'] == 'carousel_pick'] == [('shen', 'cape')]
    resumed = CapturePipeline('900', ocr=OCRFrames({}), sink=logs, tracking_events=events,
        visual_reader=VisualFrames({'board_observations': [{'zone': 'board', 'position': 0, 'unit_id': 'unknown',
            'identity_confidence': .1, 'stars': 1, 'items': ['cape']}]}), own_player_name='Owner',
        regions={'scouted': (0, 0, 1, 1), 'board': (0, 0, 1, 1)})
    resumed.ocr.values['scouted'] = [TextLine('Owner Level 4')]
    snapshot = resumed.tick(BLACK, timestamp=NOW + timedelta(seconds=1))
    assert snapshot['fields']['tracked_units']['value'][0]['unit_id'] == 'shen'
    assert snapshot['fields']['tracked_units']['value'][0]['copies'] == 1
    assert snapshot['fields']['inventory_complete']['value'] is False
    visual.values = {'item_offers_complete': False, 'confirmed_pick': {'kind': 'item', 'slot': 1}}
    pipeline.tick(BLACK, timestamp=NOW + timedelta(seconds=1))
    assert [e['kind'] for e in logs.read_events('900')].count('item_pick') == 1


def test_native_bgra_frame_copies_only_requested_regions_until_a_keyframe_is_needed(tmp_path):
    import numpy as np
    from tft_capture.frames import RegionFrame
    pixels = np.zeros((100, 200, 4), dtype=np.uint8)
    pixels[:, :, :3] = [7, 17, 27]
    pixels[:, :, 3] = 255
    frame = RegionFrame(pixels)
    logs = SessionStore(tmp_path/'app', tmp_path/'config', live_installed=True)
    logs.start_game('900')
    ocr = OCRFrames({'gold': [TextLine('27')]})
    pipeline = CapturePipeline('900', ocr=ocr, sink=logs, regions={'gold': (0, 0, .1, .1)})
    first = pipeline.tick(frame, timestamp=NOW)
    assert first['fields']['gold']['value'] == 27
    assert first['capture_copy']['full_rgb_bytes'] == 0
    assert first['capture_copy']['region_rgb_bytes'] == 20*10*3
    assert first['capture_copy']['region_rgb_copies'] == 1
    assert first['capture_copy']['full_rgb_copies'] == 0
    assert frame.crop((0, 0, 20, 10)).getpixel((0, 0)) == (27, 17, 7)
    pipeline.tick(frame, timestamp=NOW+timedelta(seconds=.25))
    assert not any(e['kind']=='keyframe' for e in logs.read_events('900'))
    # A changed shop produces a full lossless keyframe from the same original buffer.
    ocr.values['shop'] = [TextLine('Shen', box=(i*.2+.01,.82,i*.2+.13,.95)) for i in range(5)] + [TextLine('2', box=(i*.2+.16,.82,i*.2+.19,.95)) for i in range(5)]
    pipeline.catalog = NameCatalog({'units': {'shen':'Shen'}})
    pipeline.regions['shop'] = (0, .2, 1, .4)
    captured = pipeline.tick(frame, timestamp=NOW+timedelta(seconds=.5))
    assert captured['capture_copy']['full_rgb_bytes'] == 200*100*3
    assert captured['capture_copy']['full_rgb_copies'] == 1
    keyframe = next(e for e in logs.read_events('900') if e['kind']=='keyframe')
    stored = Image.open(logs.log_path('900').parent/keyframe['payload']['path'])
    assert stored.getpixel((199, 99)) == (27,17,7)


def test_real_cpu_board_reader_uses_native_bgr_regions_and_unchanged_frame_needs_no_full_rgb_copy(tmp_path):
    import numpy as np
    from pathlib import Path
    from tests.test_board_reader import _models
    from tft_capture.board_reader import BoardReader
    from tft_capture.frames import RegionFrame
    pixels = np.asarray(Image.open(Path(__file__).resolve().parents[2]/'probe/screenshots/2026-10-04/02-shop-with-wisp-2-3.jpg').convert('RGB'))[:, :, ::-1].copy()
    reader = BoardReader(_models(), set_number=18, unit_ids={'Karma': 'karma'})
    logs = SessionStore(tmp_path/'app', tmp_path/'config', live_installed=True)
    logs.start_game('900')
    pipeline = CapturePipeline('900', ocr=OCRFrames({'scouted': [TextLine('Owner Level 4')]}),
        visual_reader=reader, own_player_name='Owner', sink=logs)
    first = pipeline.tick(RegionFrame(pixels), timestamp=NOW)
    ninth = [row for row in first['fields']['board_observations']['value'] if row['zone']=='bench' and row['position']==8]
    assert [row['unit_id'] for row in ninth] == ['karma']
    repeated = pipeline.tick(RegionFrame(pixels), timestamp=NOW+timedelta(seconds=1))
    assert repeated['capture_copy']['full_rgb_bytes'] == 0
    assert repeated['fields']['board_observations']['read_at'] == repeated['captured_at']
    assert [e['kind'] for e in logs.read_events('900')].count('board_read') == 1


def test_round_wisp_count_and_board_settled_clock_require_positive_baselines_and_reset_after_gaps(tmp_path):
    slots = {'board_occupied': [], 'board_empty': list(range(28)), 'bench_occupied': [], 'bench_empty': list(range(9))}
    visual = VisualFrames({'board_observations': [], 'slot_inventory': slots, 'trait_panel_empty': True}, complete=True)
    pipeline, logs, _ = capture(tmp_path, {'scouted': [TextLine('Owner Level 1')],
        'unit_count': [TextLine('0/1')], 'stage': [TextLine('1-1')]}, visual=visual, extra=('board',))
    first = pipeline.tick(WHITE, timestamp=NOW)
    assert first['fields']['board_settled_since']['value'] == NOW.isoformat()
    assert first['fields']['wisp_purchase_count_complete']['value'] is False
    same = pipeline.tick(WHITE, timestamp=NOW+timedelta(seconds=1))
    assert same['fields']['board_settled_since']['value'] == NOW.isoformat()
    visual.values['round_start'] = True
    positive = pipeline.tick(BLACK, timestamp=NOW+timedelta(seconds=1.25))
    assert positive['fields']['wisp_purchases_this_round']['value'] == 0
    assert positive['fields']['wisp_purchase_count_complete']['value'] is True
    pipeline.tick(None, timestamp=NOW+timedelta(seconds=1.5))
    resumed = pipeline.tick(WHITE, timestamp=NOW+timedelta(seconds=1.75))
    assert resumed['fields']['board_settled_since']['value'] == resumed['captured_at']
    assert resumed['fields']['wisp_purchase_count_complete']['value'] is False
    assert [e['kind'] for e in logs.read_events('900')].count('round_tracking_start') == 1


def test_remaining_effects_require_explicit_observed_counters_and_complete_panel_count(tmp_path):
    from tft_data.models import DataSnapshot, Entity
    data = DataSnapshot('effects-pin', '16.20', 18, {}, {}, entities={
        'maxbuild': Entity('maxbuild', 'augment', 'Max Build'),
        'forest': Entity('forest', 'wisp', 'Forest Twins')})
    logs = SessionStore(tmp_path/'app', tmp_path/'config', live_installed=True)
    logs.start_game('900')
    ocr = OCRFrames({'effects': [TextLine('Remaining effects: 2'), TextLine('Max Build: 3 rolls remaining'),
        TextLine('Forest Twins: 2 rounds remaining')]})
    pipeline = CapturePipeline.from_data('900', data=data, ocr=ocr, sink=logs, regions={'effects': (0,0,1,1)})
    first = pipeline.tick(WHITE, timestamp=NOW)
    assert first['fields']['remaining_effects']['value'] == [
        {'effect_id': 'maxbuild', 'source_kind': 'augment', 'remaining_rolls': 3},
        {'effect_id': 'forest', 'source_kind': 'wisp', 'remaining_rounds': 2}]
    assert first['fields']['remaining_effects_complete']['value'] is True
    ocr.values['effects'] = [TextLine('Gain 10 free Shop rerolls'), TextLine('Remaining effects: 2'),
        TextLine('Max Build: 2 rolls remaining')]
    failed = pipeline.tick(BLACK, timestamp=NOW+timedelta(seconds=3))
    assert failed['fields']['remaining_effects_complete']['value'] is False
    assert failed['fields']['remaining_effects']['read_at'] == NOW.isoformat()
    ocr.values['effects'] = [TextLine('Remaining effects: 0')]
    empty = pipeline.tick(WHITE, timestamp=NOW+timedelta(seconds=4))
    assert empty['fields']['remaining_effects']['value'] == []
    assert empty['fields']['remaining_effects_complete']['value'] is True


def test_level_transition_logs_confirmed_values_but_never_attributes_gold_drop_to_xp_buy(tmp_path):
    pipeline, logs, ocr = capture(tmp_path, {'level': [TextLine('6')], 'xp': [TextLine('28/32')],
        'gold': [TextLine('30')]})
    pipeline.tick(WHITE, timestamp=NOW)
    ocr.values.update(level=[TextLine('7')], xp=[TextLine('0/50')], gold=[TextLine('26')])
    pipeline.tick(BLACK, timestamp=NOW+timedelta(seconds=.25))
    events = logs.read_events('900')
    transitions = [e for e in events if e['kind'] == 'level_up']
    assert len(transitions) == 1
    assert transitions[0]['payload']['before'] == {'level': 6, 'xp': 28, 'xp_to_level': 32}
    assert transitions[0]['payload']['after'] == {'level': 7, 'xp': 0, 'xp_to_level': 50}
    assert transitions[0]['payload']['before_read_at'] == NOW.isoformat()
    assert transitions[0]['payload']['after_read_at'] == (NOW+timedelta(seconds=.25)).isoformat()
    assert not any(e['kind'] == 'xp_purchase' for e in events)
    pipeline.tick(None, timestamp=NOW+timedelta(seconds=.5))
    ocr.values.update(level=[TextLine('8')], xp=[TextLine('0/70')])
    pipeline.tick(WHITE, timestamp=NOW+timedelta(seconds=.75))
    assert len([e for e in logs.read_events('900') if e['kind'] == 'level_up']) == 1


def test_failed_video_encoder_still_closes_capture_and_records_visible_failure(tmp_path):
    import pytest
    from tft_capture.media import SegmentRecorder
    pipeline, logs, _ = capture(tmp_path, {'gold': [TextLine('10')]})
    pipeline.video = SegmentRecorder(logs, executable=str(tmp_path/'missing-ffmpeg'))
    logs.set_media_mode('full_video')
    pipeline.tick(WHITE, timestamp=NOW)
    with pytest.raises(RuntimeError, match='Video encoding failed'):
        pipeline.close(timestamp=NOW+timedelta(seconds=.25))
    events = logs.read_events('900')
    assert any(e['kind'] == 'media_status' and e['payload']['state'] == 'unavailable' for e in events)
    assert events[-1]['kind'] == 'capture_closed'
    pipeline.close(timestamp=NOW+timedelta(seconds=.5))
    assert [e['kind'] for e in logs.read_events('900')].count('capture_closed') == 1
    with pytest.raises(ValueError, match='closed'):
        pipeline.tick(WHITE, timestamp=NOW+timedelta(seconds=1))


def test_resumed_capture_rejects_refreshed_data_instead_of_changing_original_game_pin(tmp_path):
    import pytest
    from tft_data.models import DataSnapshot
    logs = SessionStore(tmp_path/'app', tmp_path/'config', live_installed=True)
    logs.start_game('900', data_snapshot_id='original')
    with pytest.raises(ValueError, match='original.*data snapshot'):
        CapturePipeline.from_data('900', data=DataSnapshot('refreshed', '16.21', 18, {}, {}),
            ocr=OCRFrames({}), sink=logs, tracking_events=logs.read_events('900'))
    first = CapturePipeline.from_data('900', data=DataSnapshot('original', '16.20', 18, {}, {}),
        ocr=OCRFrames({'gold': [TextLine('28')]}), sink=logs, regions={'gold': (0,0,1,1)})
    first.tick(WHITE, timestamp=NOW)
    with pytest.raises(ValueError, match='original.*data snapshot'):
        CapturePipeline.from_data('900', data=DataSnapshot('refreshed', '16.21', 18, {}, {}),
            ocr=OCRFrames({}), sink=logs, tracking_events=logs.read_events('900'))
    resumed = CapturePipeline.from_data('900', data=DataSnapshot('original', '16.20', 18, {}, {}),
        ocr=OCRFrames({}), sink=logs, tracking_events=logs.read_events('900'))
    unavailable = resumed.tick(None, timestamp=NOW+timedelta(seconds=3))
    assert unavailable['data_snapshot_id'] == 'original'
    assert unavailable['fields']['gold']['read_at'] == NOW.isoformat()


def test_capture_cli_rejects_changed_model_cache_before_creating_game_log(tmp_path, capsys):
    import json
    from tft_core.capture_cli import main
    image = tmp_path/'frame.png'
    WHITE.save(image)
    profile = tmp_path/'profile.json'
    profile.write_text(json.dumps({'version': 1, 'regions': {'gold': [0,0,1,1]}}))
    names = tmp_path/'names.json'
    names.write_text(json.dumps({'units': {'karma': 'Karma'}}))
    pointer = tmp_path/'pointer.json'
    pointer.write_text(json.dumps({'version': 'accepted', 'files': {'unit_classifier.json': '0'*64}}))
    bundle = tmp_path/'cache/accepted'
    bundle.mkdir(parents=True)
    (bundle/'unit_classifier.json').write_text('{"labels": ["Karma"], "set": 18}')
    assert main(['inspect', '--profile', str(profile), '--images', str(image), '--game-id', '900',
        '--log-root', str(tmp_path/'logs'), '--models', str(tmp_path/'cache'), '--model-pointer', str(pointer),
        '--set-number', '18', '--names', str(names)], ocr=OCRFrames({})) == 2
    assert 'corrupt' in json.loads(capsys.readouterr().out)['error']
    assert not (tmp_path/'logs/games/900/events.jsonl').exists()


def test_long_unobserved_shop_interval_cannot_confirm_purchase_or_keep_wisp_counter(tmp_path):
    rows = [TextLine('Shen', box=(i*.2+.01,.82,i*.2+.13,.95)) for i in range(5)] + [TextLine('2', box=(i*.2+.16,.82,i*.2+.19,.95)) for i in range(5)]
    visual = VisualFrames({'round_start': True})
    pipeline, logs, ocr = capture(tmp_path, {'stage': [TextLine('2-1')], 'gold': [TextLine('20')], 'shop': rows},
        visual=visual, catalog=NameCatalog({'units': {'shen': 'Shen'}}))
    pipeline.tick(WHITE, timestamp=NOW)
    visual.values = {'shop_empty_slots': [0]}
    ocr.values.update(shop=[line for line in rows if line.box[0] >= .2], gold=[TextLine('18')])
    after = pipeline.tick(BLACK, timestamp=NOW+timedelta(seconds=10))
    events = logs.read_events('900')
    assert not any(e['kind'] == 'purchase' for e in events)
    assert any(e['kind'] == 'tracking_ambiguity' and 'interval' in e['payload']['reason'] for e in events)
    assert after['fields']['wisp_purchase_count_complete']['value'] is False


def test_carousel_acquisition_does_not_disappear_behind_a_same_frame_empty_board_certificate(tmp_path):
    slots = {'board_occupied': [], 'board_empty': list(range(28)), 'bench_occupied': [], 'bench_empty': list(range(9))}
    visual = VisualFrames({'board_observations': [], 'slot_inventory': slots, 'trait_panel_empty': True,
        'carousel': [{'slot': 0, 'unit_id': 'shen', 'item_id': 'cape'}], 'carousel_complete': True}, complete=True)
    pipeline, logs, _ = capture(tmp_path, {'scouted': [TextLine('Owner Level 1')],
        'unit_count': [TextLine('0/1')], 'stage': [TextLine('1-4')]}, visual=visual, extra=('board','carousel'))
    pipeline.tick(WHITE, timestamp=NOW)
    visual.values['confirmed_pick'] = {'kind': 'carousel', 'slot': 0}
    picked = pipeline.tick(BLACK, timestamp=NOW+timedelta(seconds=.25))
    assert picked['fields']['inventory_complete']['value'] is False
    events = logs.read_events('900')
    payload = next(e['payload'] for e in events if e['kind'] == 'carousel_pick')
    assert payload['ownership_included'] is False
    resumed = CapturePipeline('900', sink=logs, ocr=OCRFrames({'scouted': [TextLine('Owner Level 1')]}),
        own_player_name='Owner', visual_reader=VisualFrames({'board_observations': []}),
        regions={'scouted': (0,0,1,1), 'board': (0,0,1,1)}, tracking_events=events)
    observed = resumed.tick(WHITE, timestamp=NOW+timedelta(seconds=.5))
    assert observed['fields']['tracked_units']['value'][0]['unit_id'] == 'shen'
    assert observed['fields']['tracked_units']['value'][0]['copies'] == 1
    assert observed['fields']['tracked_units']['value'][0]['stars'] is None


def test_positive_pick_notification_and_new_held_hud_do_not_double_count_same_augment(tmp_path):
    rows = [TextLine(name, box=(i/3+.01,.4,(i+1)/3-.01,.5)) for i, name in enumerate(['First Choice','Second Choice','Third Choice'])]
    visual = VisualFrames({'augment_tier':'gold','augment_rerolls': {'0':True,'1':True,'2':True},
        'held_augments': [], 'held_augments_complete': True})
    pipeline, logs, _ = capture(tmp_path, {'scouted':[TextLine('Owner Level 4')], 'stage':[TextLine('2-1')], 'cards': rows},
        visual=visual, catalog=NameCatalog({'augments': {'a':'First Choice','b':'Second Choice','c':'Third Choice'}}))
    pipeline.tick(WHITE, timestamp=NOW)
    visual.values.update(held_augments=['b'], confirmed_pick={'kind':'augment','slot':1})
    after = pipeline.tick(BLACK, timestamp=NOW+timedelta(seconds=.25))
    assert after['fields']['held_augments']['value'] == ['b']
    assert [e['kind'] for e in logs.read_events('900')].count('augment_pick') == 1
