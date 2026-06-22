"""Unit tests for database DTO models."""

from datetime import datetime, timezone

import pytest

from app.database.dto import ChatDetail, CommandBindingConfig


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


class TestCommandBindingConfig:
    """CommandBindingConfig DTO validation and backward compatibility."""

    def test_new_format_skill_ids(self) -> None:
        cfg = CommandBindingConfig(
            command_name="deploy",
            skill_ids=["deploy_skill", "notify_skill"],
        )
        assert cfg.skill_ids == ["deploy_skill", "notify_skill"]
        assert cfg.instruction == ""

    def test_legacy_skill_id_migrated(self) -> None:
        cfg = CommandBindingConfig.model_validate(
            {"command_name": "report", "skill_id": "daily_report_skill"}
        )
        assert cfg.skill_ids == ["daily_report_skill"]

    def test_legacy_empty_skill_id(self) -> None:
        cfg = CommandBindingConfig.model_validate(
            {"command_name": "noop", "skill_id": ""}
        )
        assert cfg.skill_ids == []

    def test_skill_ids_takes_precedence_over_skill_id(self) -> None:
        cfg = CommandBindingConfig.model_validate(
            {
                "command_name": "test",
                "skill_id": "old",
                "skill_ids": ["new_a", "new_b"],
            }
        )
        assert cfg.skill_ids == ["new_a", "new_b"]

    def test_instruction_field(self) -> None:
        cfg = CommandBindingConfig(
            command_name="combo",
            skill_ids=["a", "b"],
            instruction="be concise",
        )
        assert cfg.instruction == "be concise"

    def test_defaults(self) -> None:
        cfg = CommandBindingConfig(command_name="minimal")
        assert cfg.skill_ids == []
        assert cfg.description == ""
        assert cfg.aliases == []
        assert cfg.instruction == ""

    def test_serialization_roundtrip(self) -> None:
        cfg = CommandBindingConfig(
            command_name="deploy",
            skill_ids=["deploy_skill"],
            description="Deploy app",
            instruction="use prod env",
        )
        data = cfg.model_dump()
        restored = CommandBindingConfig.model_validate(data)
        assert restored.command_name == cfg.command_name
        assert restored.skill_ids == cfg.skill_ids
        assert restored.instruction == cfg.instruction

    def test_legacy_skill_id_ignored_when_skill_ids_present(self) -> None:
        cfg = CommandBindingConfig.model_validate(
            {"command_name": "x", "skill_id": "old", "skill_ids": ["a", "b"]}
        )
        assert cfg.skill_ids == ["a", "b"]

    def test_legacy_none_skill_id(self) -> None:
        cfg = CommandBindingConfig.model_validate(
            {"command_name": "x", "skill_id": None}
        )
        assert cfg.skill_ids == []

    def test_command_name_max_length(self) -> None:
        cfg = CommandBindingConfig(command_name="a" * 50)
        assert len(cfg.command_name) == 50
        with pytest.raises(Exception):
            CommandBindingConfig(command_name="a" * 51)
