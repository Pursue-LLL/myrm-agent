"""Safe PII action parsing for persisted privacy configuration.

[INPUT]
- myrm_agent_harness.agent.security.types::PIIAction (POS: PII action enum)

[OUTPUT]
- coerce_pii_action: parse a persisted action string into a PIIAction enum value

[POS]
Business-layer defensive parsing. Coerces persisted PII action strings so a
stale/foreign configuration cannot crash agent init or memory extraction.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.security.types import PIIAction

logger = logging.getLogger(__name__)


def coerce_pii_action(value: object | None, default: PIIAction) -> PIIAction:
    """Parse a persisted PII action string into a valid enum value.

    Falls back to *default* for missing or invalid values so a stale/foreign
    configuration cannot crash agent initialization or memory extraction.
    """
    if value is None:
        return default
    try:
        return PIIAction(str(value))
    except ValueError:
        logger.warning("Invalid PII action %r, falling back to %s", value, default.value)
        return default


__all__ = ["coerce_pii_action"]
