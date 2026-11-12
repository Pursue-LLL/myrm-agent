"""Closure of the numbers and identifiers a consolidation result may state.

[INPUT]
- strategies.exact_fact::{ExactFactClassifier, identifier_key} (POS: deterministic extractor of high-entropy identifiers and their comparison form)
- strategies.named_entity_guard::NamedEntityGuard (POS: deterministic extractor of ports, addresses, URLs, variables and paths)

[OUTPUT]
- Facts: the numbers and identifiers a text states, with the comparison that finds what a text states beyond another
- facts_of: Extract the facts of one or more texts

[POS]
A consolidation result may merge, shorten and re-date what the model was shown, but it may not state a number or an
identifier that none of those texts states. The entity guard catches a technical entity that is lost; this closure
catches one that is invented or changed (a rent of 4500 becoming 5400, a port, an address or a version that was never
written). A date or a time of day is no claim, since the model resolves relative dates against today; the year that a
date in the sources writes still counts as stated. Both checks are deterministic and read no store.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from myrm_agent_harness.toolkits.memory.strategies.exact_fact import ExactFactClassifier, identifier_key
from myrm_agent_harness.toolkits.memory.strategies.named_entity_guard import NamedEntityGuard

# A date or a time of day is derived from "today" and the wording of the source, so its digits are never a claim.
# A month name is only a month when spelled out whole or in the usual abbreviation ("Marketing 2024" is no date),
# and the year after it is a plausible one ("Mar 5000" is a quantity).
_MONTH = (
    r"(?<![A-Za-z])(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)(?![A-Za-z])\.?"
)
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_PLAUSIBLE_YEAR = r"(?:19|20)\d{2}(?!\d)"
_DATE = re.compile(
    r"(?<!\d)(?:"
    r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?"
    r"|\d{4}年(?:\d{1,2}月)?"
    r"|\d{1,2}月\d{1,2}[日号]"
    r"|\d{1,2}:\d{2}(?::\d{2})?(?!\d)"
    rf"|{_MONTH}\s+(?:{_DAY},?\s+)?{_PLAUSIBLE_YEAR}"
    rf"|{_DAY}\s+(?:of\s+)?{_MONTH},?\s+{_PLAUSIBLE_YEAR}"
    r")"
)
_YEAR = re.compile(r"(?<!\d)\d{4}(?!\d)")

# A number is not read out of an identifier or a dotted run ("v2.4.1", "10.0.0.5", "sha1": those are the identifier
# extractors' business); a comma groups thousands only when exactly three digits follow it, so "1,2,3" stays
# three numbers.
_NUMBER = re.compile(r"(?<![A-Za-z0-9_.])((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?!\.\d)\s?(%|[kK](?![A-Za-z])|万|亿)?")
_SCALE: dict[str, Decimal] = {"k": Decimal(1000), "K": Decimal(1000), "万": Decimal(10_000), "亿": Decimal(100_000_000)}
_PERCENT = Decimal(100)
# Whole numbers below one hundred are counts, ordinals and days of the month, which a rewrite spells differently
# ("two dogs", "the 5th") without changing what is claimed.
_SMALL_WHOLE = Decimal(100)

_ENTITY_GUARD = NamedEntityGuard()


@dataclass(frozen=True, slots=True)
class Facts:
    """The numbers and identifiers a text states, in one comparable form each.

    A date is no claim, so its digits are not ``numbers``; its year is kept in ``dated_years`` because a result that
    shortens "2024-03-01" to "in 2024" states nothing new.
    """

    numbers: frozenset[Decimal] = frozenset()
    identifiers: frozenset[str] = frozenset()
    dated_years: frozenset[Decimal] = frozenset()

    @property
    def is_empty(self) -> bool:
        return not (self.numbers or self.identifiers)

    def beyond(self, reference: Facts) -> Facts:
        """What these facts state that ``reference`` does not."""
        return Facts(
            self.numbers - reference.numbers - reference.dated_years,
            self.identifiers - reference.identifiers,
        )


def _quantities(text: str) -> tuple[set[Decimal], set[Decimal]]:
    """The quantities in ``text`` and the years of its dates.

    A quantity is a canonical value: separators, ``k`` / ``万`` / ``亿`` and ``%`` folded in, dates and times left out.
    """
    folded = unicodedata.normalize("NFKC", text)
    years = {Decimal(year) for date in _DATE.findall(folded) for year in _YEAR.findall(date)}
    values: set[Decimal] = set()
    for match in _NUMBER.finditer(_DATE.sub(" ", folded)):
        value = Decimal(match.group(1).replace(",", ""))
        unit = match.group(2)
        if unit == "%":
            value /= _PERCENT
        elif unit:
            value *= _SCALE[unit]
        if value < _SMALL_WHOLE and value == value.to_integral_value():
            continue
        values.add(value.normalize())
    return values, years


def _identifiers(text: str) -> set[str]:
    found = {identifier_key(identifier) for identifier in ExactFactClassifier.extract_identifiers(text)}
    found.update(identifier_key(entity.value) for entity in _ENTITY_GUARD.extract_entities(text))
    return found


def facts_of(*texts: str) -> Facts:
    """The union of the facts of every text."""
    numbers: set[Decimal] = set()
    years: set[Decimal] = set()
    identifiers: set[str] = set()
    for text in texts:
        text_numbers, text_years = _quantities(text)
        numbers |= text_numbers
        years |= text_years
        identifiers |= _identifiers(text)
    return Facts(frozenset(numbers), frozenset(identifiers), frozenset(years))


__all__ = ["Facts", "facts_of"]
