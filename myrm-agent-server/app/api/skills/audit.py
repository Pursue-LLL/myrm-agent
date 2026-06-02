from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

def _audit_skill_action(
    action: str,
    skill_id: str,
    *,
    source: str = "",
    scan_findings: int = 0,
) -> None:
    """Structured audit log for skill lifecycle operations.

    Covers install/uninstall/enable/disable for security traceability.
    """
    logger.info(
        "SKILL_AUDIT action=%s user=sandbox skill=%s source=%s scan_findings=%d",
        action,
        skill_id,
        source,
        scan_findings,
    )

