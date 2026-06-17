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

    def test_is_incognito_defaults_to_false(self, _now: datetime) -> None:
        detail = ChatDetail(
            id="chat-005",
            title="Test",
            actionMode="agent",
            created_at=_now,
            updated_at=_now,
        )
        assert detail.is_incognito is False

    def test_is_incognito_true(self, _now: datetime) -> None:
        detail = ChatDetail(
            id="chat-006",
            title="Incognito Chat",
            actionMode="agent",
            is_incognito=True,
            created_at=_now,
            updated_at=_now,
        )
        assert detail.is_incognito is True
        data = detail.model_dump()
        assert data["is_incognito"] is True

    def test_both_agent_id_and_incognito(self, _now: datetime) -> None:
        detail = ChatDetail(
            id="chat-007",
            title="Agent + Incognito",
            actionMode="agent",
            agent_id="agent-x",
            is_incognito=True,
            created_at=_now,
            updated_at=_now,
        )
        data = detail.model_dump()
        assert data["agent_id"] == "agent-x"
        assert data["is_incognito"] is True

    def test_json_serialization_roundtrip(self, _now: datetime) -> None:
        detail = ChatDetail(
            id="chat-008",
            title="Roundtrip",
            actionMode="fast",
            agent_id="builtin-coder",
            is_incognito=False,
            created_at=_now,
            updated_at=_now,
        )
        json_str = detail.model_dump_json()
        assert '"agent_id":"builtin-coder"' in json_str
        assert '"is_incognito":false' in json_str
