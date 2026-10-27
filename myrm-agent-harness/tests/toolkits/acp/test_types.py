"""Tests for the ACP runtime types: RuntimeConfig and RuntimeEvent."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.acp.types import (
    AcpErrorCode,
    RuntimeConfig,
    RuntimeEventType,
    create_event,
    create_permission_request,
)


class TestRuntimeConfig:
    def test_defaults(self) -> None:
        cfg = RuntimeConfig(backend_type="acp", command="claude")
        assert cfg.command == "claude"
        assert cfg.args == []
        assert cfg.env is None
        assert cfg.cwd is None
        assert cfg.timeout_seconds == 300
        assert cfg.permission_mode == "allow_all"
        assert cfg.allowed_tools == []
        assert cfg.max_response_chars == 50_000

    def test_custom_values(self) -> None:
        cfg = RuntimeConfig(
            backend_type="cli",
            command="codex",
            args=["--acp"],
            env={"MY_VAR": "1"},
            cwd="/workspace",
            timeout_seconds=120,
            permission_mode="safe",
            allowed_tools=["Read", "Bash(npm run *)"],
        )
        assert cfg.command == "codex"
        assert cfg.backend_type == "cli"
        assert cfg.timeout_seconds == 120
        assert cfg.permission_mode == "safe"

    def test_max_turns_default(self) -> None:
        cfg = RuntimeConfig(backend_type="acp", command="test")
        assert cfg.max_turns == 25

    def test_description_default(self) -> None:
        cfg = RuntimeConfig(backend_type="acp", command="test")
        assert cfg.description == ""

    def test_custom_max_turns_and_description(self) -> None:
        cfg = RuntimeConfig(
            backend_type="cli",
            command="claude",
            max_turns=50,
            description="A powerful coding agent",
        )
        assert cfg.max_turns == 50
        assert cfg.description == "A powerful coding agent"

    def test_max_turns_zero_disables(self) -> None:
        cfg = RuntimeConfig(backend_type="cli", command="claude", max_turns=0)
        assert cfg.max_turns == 0

    def test_frozen(self) -> None:
        cfg = RuntimeConfig(backend_type="acp", command="test")
        with pytest.raises(AttributeError):
            cfg.command = "other"  # type: ignore[misc]


class TestRuntimeEvent:
    def test_create_event(self) -> None:
        event = create_event(RuntimeEventType.TEXT_DELTA, "sess-1", content="hello")
        assert event.type == RuntimeEventType.TEXT_DELTA
        assert event.data["content"] == "hello"
        assert event.session_id == "sess-1"
        assert event.timestamp > 0

    @pytest.mark.asyncio
    async def test_create_permission_request(self) -> None:
        event, _future = create_permission_request("sess-1", "Write", {"path": "/tmp"})
        assert event.type == RuntimeEventType.PERMISSION_REQUEST
        assert event.data["tool_name"] == "Write"
        assert "response_future" in event.data

    def test_event_types_count(self) -> None:
        assert len(RuntimeEventType) == 9

    def test_error_codes_count(self) -> None:
        assert len(AcpErrorCode) == 8
        assert AcpErrorCode.MAX_TURNS == "max_turns"
        assert AcpErrorCode.BACKEND_NOT_FOUND == "backend_not_found"
