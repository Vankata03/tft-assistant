"""Derived threat tags retain matched phrases and trait breakpoints for review."""

import html
import re
from dataclasses import replace

from .models import TaggedValue


def plain_text(text):
    # A missing source description matches no threat phrase.
    return re.sub(r"<[^>]*>", " ", html.unescape(text or "")).casefold()


def derive_threats(entities, keywords):
    result = {}
    for id, entity in entities.items():
        text = plain_text(entity.text)
        matched = {
            tag: tuple(phrase for phrase in phrases if phrase.casefold() in text)
            for tag, phrases in keywords.items()
        }
        matched = {tag: phrases for tag, phrases in matched.items() if phrases}
        result[id] = replace(
            entity,
            threat_tags=tuple(matched),
            values={**entity.values, "threat_matches": TaggedValue(matched, "cdragon")},
        )
    for id, trait in list(result.items()):
        if trait.kind != "trait":
            continue
        units = [
            unit
            for unit in result.values()
            if unit.kind == "unit" and id in unit.traits
        ]
        tags = set(trait.threat_tags)
        inherited = []
        for tag in keywords:
            count = sum(tag in unit.threat_tags for unit in units)
            if units and count > len(units) / 2:
                tags.add(tag)
                inherited.append(tag)
        breakpoints = trait.values.get("breakpoints")
        minimum = min(breakpoints.value) if breakpoints and breakpoints.value else None
        # Where Riot supplies an explicit higher threshold in the sentence, honor it.
        threshold = re.search(
            r"(?:at|with)\s+(\d+)\s+(?:units|stacks)", plain_text(trait.text)
        )
        if threshold and minimum is not None:
            minimum = max(minimum, int(threshold[1]))
        values = {
            **trait.values,
            "threat_majority": TaggedValue(tuple(inherited), "cdragon"),
        }
        if minimum is not None:
            values["threat_breakpoints"] = TaggedValue(
                {tag: minimum for tag in tags}, "cdragon"
            )
        result[id] = replace(trait, threat_tags=tuple(sorted(tags)), values=values)
    return result
