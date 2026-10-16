"""Production producer of the ``opponent_joint_support`` declaration.

A qualified public statistics provider exports whole-board frequencies per
round and level. Each counted board becomes one weighted hypothesis, so
correlations between units, forms, items and capacity are kept rather than
rebuilt from trait marginals. A (round, level) context below the board gate
is left out; the consumer then reports that context as unavailable.

The declaration binds the provider's patch, cohort and update time, which
``tft_review.sighting_forecast.sighting_law`` checks again before use. The
overlay adds the declaration to historical snapshots of the same patch for
offline evaluation without changing any stored snapshot.
"""
from collections.abc import Mapping
from dataclasses import replace

from tft_data import DataError, TaggedValue
from tft_data.config import STATISTICS_MIN_SAMPLES
from tft_data.models import plain
from tft_engine import Board
from tft_review.identity import digest


def build_joint_support(rows, data, *, provider, citation, min_boards=STATISTICS_MIN_SAMPLES):
    """Return (declaration, report) for ``data``'s patch from counted public boards."""
    if not isinstance(citation, str) or not citation.strip():
        raise DataError('Joint support requires a source citation')
    state = data.sources.get(provider)
    if (state is None or state.qualified is not True or state.kind != 'statistics'
            or state.patch != data.patch or not state.cohort
            or any(value is None for value in state.cohort.values())):
        raise DataError('Joint support requires a qualified current-patch statistics provider')
    contexts = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise DataError('Joint support rows must be tables')
        round_id, level, count = row.get('round_id'), row.get('level'), row.get('count')
        if not isinstance(round_id, str) or type(level) is not int or level < 1:
            raise DataError('Joint support rows need a round id and a positive level')
        if type(count) is not int or count < 1:
            raise DataError('Joint support boards need a positive integer count')
        try:
            board = Board.from_dict(plain(row['board']))
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise DataError(f'Invalid joint support board: {error}') from None
        unknown = sorted({unit.unit_id for unit in (*board.units, *board.bench)} - set(data.entities))
        if unknown or not board.units:
            raise DataError(f'Joint support board names unknown or no units: {unknown}')
        hypothesis = {'weight': count, 'board': board.to_dict()}
        for name in ('capacity', 'forms'):
            if row.get(name) is not None:
                hypothesis[name] = plain(row[name])
        contexts.setdefault((round_id, level), []).append(hypothesis)
    rounds, kept, thin = {}, {}, {}
    for (round_id, level), hypotheses in sorted(contexts.items()):
        boards = sum(hypothesis['weight'] for hypothesis in hypotheses)
        if boards < min_boards:
            thin[f'{round_id}/{level}'] = boards
            continue
        rounds.setdefault(round_id, {})[str(level)] = hypotheses
        kept[f'{round_id}/{level}'] = boards
    if not rounds:
        raise DataError('No joint support context passes the board gate')
    declaration = {'provider': provider, 'patch': data.patch, 'cohort': plain(state.cohort),
        'source_updated_at': state.updated_at.isoformat(), 'rounds': rounds}
    return TaggedValue(declaration, 'owner', citation), {'contexts': kept, 'thin_contexts': thin,
        'min_boards': min_boards, 'provider': provider}


class JointSupportOverlay:
    """Read historical snapshots with the declaration of their own patch added."""

    def __init__(self, historical_store, declarations):
        self.historical_store = historical_store
        self.declarations = dict(declarations)
        self.identity = digest({patch: {'value': plain(value.value), 'citation': value.citation}
            for patch, value in sorted(self.declarations.items())})

    def get(self, snapshot_id):
        original = self.historical_store.get(snapshot_id)
        support = self.declarations.get(original.patch)
        if support is None:
            return original
        return replace(original, static=dict(original.static) | {'opponent_joint_support': support})
