"""UserConfig-backed locale provider for channel ingress.

[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs (POS: cached user config bundle)
- myrm_agent_harness.utils.locale::normalize_locale (POS: BCP-47 normalization)

[OUTPUT]
- UserConfigLocaleProvider: LocaleProvider implementation

[POS]
Business-layer adapter that resolves the GUI user's language preference
(personalSettings.locale) for channel slash command replies.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.utils.locale import normalize_locale

from app.channels.types import InboundMessage

logger = logging.getLogger(__name__)


class UserConfigLocaleProvider:
    """Resolve locale from personalSettings.locale in UserConfig."""

    async def resolve_locale(self, msg: InboundMessage) -> str:
        del msg  # Single-user server; locale is global per deployment instance.
        try:
            from app.core.channel_bridge.config_loader import load_user_config_entry

            personal = await load_user_config_entry("personalSettings") or {}
            locale_val = personal.get("locale")
            if locale_val:
                return normalize_locale(str(locale_val))
        except Exception as exc:
            logger.warning("Failed to resolve user locale from config: %s", exc)
        return normalize_locale(None)
