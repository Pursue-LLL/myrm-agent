"""Core skill audit logging."""

from __future__ import annotations

import logging

from app.core.skills.audit import audit_skill_action


def test_audit_skill_action_emits_structured_info(caplog) -> None:
    with caplog.at_level(logging.INFO):
        audit_skill_action("install", "prebuilt::demo", source="clawhub", scan_findings=2)

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "SKILL_AUDIT action=install" in message
    assert "prebuilt::demo" in message
    assert "clawhub" in message
