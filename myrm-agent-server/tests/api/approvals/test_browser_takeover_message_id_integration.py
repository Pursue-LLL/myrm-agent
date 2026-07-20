"""Integration tests for browser_takeover approval payload messageId persistence."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.services.agent.approval_payload import extract_approval_registry_payload
from app.services.approvals.registry import ApprovalRegistry


def _browser_takeover_interrupt(*, message_id: str) -> tuple[dict[str, object], dict[str, object]]:
    interrupt: dict[str, object] = {
        "action_type": "browser_takeover",
        "tool_name": "browser_ask_human_tool",
        "reason": "Complete login in Chrome",
        "url": "about:blank",
        "is_managed": False,
        "severity": "warning",
        "thread_id": f"langgraph-thread-takeover-{uuid.uuid4().hex[:8]}",
    }
    payload = extract_approval_registry_payload(interrupt)
    payload = {**payload, "messageId": message_id}
    return interrupt, payload


class TestBrowserTakeoverMessageIdIntegration:
    @pytest.mark.asyncio
    async def test_browser_takeover_persists_message_id_in_payload(self, client: TestClient) -> None:
        message_id = f"msg-{uuid.uuid4().hex[:12]}"
        interrupt, payload = _browser_takeover_interrupt(message_id=message_id)

        record = await ApprovalRegistry.create_approval(
            agent_id="builtin-general",
            chat_id=str(uuid.uuid4()),
            thread_id=str(interrupt["thread_id"]),
            action_type="browser_takeover",
            payload=payload,
            reason=str(interrupt["reason"]),
            severity=str(interrupt["severity"]),
            status="PENDING",
        )

        resp = client.get("/api/v1/approvals?limit=100&offset=0")
        assert resp.status_code == 200
        match = next((a for a in resp.json()["approvals"] if a["id"] == record.id), None)
        assert match is not None, "Created browser_takeover approval must appear in pending list"

        stored = match["payload"]
        assert stored.get("messageId") == message_id
        assert stored.get("url") == interrupt["url"]
        assert stored.get("is_managed") is False

    @pytest.mark.asyncio
    async def test_resolve_pending_browser_takeover_for_chat(self) -> None:
        chat_id = str(uuid.uuid4())
        message_id = f"msg-{uuid.uuid4().hex[:12]}"
        _, payload = _browser_takeover_interrupt(message_id=message_id)

        record = await ApprovalRegistry.create_approval(
            agent_id="builtin-general",
            chat_id=chat_id,
            thread_id=f"langgraph-thread-takeover-{uuid.uuid4().hex[:8]}",
            action_type="browser_takeover",
            payload=payload,
            reason="Complete login in Chrome",
            severity="warning",
            status="PENDING",
        )

        resolved = await ApprovalRegistry.resolve_pending_browser_takeover_for_chat(
            chat_id,
            decision="approve",
        )
        assert resolved == 1

        refreshed = await ApprovalRegistry.resolve_approval(record.id, "approve")
        assert refreshed is None
