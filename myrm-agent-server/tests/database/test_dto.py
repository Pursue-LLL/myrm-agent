"""Unit tests for database DTO models."""

from datetime import datetime, timezone

import pytest

from app.database.dto import ChatDetail


class TestChatDetail:
    """ChatDetail DTO field validation."""

    @pytest.fixture()
    def _now(self) -> datetime:
        return datetime.now(tz=timezone.utc)

    def test_agent_id_included(self, _now: datetime) -> None:
        detail = ChatDetail(
            id="chat-001",
            title="Test",
            actionMode="agent",
            agent_id="builtin-general",
            created_at=_now,
            updated_at=_now,
        )
        assert detail.agent_id == "builtin-general"

    def test_agent_id_defaults_to_none(self, _now: datetime) -> None:
        detail = ChatDetail(
            id="chat-002",
            title="Test",
            actionMode="agent",
            created_at=_now,
            updated_at=_now,
        )
        assert detail.agent_id is None

    def test_serialization_includes_agent_id(self, _now: datetime) -> None:
        detail = ChatDetail(
            id="chat-003",
            title="Test",
            actionMode="agent",
            agent_id="custom-agent",
            created_at=_now,
            updated_at=_now,
        )
        data = detail.model_dump()
        assert "agent_id" in data
        assert data["agent_id"] == "custom-agent"

    def test_serialization_none_agent_id(self, _now: datetime) -> None:
        detail = ChatDetail(
            id="chat-004",
            title="Test",
            actionMode="agent",
            created_at=_now,
            updated_at=_now,
        )
        data = detail.model_dump()
        assert "agent_id" in data
        assert data["agent_id"] is None
