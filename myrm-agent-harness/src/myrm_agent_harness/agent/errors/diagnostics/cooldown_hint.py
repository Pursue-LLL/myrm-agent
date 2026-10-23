"""Cooldown hint rendering for rate-limit diagnostics.

[INPUT]
- diagnostics.i18n::get_locale_manager (POS: bundled and override locale bundles)
- locale JSON keys `cooldown_hint_template` / `cooldown_hint_second_one` / `cooldown_hint_second_other`

[OUTPUT]
- format_cooldown_hint(): the sentence to append to a rate-limit message, or "" when there is no wait

[POS]
Keeps the unit-and-template lookup out of the diagnostic engine: the engine states that a wait
exists, this module states how the wait reads in the caller's language.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_FALLBACK_UNIT = "{n} seconds"
_FALLBACK_TEMPLATE = " Retry after {duration}."


def _duration_seconds(translations: dict[str, str], seconds: int) -> str:
    """Render ``seconds`` with the locale's own word for it.

    Seconds stay seconds: the provider reports the wait in seconds, so restating 120 as "2 minutes"
    would replace a number the caller already holds with a derived one.
    """
    plural = "one" if seconds == 1 else "other"
    template = translations.get(f"second_{plural}") or translations.get("second_other") or _FALLBACK_UNIT
    return template.format(n=seconds)


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
        translations = manager._translations.get(locale, {}).get("_cooldown_hint", {})
        if not translations:
            translations = manager._translations.get("en", {}).get("_cooldown_hint", {})

        template = translations.get("template", "")
        if not template:
            return _FALLBACK_TEMPLATE.format(duration=_duration_seconds({}, cooldown_seconds))
        return template.format(duration=_duration_seconds(translations, cooldown_seconds))
    except Exception:
        logger.debug("cooldown hint could not be rendered", exc_info=True)
        return _FALLBACK_TEMPLATE.format(duration=_duration_seconds({}, cooldown_seconds))


__all__ = ["format_cooldown_hint"]
