"""Calibrated visual evidence for HUD signals and choice/inventory icon slots.

Profiles describe geometry and reference artwork, never manually entered game
state. A failed template match omits the value. Every inventory slot must match
an item or a calibrated empty template before an inventory is called complete.
"""
from dataclasses import dataclass
import math

from tft_capture.reader_assets import TemplateBank
from tft_capture.ocr import NameCatalog
from tft_capture.vision import VisionRead


def crop_box(image, rectangle, box):
    if len(box) != 4 or not all(math.isfinite(value) for value in box):
        raise ValueError('Visual calibration needs four finite coordinates')
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError('Visual calibration rectangle must stay within its region')
    left, top, right, bottom = rectangle
    return image.crop((round(left + x0*(right-left)), round(top + y0*(bottom-top)),
                       round(left + x1*(right-left)), round(top + y1*(bottom-top))))


@dataclass(frozen=True)
class Signal:
    region: str
    box: tuple
    field: str
    templates: dict
    index: int | None = None


class SurfaceReader:
    source = 'calibrated-visual-surfaces'

    def __init__(self, *, board_reader=None, signals=(), items=None, item_slots=(), item_categories=None, item_offer_slots=(), carousel_classifier=None, unit_ids=None, carousel_slots=(), identity_min=.55, unit_slots=(), slot_templates=None, augment_icons=None, held_augment_slots=()):
        self.board_reader = board_reader
        self.augment_icons, self.held_augment_slots = augment_icons, tuple(held_augment_slots)
        self.signals = [(signal, TemplateBank(signal.templates)) for signal in signals]
        self.items, self.item_slots = items, tuple(item_slots)
        self.item_offer_slots = tuple(item_offer_slots)
        self.carousel_classifier, self.carousel_slots = carousel_classifier, tuple(carousel_slots)
        self.unit_ids = {NameCatalog.normalize(label): identity for label, identity in (unit_ids or {}).items()}
        self.identity_min = identity_min
        self.unit_slots = tuple(unit_slots)
        self.slot_templates = TemplateBank(slot_templates) if slot_templates else None
        self.observed_regions = {'board', 'bench', 'item_bench', 'cards', 'carousel', 'shop', 'held_augments'} | {signal.region for signal in signals}
        self.item_categories = item_categories or {}
        if board_reader:
            self.identity_min = board_reader.identity_min
            self.model_version = board_reader.model_version
            self.label_map = board_reader.label_map

    def read(self, image, *, regions, own_view):
        import numpy as np

        fields, scores, provenance = {}, [], {}
        complete = False
        if self.board_reader and own_view is True and 'board' in regions:
            board = self.board_reader.read(image, regions=regions, own_view=own_view)
            fields.update(board.fields)
            provenance.update({name: board.provenance.get(name, {'source': board.source, 'confidence': board.confidence}) for name in board.fields})
            if board.fields:
                scores.append(board.confidence)
            complete = board.inventory_complete
        for signal, bank in self.signals:
            if signal.region not in regions:
                continue
            if signal.field not in {'phase', 'augment_tier', 'augment_rerolls', 'choice_kind', 'trait_panel_empty', 'confirmed_pick', 'grant_receipt', 'round_start'}:
                raise ValueError('Unsupported calibrated signal field')
            pixels = np.asarray(crop_box(image, regions[signal.region], signal.box).convert('RGB'))[:, :, ::-1].copy()
            match = bank.match(pixels)
            if match is None:
                continue
            label, raw_score = match
            score = min(1., max(0., raw_score))
            if signal.field == 'augment_rerolls':
                if signal.index not in (0, 1, 2) or label not in {'true', 'false'}:
                    raise ValueError('A reroll signal needs its slot and positive true/false artwork')
                fields.setdefault(signal.field, {})[str(signal.index)] = label == 'true'
            else:
                if signal.field == 'round_start':
                    if label not in {'true', 'false'}:
                        raise ValueError('Round start needs positive present/absent artwork')
                    fields[signal.field] = label == 'true'
                elif signal.field == 'grant_receipt':
                    if label == 'none':
                        fields[signal.field] = None
                    else:
                        parts = label.split(':')
                        if len(parts) != 3 or parts[0] not in {'wisp', 'encounter', 'duplicator', 'carousel'} or not parts[1] or not parts[2].isdigit() or int(parts[2]) <= 0:
                            raise ValueError('Grant artwork must identify the source, unit and positive copy count')
                        fields[signal.field] = {'source': parts[0], 'unit_id': parts[1], 'copies': int(parts[2])}
                elif signal.field == 'confirmed_pick':
                    if label == 'none':
                        fields[signal.field] = None
                    else:
                        parts = label.split(':')
                        if len(parts) != 2 or parts[0] not in {'augment', 'item', 'carousel'} or not parts[1].isdigit():
                            raise ValueError('Pick artwork must identify the confirmed choice kind and slot')
                        fields[signal.field] = {'kind': parts[0], 'slot': int(parts[1])}
                elif signal.field == 'trait_panel_empty':
                    if own_view is True and label == 'true':
                        fields[signal.field] = True
                else:
                    fields[signal.field] = label
                if signal.field == 'phase':
                    fields['planning_phase'] = label in {'planning', 'roll_down'}
            if signal.field in fields:
                provenance[signal.field] = {'source': self.source+':'+signal.field, 'confidence': score}
            if signal.field == 'phase':
                provenance['planning_phase'] = {'source': self.source+':phase', 'confidence': score}
            scores.append(score)
        if own_view is True and self.augment_icons and self.held_augment_slots and 'held_augments' in regions:
            if len(self.held_augment_slots) != 3:
                raise ValueError('Held augments require all three calibrated slots')
            matches = [self.augment_icons.match(np.asarray(crop_box(image, regions['held_augments'], box).convert('RGB'))[:, :, ::-1].copy())
                for box in self.held_augment_slots]
            fields['held_augments_complete'] = all(match is not None for match in matches)
            scores.extend(match[1] for match in matches if match is not None)
            if fields['held_augments_complete']:
                fields['held_augments'] = [match[0] for match in matches if match[0] is not None]
        if own_view is True and self.unit_slots and self.slot_templates:
            slots = {'board_occupied': [], 'board_empty': [], 'bench_occupied': [], 'bench_empty': []}
            all_read = True
            for slot in self.unit_slots:
                zone = slot['zone']
                if zone not in {'board', 'bench'}:
                    raise ValueError('Unit slot zone must be board or bench')
                if zone not in regions:
                    all_read = False
                    continue
                pixels = np.asarray(crop_box(image, regions[zone], slot['box']).convert('RGB'))[:, :, ::-1].copy()
                matched = self.slot_templates.match(pixels)
                if matched is None or matched[0] not in {None, 'occupied'}:
                    all_read = False
                    continue
                slots[zone+('_empty' if matched[0] is None else '_occupied')].append(slot['position'])
                scores.append(matched[1])
            fields['slot_inventory'] = slots
            if 'board_observations' not in fields and not slots['board_occupied'] and not slots['bench_occupied'] and all_read:
                fields['board_observations'] = []
            complete = all_read and all(len(slots[zone+'_occupied']) + len(slots[zone+'_empty']) == count
                and set(slots[zone+'_occupied'] + slots[zone+'_empty']) == set(range(count)) for zone, count in (('board', 28), ('bench', 9)))
        if self.items is not None and self.item_offer_slots and fields.get('choice_kind') == 'item' and 'cards' in regions:
            matches = [self.items.match(np.asarray(crop_box(image, regions['cards'], slot).convert('RGB'))[:, :, ::-1].copy())
                       for slot in self.item_offer_slots]
            valid = all(match is not None and match[0] is not None for match in matches)
            fields['item_offers_complete'] = valid
            scores.extend(match[1] for match in matches if match is not None)
            if valid:
                fields['item_offers'] = [{'slot': slot, 'item_id': match[0]} for slot, match in enumerate(matches)]
        if fields.get('phase') == 'carousel' and 'carousel' in regions and self.carousel_slots and self.carousel_classifier and self.items:
            crops = [np.asarray(crop_box(image, regions['carousel'], slot['unit']).convert('RGB'))[:, :, ::-1].copy()
                     for slot in self.carousel_slots]
            predictions = self.carousel_classifier.predict(crops)
            matches = [self.items.match(np.asarray(crop_box(image, regions['carousel'], slot['item']).convert('RGB'))[:, :, ::-1].copy())
                       for slot in self.carousel_slots]
            options = []
            for index, ((label, confidence), item) in enumerate(zip(predictions, matches)):
                identity = self.unit_ids.get(NameCatalog.normalize(label))
                if identity and confidence >= self.identity_min and item is not None and item[0] is not None:
                    options.append({'slot': index, 'unit_id': identity, 'item_id': item[0]})
                    scores.extend((confidence, item[1]))
            valid = len(options) == len(self.carousel_slots)
            fields['carousel_observations'] = options
            fields['carousel_complete'] = valid
            if valid:
                fields['carousel'] = options
        if self.items is not None and self.item_slots and own_view is True and 'item_bench' in regions:
            matches = [self.items.match(np.asarray(crop_box(image, regions['item_bench'], slot).convert('RGB'))[:, :, ::-1].copy())
                       for slot in self.item_slots]
            known = [match[0] for match in matches if match is not None and match[0] is not None]
            inventory_complete = all(match is not None for match in matches)
            fields['item_bench_observations'] = {'items': known, 'complete': inventory_complete}
            fields['item_inventory_complete'] = inventory_complete
            scores.extend(match[1] for match in matches if match is not None)
            if inventory_complete:
                fields['item_bench'] = known
                if all(identity in self.item_categories for identity in known):
                    fields['components'] = [identity for identity in known if self.item_categories[identity] == 'component']
                    fields['completed_items'] = [identity for identity in known if self.item_categories[identity] == 'finished']
                    fields['tools'] = [identity for identity in known if self.item_categories[identity] in {'remover', 'reforger', 'tool'}]
                    fields['removers'] = [identity for identity in known if self.item_categories[identity] == 'remover']
                    fields['reforgers'] = [identity for identity in known if self.item_categories[identity] == 'reforger']
        return VisionRead(fields, self.source, min(1., min(scores, default=0)), complete, provenance)
