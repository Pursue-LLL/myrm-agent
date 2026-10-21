"""Contract tests for Evidence Playback endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.api.memory.operations import command_center as command_center_operation
from app.schemas.memory.command_center import (
    MemoryEvidencePlaybackResponse,
    MemoryEvidencePlaybackTurn,
)


@pytest.fixture
def evidence_client() -> TestClient:
    app = FastAPI()
    app.include_router(command_center_operation.router, prefix="/api/memory")

    async def _mock_db() -> AsyncMock:
        return AsyncMock()

    app.dependency_overrides[get_db_session] = _mock_db
    return TestClient(app)


def test_get_evidence_playback_endpoint_live(evidence_client: TestClient) -> None:
    now = datetime.now(UTC)
    mock_response = MemoryEvidencePlaybackResponse(
        status="live_context",
        source_type="chat",
        source_id="chat-123",
        target_message_id="msg-target",
        quote_snippet="We should use pnpm for frontend",
        occurred_at=now,
        turns=[
            MemoryEvidencePlaybackTurn(
                message_id="msg-1",
                role="user",
                sender_name="Alice",
                content="What package manager do we use?",
                sent_at=now,
                is_target=False,
                is_self=True,
            ),
            MemoryEvidencePlaybackTurn(
                message_id="msg-target",
                role="assistant",
                sender_name="Assistant",
                content="We should use pnpm for frontend builds.",
                sent_at=now,
                is_target=True,
                is_self=False,
            ),
        ],
        is_user_locked=True,
    )

    with patch(
        "app.api.memory.operations.command_center.EvidencePlaybackService.get_playback",
        new=AsyncMock(return_value=mock_response),
    ):
        resp = evidence_client.get("/api/memory/command-center/evidence/playback?source_id=chat-123&message_id=msg-target")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "live_context"
        assert data["source_type"] == "chat"
        assert data["target_message_id"] == "msg-target"
        assert len(data["turns"]) == 2
        assert data["turns"][1]["is_target"] is True
        assert data["is_user_locked"] is True


def test_get_evidence_playback_endpoint_archived_fallback(evidence_client: TestClient) -> None:
    now = datetime.now(UTC)
    mock_response = MemoryEvidencePlaybackResponse(
        status="archived_snapshot",
        source_type="channel",
        source_id="slack-arch",
        target_message_id="msg-purged",
        channel="slack",
        quote_snippet="Temporary proxy configuration token=***REDACTED***",
        occurred_at=now,
        turns=[
            MemoryEvidencePlaybackTurn(
                message_id="msg-purged",
                role="user",
                sender_name="Bob",
                content="Temporary proxy configuration token=***REDACTED***",
                sent_at=now,
                is_target=True,
                is_self=True,
            )
        ],
        is_user_locked=False,
    )

    with patch(
        "app.api.memory.operations.command_center.EvidencePlaybackService.get_playback",
        new=AsyncMock(return_value=mock_response),
    ):
        resp = evidence_client.get("/api/memory/command-center/evidence/playback?channel_id=slack&quote_snippet=Temporary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "archived_snapshot"
        assert data["channel"] == "slack"
        assert "***REDACTED***" in data["quote_snippet"]
        assert len(data["turns"]) == 1
