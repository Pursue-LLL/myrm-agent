"""Cooldown hint rendering for rate-limit diagnostics.

[INPUT]
- diagnostics.i18n::get_locale_manager (POS: bundled and override locale bundles)
- locale JSON keys `cooldown_hint_template` / `cooldown_hint_joiner` and the unit words `cooldown_hint_<second|minute|hour|day>_one` / `_other`

[OUTPUT]
- format_cooldown_hint(): the sentence to append to a rate-limit message, or "" when there is no wait

[POS]
Keeps the unit-and-template lookup out of the diagnostic engine: the engine states that a wait
exists, this module states how the wait reads in the caller's language.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

_FALLBACK_UNIT = "{n} seconds"
_FALLBACK_TEMPLATE = " Retry after {duration}."

_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 3600
_SECONDS_PER_DAY = 86400
_MINUTES_PER_HOUR = 60
_HOURS_PER_DAY = 24


def _units(seconds: int) -> list[tuple[str, int]]:
    """The units a wait of ``seconds`` is spelled in, largest first; a unit with nothing left is left out.

    Below an hour the wait stays in seconds, the unit the provider reports it in. From an hour up the two
    largest units place it on a clock (``6 hours 24 minutes``, ``7 days``) and the smaller one rounds up:
    a wait stated too short sends the retry in too early.
    """
    if seconds < _SECONDS_PER_HOUR:
        return [("second", seconds)]
    if seconds < _SECONDS_PER_DAY:
        hours, minutes = divmod(math.ceil(seconds / _SECONDS_PER_MINUTE), _MINUTES_PER_HOUR)
        return [(unit, n) for unit, n in (("hour", hours), ("minute", minutes)) if n]
    days, hours = divmod(math.ceil(seconds / _SECONDS_PER_HOUR), _HOURS_PER_DAY)
    return [(unit, n) for unit, n in (("day", days), ("hour", hours)) if n]


def _spell(translations: dict[str, str], units: list[tuple[str, int]]) -> str | None:
    """``units`` in the locale's own words, or None when the bundle lacks the word of one of them."""
    words: list[str] = []
    for unit, n in units:
        plural = "one" if n == 1 else "other"
        template = translations.get(f"{unit}_{plural}") or translations.get(f"{unit}_other")
        if not template:
            return None
        words.append(template.format(n=n))
    return translations.get("joiner", " ").join(words)


def _duration(translations: dict[str, str], seconds: int) -> str:
    """The wait in the locale's words; a bundle without the words of a long wait still states it in seconds."""
    return (
        _spell(translations, _units(seconds))
        or _spell(translations, [("second", seconds)])
        or _FALLBACK_UNIT.format(n=seconds)
    )


def format_cooldown_hint(cooldown_remaining_ms: int | None, locale: str) -> str:
    """The cooldown sentence for this locale, or "" when no wait is left."""
    if not cooldown_remaining_ms or cooldown_remaining_ms <= 0:
        return ""

    cooldown_seconds = int(cooldown_remaining_ms / 1000)
    if cooldown_seconds <= 0:
        return ""

    try:
        from myrm_agent_harness.agent.errors.diagnostics.i18n import get_locale_manager

        manager = get_locale_manager()
        bundle = manager._translations.get(locale, {}).get("_cooldown_hint", {})
        if not bundle:
            bundle = manager._translations.get("en", {}).get("_cooldown_hint", {})
        # The bundle type also admits step lists; only text entries are templates.
        translations = {key: text for key, text in bundle.items() if isinstance(text, str)}

        template = translations.get("template", "")
        if not template:
            return _FALLBACK_TEMPLATE.format(duration=_duration({}, cooldown_seconds))
        return template.format(duration=_duration(translations, cooldown_seconds))
    except Exception:
        logger.debug("cooldown hint could not be rendered", exc_info=True)
        return _FALLBACK_TEMPLATE.format(duration=_duration({}, cooldown_seconds))


__all__ = ["format_cooldown_hint"]
