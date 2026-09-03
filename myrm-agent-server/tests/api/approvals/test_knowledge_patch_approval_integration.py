"""Integration tests for knowledge_patch approval and guardian harvesting.

Tests:
1. harvest_session_blind_spots scans messages and creates ApprovalRecords.
2. Resolving a knowledge_patch approval writes to wiki / procedural stores.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory.strategies.blind_spot import (
    BlindSpotKnowledgePatch,
    BlindSpotResponse,
    PatchTargetType,
)

from app.database.connection import get_session
from app.database.models.chat import Chat, Message
from app.lifecycle.memory_guardian_ops import harvest_session_blind_spots
from app.services.approvals.registry import ApprovalRegistry


@pytest.mark.asyncio
async def test_harvest_session_blind_spots_creates_approval(client: TestClient) -> None:
    chat_id = f"test-chat-{uuid.uuid4().hex[:8]}"
    msg_id = f"msg-{uuid.uuid4().hex[:8]}"

    async with get_session() as db:
        chat = Chat(id=chat_id, user_id="test-user", title="Test Chat")
        db.add(chat)
        msg = Message(
            id=msg_id,
            chat_id=chat_id,
            role="user",
            content="How do I configure the external prometheus alertmanager?",
            created_at=datetime.now(UTC),
            extra_data={
                "missed_query": "How do I configure external prometheus alertmanager?",
                "thumbs_down": True,
                "user_correction": "Alertmanager requires webhook url at /api/v2/alerts",
            },
        )
        db.add(msg)
        await db.commit()

    mock_llm = MagicMock()
    mock_structured = AsyncMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.ainvoke.return_value = BlindSpotResponse(
        patches=[
            BlindSpotKnowledgePatch(
                title="Prometheus Alertmanager Webhook",
                target_type=PatchTargetType.WIKI,
                content="Alertmanager requires webhook endpoint at /api/v2/alerts with bearer auth.",
                trigger_condition="Alertmanager configuration or Prometheus webhook",
                rationale="User corrected missing endpoint details",
                confidence=0.92,
                source_queries=["How do I configure external prometheus alertmanager?"],
                suggested_action="Save to infrastructure wiki",
            )
        ],
        summary_note="Found alertmanager configuration gap",
    )

    with patch(
        "app.services.agent.platform_config.load_platform_llm",
        AsyncMock(return_value=mock_llm),
    ):
        created_count = await harvest_session_blind_spots(limit=10, since_hours=24)
        assert created_count == 1

    resp = client.get("/api/v1/approvals?limit=100&offset=0")
    assert resp.status_code == 200
    approvals = resp.json()["approvals"]
    patch_appr = next((a for a in approvals if a["action_type"] == "knowledge_patch"), None)
    assert patch_appr is not None
    assert patch_appr["payload"]["title"] == "Prometheus Alertmanager Webhook"
    assert patch_appr["payload"]["target_type"] == "wiki"
    assert patch_appr["payload"]["confidence"] == 0.92


@pytest.mark.asyncio
async def test_resolve_knowledge_patch_wiki_target(client: TestClient) -> None:
    record = await ApprovalRegistry.create_approval(
        agent_id="test-agent",
        action_type="knowledge_patch",
        reason="Session blind spot patch",
        severity="info",
        payload={
            "title": "Staging DB Connection",
            "target_type": "wiki",
            "content": "Staging DB runs at 10.0.1.20:5432 with sslmode=verify-full",
            "trigger_condition": "Connecting to staging postgres database",
            "rationale": "Clarified from user feedback",
            "confidence": 0.88,
            "source_queries": ["What is staging DB port?"],
        },
    )

    with patch("myrm_agent_harness.toolkits.wiki.pipeline.raw_gate.publish_raw", AsyncMock()) as mock_publish:
        resp = client.post(
            f"/api/v1/approvals/{record.id}/resolve",
            json={"decision": "approve"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "APPROVED"
        mock_publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_knowledge_patch_procedural_target(client: TestClient) -> None:
    record = await ApprovalRegistry.create_approval(
        agent_id="test-agent",
        action_type="knowledge_patch",
        reason="Procedural rule patch",
        severity="info",
        payload={
            "title": "Strict Type Hint Policy",
            "target_type": "procedural",
            "content": "Always annotate return types on public methods",
            "trigger_condition": "Writing Python functions",
            "rationale": "User requested PEP8 typing compliance",
            "confidence": 0.95,
        },
    )

    mock_manager = MagicMock()
    mock_rel_store = AsyncMock()
    mock_manager.relational_store = mock_rel_store

    with patch(
        "app.lifecycle.memory_guardian_ops.create_guardian_memory_manager",
        AsyncMock(return_value=mock_manager),
    ):
        resp = client.post(
            f"/api/v1/approvals/{record.id}/resolve",
            json={"decision": "approve"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "APPROVED"
        mock_rel_store.add_procedural_rule.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_knowledge_patch_rejected(client: TestClient) -> None:
    record = await ApprovalRegistry.create_approval(
        agent_id="test-agent",
        action_type="knowledge_patch",
        reason="Rejected patch",
        severity="info",
        payload={
            "title": "Temporary Hack",
            "target_type": "wiki",
            "content": "Do not commit",
        },
    )

    with patch("myrm_agent_harness.toolkits.wiki.pipeline.raw_gate.publish_raw", AsyncMock()) as mock_publish:
        resp = client.post(
            f"/api/v1/approvals/{record.id}/resolve",
            json={"decision": "deny"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"
        mock_publish.assert_not_awaited()
