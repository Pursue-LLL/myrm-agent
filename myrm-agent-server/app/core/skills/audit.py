"""Structured audit logging for skill lifecycle operations.

[INPUT]
- logging (stdlib)

[OUTPUT]
- audit_skill_action: INFO-level SKILL_AUDIT log lines for install/enable/disable etc.

[POS]
Server core audit sink for skill actions. API and discovery layers call this; no HTTP coupling.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def audit_skill_action(
    action: str,
    skill_id: str,
    *,
    source: str = "",
    scan_findings: int = 0,
) -> None:
    """Structured audit log for skill lifecycle operations."""
    logger.info(
        "SKILL_AUDIT action=%s user=sandbox skill=%s source=%s scan_findings=%d",
        action,
        skill_id,
        source,
        scan_findings,
    )
