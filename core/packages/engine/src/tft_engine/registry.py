"""Explicit deterministic decision hooks; callers can pass a different tuple for review."""
from dataclasses import dataclass, field
from typing import Callable, Mapping
from tft_data.models import freeze

@dataclass(frozen=True)
class FitTerm:
    delta: float
    reason: str
    numbers: Mapping = field(default_factory=dict)
    confidence: float = 1.0
    def __post_init__(self):
        object.__setattr__(self,'numbers',freeze(self.numbers))

@dataclass(frozen=True)
class DomainHook:
    name: str
    required_fields: tuple[str,...]
    fit: Callable | None = None
    advice: Callable | None = None
    fit_required_fields: tuple[str,...] = ()
    advice_phases: tuple[str,...] = ('planning','roll_down')
    activation_field: str | None = None
    dependency_fields: tuple[str,...] = ()


def default_hooks():
    from .shop import advice as shop_advice
    from .items import fit as item_fit, advice as item_advice
    from .wisps import advice as wisp_advice, fit as wisp_fit
    from .augments import fit as augment_fit, advice as augment_advice
    from .carousel import advice as carousel_advice
    from .positioning import advice as positioning_advice
    ownership=('board','bench','inventory_complete')
    items=ownership+('item_bench','item_inventory_complete')
    choices=items+('gold','hp','level','xp','streak','lobby','lobby_complete')
    stochastic=('team_slot_budget','slot_count','shop','roll_down','held_augments','held_augments_complete','augment_tier','remaining_effects','remaining_effects_complete','comp_lock','pinned_line','include_unguided')
    return (DomainHook('shop',ownership+('shop','gold','level'),advice=shop_advice,activation_field='shop',dependency_fields=choices+stochastic),
        DomainHook('item',items,fit=item_fit,advice=item_advice,fit_required_fields=items,activation_field='item_bench',advice_phases=('planning','roll_down','augment'),dependency_fields=choices+stochastic+('item_offers','item_offers_complete','choice_kind')),
        DomainHook('wisp',choices+('wisp','wisp_complete','slot_count','wisp_purchases_this_round','wisp_purchase_count_complete'),fit=wisp_fit,advice=wisp_advice,activation_field='wisp',dependency_fields=stochastic),
        DomainHook('augment',('augments','augment_tier','augment_offers_complete'),fit=augment_fit,advice=augment_advice,advice_phases=('augment',),activation_field='augments',dependency_fields=choices+stochastic),
        DomainHook('carousel',choices+('carousel','carousel_complete'),advice=carousel_advice,advice_phases=('carousel',),activation_field='carousel',dependency_fields=stochastic),
        DomainHook('positioning',ownership+('level',),advice=positioning_advice,dependency_fields=('lobby','lobby_complete','board_settled_since','recent_opponents','recent_opponent_fights','recent_opponent_fights_complete','position_locks','held_augments','held_augments_complete','comp_lock')))
