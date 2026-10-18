"""Shared static trait-form helper, prepared once per evaluation scope."""
from tft_data.traits import unit_trait_variants as _source_variants
from .preparation import patch_calculation

__all__=['unit_trait_variants']


@patch_calculation
def _prepared_variants(unit_id,data):
    return _source_variants(unit_id,data)


def unit_trait_variants(unit_id,data):
    # Callers receive fresh dictionaries, exactly as from the source helper.
    return tuple(dict(variant) for variant in _prepared_variants(unit_id,data))
