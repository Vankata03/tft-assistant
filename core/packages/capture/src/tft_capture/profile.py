"""Load reviewed geometry and hash-checked artwork before starting capture.

Profiles contain calibration and recognition assets, never live game-state
values. A profile's coverage still requires target-HUD qualification; matching
all configured choice slots does not prove an uncalibrated layout is exhaustive.
"""
from dataclasses import dataclass
from copy import deepcopy
import math
import hashlib
import json
from pathlib import Path

from PIL import Image

from tft_capture.surfaces import SurfaceReader, Signal, crop_box
from tft_capture.reader_assets import TemplateBank


@dataclass(frozen=True)
class CaptureProfile:
    regions: dict
    reader: SurfaceReader
    sha256: str
    _surface: object = None

    @property
    def surface(self):
        return deepcopy(self._surface)


def load_profile(path, *, board_reader=None, carousel_classifier=None, unit_ids=None):
    import cv2

    path = Path(path)
    content = path.read_bytes()
    raw = json.loads(content)
    allowed = {'version', 'regions', 'signals', 'item_templates', 'augment_templates', 'slot_templates',
        'item_slots', 'item_offer_slots', 'carousel_slots', 'unit_slots', 'held_augment_slots', 'item_categories',
        'anchors', 'anchor_calibration'}
    if raw.get('version') != 1 or set(raw)-allowed:
        raise ValueError('Unsupported capture profile fields/version')
    if not raw.get('regions'):
        raise ValueError('Capture profile requires calibrated regions')
    for box in raw['regions'].values():
        crop_box(Image.new('RGB', (1, 1)), (0, 0, 1, 1), box)
    surface = None
    if raw.get('anchors'):
        calibration = raw.get('anchor_calibration')
        size = calibration.get('client_size') if isinstance(calibration, dict) else None
        scale = calibration.get('ui_scale') if isinstance(calibration, dict) else None
        if (not isinstance(size, list) or len(size) != 2 or any(type(v) is not int or not 0 < v <= 20000 for v in size)
            or type(scale) not in (int, float) or not math.isfinite(scale) or not .5 <= scale <= 1.5
            or set(calibration) != {'client_size', 'ui_scale'}):
            raise ValueError('Surface anchors require explicit reviewed client size and UI scale')
        identities = set()
        if not isinstance(raw['anchors'], list) or len(raw['anchors']) > 128:
            raise ValueError('Invalid surface anchor count')
        for anchor in raw['anchors']:
            if (not isinstance(anchor, dict) or set(anchor) != {'kind', 'index', 'x', 'y', 'width', 'height'}
                or anchor['kind'] not in {'shop', 'level', 'par', 'augment', 'carousel', 'wisp', 'xp', 'player', 'hex', 'line', 'review'}
                or type(anchor['index']) is not int or not 0 <= anchor['index'] <= (27 if anchor['kind'] == 'hex' else 20)
                or any(type(anchor[k]) not in (int, float) or not math.isfinite(anchor[k]) for k in ('x', 'y', 'width', 'height'))
                or min(anchor['x'], anchor['y']) < 0 or min(anchor['width'], anchor['height']) <= 0
                or anchor['x'] + anchor['width'] > 1 or anchor['y'] + anchor['height'] > 1):
                raise ValueError('Invalid calibrated surface anchor')
            key = (anchor['kind'], anchor['index'])
            if key in identities:
                raise ValueError('Ambiguous duplicate surface anchor')
            identities.add(key)
        surface = {'anchors': raw['anchors'], 'calibration': calibration,
                   'profile_sha256': hashlib.sha256(content).hexdigest()}

    def asset(entry):
        filename = Path(entry['file'])
        if filename.is_absolute() or '..' in filename.parts:
            raise ValueError('Recognition assets must stay inside the profile directory')
        image_path = path.parent / filename
        if hashlib.sha256(image_path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Capture artwork integrity failed')
        pixels = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if pixels is None:
            raise ValueError('Capture artwork cannot be decoded')
        return pixels

    def bank(name):
        entries = raw.get(name)
        return TemplateBank({identity: asset(entry) for identity, entry in entries.items()}) if entries else None

    signals = []
    supported = {'phase', 'augment_tier', 'augment_rerolls', 'choice_kind', 'trait_panel_empty', 'confirmed_pick', 'grant_receipt', 'round_start'}
    for row in raw.get('signals', []):
        if row['field'] not in supported or row['region'] not in raw['regions']:
            raise ValueError('Capture signal needs a supported field and calibrated region')
        crop_box(Image.new('RGB', (1, 1)), (0, 0, 1, 1), row['box'])
        signals.append(Signal(row['region'], tuple(row['box']), row['field'],
            {label: asset(entry) for label, entry in row['templates'].items()}, row.get('index')))
    slot_bank = bank('slot_templates')
    reader = SurfaceReader(board_reader=board_reader, carousel_classifier=carousel_classifier, unit_ids=unit_ids,
        signals=signals, items=bank('item_templates'), augment_icons=bank('augment_templates'),
        slot_templates=slot_bank.templates if slot_bank else None,
        **{key: raw[key] for key in ('item_slots', 'item_offer_slots', 'carousel_slots', 'unit_slots',
            'held_augment_slots', 'item_categories') if key in raw})
    return CaptureProfile(raw['regions'], reader, hashlib.sha256(content).hexdigest(), surface)
