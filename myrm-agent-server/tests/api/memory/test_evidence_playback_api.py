"""Unit and contract tests for Memory Evidence Playback API."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.api.memory.operations import command_center as command_center_operation
from app.api.memory.utils import get_crud_memory_manager
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

    def _mock_manager() -> MagicMock:
        return MagicMock()

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_crud_memory_manager] = _mock_manager
    return TestClient(app)


def test_get_evidence_playback_endpoint(evidence_client: TestClient) -> None:
    now = datetime.now(UTC)
    mock_playback = MemoryEvidencePlaybackResponse(
        status="live_context",
        source_type="chat",
        source_id="chat-abc-123",
        target_message_id="msg-target-456",
        channel="web",
        quote_snippet="Port is 8080",
        author_name="Alice",
        author_id="user-1",
        occurred_at=now,
        turns=[
            MemoryEvidencePlaybackTurn(
                message_id="msg-prev",
                role="user",
                sender_name="Alice",
                content="Which port should I configure?",
                sent_at=now,
                is_target=False,
                is_self=False,
            ),
            MemoryEvidencePlaybackTurn(
                message_id="msg-target-456",
                role="assistant",
                sender_name="MyrmAgent",
                content="Port is 8080 for web server.",
                sent_at=now,
                is_target=True,
                is_self=True,
            ),
        ],
        is_user_locked=False,
    )

    with patch(
        "app.api.memory.operations.command_center.EvidencePlaybackService.get_playback",
        new=AsyncMock(return_value=mock_playback),
    ):
        resp = evidence_client.get(
            "/api/memory/command-center/evidence/playback",
            params={
                "source_id": "chat-abc-123",
                "message_id": "msg-target-456",
                "quote_snippet": "Port is 8080",
                "author_name": "Alice",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "live_context"
        assert data["source_id"] == "chat-abc-123"
        assert data["target_message_id"] == "msg-target-456"
        assert len(data["turns"]) == 2
        assert data["turns"][1]["is_target"] is True
        assert data["turns"][1]["content"] == "Port is 8080 for web server."
