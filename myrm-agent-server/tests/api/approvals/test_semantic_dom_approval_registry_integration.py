"""Integration tests for high_risk_dom_action approval registry + HTTP API.

Exercises extract_approval_registry_payload → ApprovalRegistry → GET/POST /approvals
without mocks on the persistence path (real in-memory SQLite via conftest).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.services.agent.approval_payload import extract_approval_registry_payload
from app.services.approvals.registry import ApprovalRegistry


def _flat_semantic_dom_interrupt() -> dict[str, object]:
    expr = "document.querySelector('.checkout').click()"
    return {
        "action_type": "high_risk_dom_action",
        "tool_name": "browser_manage_tool",
        "tool_input": {"action": "evaluate", "expression": expr},
        "page_url": "https://shop.example.com/cart",
        "reason": "Mutating JS evaluate requires human confirmation",
        "severity": "warning",
        "thread_id": "langgraph-thread-dom-hitl",
    }


class TestSemanticDomApprovalRegistryIntegration:
    @pytest.mark.asyncio
    async def test_flat_interrupt_persists_tool_input_and_page_url(self, client: TestClient) -> None:
        interrupt = _flat_semantic_dom_interrupt()
        payload = extract_approval_registry_payload(interrupt)

        record = await ApprovalRegistry.create_approval(
            agent_id="builtin-general",
            chat_id=str(uuid.uuid4()),
            thread_id=str(interrupt["thread_id"]),
            action_type=str(interrupt["action_type"]),
            payload=payload,
            reason=str(interrupt["reason"]),
            severity=str(interrupt["severity"]),
            status="PENDING",
        )

        resp = client.get("/api/v1/approvals?limit=100&offset=0")
        assert resp.status_code == 200
        match = next((a for a in resp.json()["approvals"] if a["id"] == record.id), None)
        assert match is not None, "Created approval must appear in pending list"

        stored = match["payload"]
        tool_input = stored.get("tool_input")
        assert isinstance(tool_input, dict)
        assert tool_input.get("action") == "evaluate"
        assert tool_input.get("expression") == interrupt["tool_input"]["expression"]  # type: ignore[index]
        assert stored.get("page_url") == interrupt["page_url"]
        assert stored.get("tool_name") == interrupt["tool_name"]
        assert match["action_type"] == "high_risk_dom_action"

    @pytest.mark.asyncio
    async def test_click_interrupt_persists_element_metadata(self, client: TestClient) -> None:
        interrupt: dict[str, object] = {
            "action_type": "high_risk_dom_action",
            "tool_name": "browser_interact_tool",
            "tool_input": {"action": "click", "ref": "e5", "text": ""},
            "element": {"role": "button", "name": "Delete Repository", "ref": "e5"},
            "page_url": "https://github.com/settings",
            "reason": "High-risk destructive click",
            "severity": "warning",
            "thread_id": "langgraph-thread-dom-click",
        }
        payload = extract_approval_registry_payload(interrupt)

        record = await ApprovalRegistry.create_approval(
            agent_id="builtin-general",
            chat_id=str(uuid.uuid4()),
            thread_id=str(interrupt["thread_id"]),
            action_type="high_risk_dom_action",
            payload=payload,
            reason=str(interrupt["reason"]),
            severity="warning",
            status="PENDING",
        )

        resp = client.get("/api/v1/approvals?limit=100&offset=0")
        match = next(a for a in resp.json()["approvals"] if a["id"] == record.id)
        assert match["payload"]["element"] == interrupt["element"]
        assert match["payload"]["tool_input"]["action"] == "click"

    @pytest.mark.asyncio
    async def test_resolve_approve_via_http_api(self, client: TestClient) -> None:
        interrupt = _flat_semantic_dom_interrupt()
        payload = extract_approval_registry_payload(interrupt)

        record = await ApprovalRegistry.create_approval(
            agent_id="builtin-general",
            chat_id=str(uuid.uuid4()),
            thread_id=str(interrupt["thread_id"]),
            action_type="high_risk_dom_action",
            payload=payload,
            reason=str(interrupt["reason"]),
            severity="warning",
            status="PENDING",
        )

        resolve_resp = client.post(
            f"/api/v1/approvals/{record.id}/resolve",
            json={"decision": "approve"},
        )
        assert resolve_resp.status_code == 200
        body = resolve_resp.json()
        assert body["status"] == "APPROVED"
        assert body["payload"]["tool_input"]["expression"] == interrupt["tool_input"]["expression"]  # type: ignore[index]

        list_resp = client.get("/api/v1/approvals?limit=100&offset=0")
        pending_ids = {a["id"] for a in list_resp.json()["approvals"]}
        assert record.id not in pending_ids

    @pytest.mark.asyncio
    async def test_resolve_reject_via_http_api(self, client: TestClient) -> None:
        interrupt = _flat_semantic_dom_interrupt()
        payload = extract_approval_registry_payload(interrupt)

        record = await ApprovalRegistry.create_approval(
            agent_id="builtin-general",
            chat_id=str(uuid.uuid4()),
            thread_id=str(interrupt["thread_id"]),
            action_type="high_risk_dom_action",
            payload=payload,
            reason=str(interrupt["reason"]),
            severity="warning",
            status="PENDING",
        )

        resolve_resp = client.post(
            f"/api/v1/approvals/{record.id}/resolve",
            json={"decision": "reject"},
        )
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["status"] == "REJECTED"
