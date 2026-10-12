"""Unit tests for MemoryDefenseFirewallService."""

from __future__ import annotations

import pytest

from app.schemas.memory_defense_firewall import (
    DefenseInspectRequest,
)
from app.services.security.memory_defense_firewall_service import (
    MemoryDefenseFirewallService,
)


@pytest.fixture
def service() -> MemoryDefenseFirewallService:
    return MemoryDefenseFirewallService()


def test_inspect_clean_text_allow(service: MemoryDefenseFirewallService) -> None:
    req = DefenseInspectRequest(text="Meeting notes: discussed clean architecture and roadmap.")
    resp = service.inspect_and_defend(req)

    assert resp.action_taken == "ALLOW"
    assert resp.is_admitted is True
    assert resp.sanitized_text == req.text
    assert len(resp.matches) == 0
    assert resp.audit_id.startswith("mdf_")


def test_inspect_sensitive_text_redact(service: MemoryDefenseFirewallService) -> None:
    raw = "My OpenAI secret is sk-proj-1234567890abcdef1234567890abcdef1234567890 please keep it safe."
    req = DefenseInspectRequest(text=raw, default_action="REDACT")
    resp = service.inspect_and_defend(req)

    assert resp.action_taken == "REDACT"
    assert resp.is_admitted is True
    assert "[REDACTED_OPENAI_KEY]" in resp.sanitized_text
    assert "sk-proj-" not in resp.sanitized_text
    assert len(resp.matches) >= 1


def test_inspect_sensitive_text_block(service: MemoryDefenseFirewallService) -> None:
    raw = "Hostile payload with database creds: postgres://root:superSecret123@db.prod.internal:5432/core"
    req = DefenseInspectRequest(text=raw, default_action="BLOCK")
    resp = service.inspect_and_defend(req)

    assert resp.action_taken == "BLOCK"
    assert resp.is_admitted is False
    assert resp.sanitized_text == ""
    assert len(resp.matches) >= 1


def test_exemption_management_lifecycle(service: MemoryDefenseFirewallService) -> None:
    token = "ghp_111122223333444455556666777788889999"
    text = f"Sample code example with token: {token}"

    # 1. Before exemption: redacted
    resp_before = service.inspect_and_defend(DefenseInspectRequest(text=text))
    assert resp_before.action_taken == "REDACT"

    # 2. Add exemption
    add_resp = service.add_exemption(token)
    assert add_resp.success is True

    # 3. List exemptions
    list_resp = service.list_exemptions()
    assert token in list_resp.exemptions

    # 4. After exemption: allowed
    resp_after = service.inspect_and_defend(DefenseInspectRequest(text=text))
    assert resp_after.action_taken == "ALLOW"
    assert token in resp_after.sanitized_text

    # 5. Remove exemption
    del_resp = service.remove_exemption(token)
    assert del_resp.success is True


def test_pattern_catalog_and_audit_history(service: MemoryDefenseFirewallService) -> None:
    catalog = service.get_pattern_catalog()
    assert catalog.total_count >= 40
    assert any(p.pattern_id == "openai_key" for p in catalog.patterns)

    service.inspect_and_defend(DefenseInspectRequest(text="Normal log entry."))
    records = service.get_audit_records(limit=10)
    assert len(records) >= 1
    assert records[-1].action_taken == "ALLOW"
