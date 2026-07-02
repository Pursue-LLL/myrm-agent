"""Tests for canonical enabled_builtin_tools SSOT."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.database.dto import AgentCreate, AgentUpdate
from app.services.agent.builtin_tool_ids import (
    BUILTIN_TOOL_ID_SET,
    DEFAULT_ENABLED_BUILTIN_TOOLS,
    InvalidBuiltinToolIdsError,
    normalize_enabled_builtin_tools,
)
from app.services.agent.params.models import AgentConfigRequest


def test_default_tools_match_frontend_contract() -> None:
    assert DEFAULT_ENABLED_BUILTIN_TOOLS == ("web_search", "memory")
    assert len(BUILTIN_TOOL_ID_SET) == 16


def test_normalize_rejects_legacy_ids() -> None:
    with pytest.raises(InvalidBuiltinToolIdsError, match="image_gen"):
        normalize_enabled_builtin_tools(["web_search", "image_gen"])


def test_normalize_rejects_unknown_ids() -> None:
    with pytest.raises(InvalidBuiltinToolIdsError, match="unknown IDs"):
        normalize_enabled_builtin_tools(["web_search", "not_a_real_tool"])


def test_normalize_deduplicates_preserving_order() -> None:
    assert normalize_enabled_builtin_tools(
        ["memory", "web_search", "memory", "file_ops"]
    ) == ["memory", "web_search", "file_ops"]


def test_agent_config_request_rejects_legacy_id() -> None:
    with pytest.raises(ValidationError):
        AgentConfigRequest(enabled_builtin_tools=["code_interpreter"])


def test_agent_create_rejects_legacy_id() -> None:
    with pytest.raises(ValidationError):
        AgentCreate(name="Bad Agent", enabled_builtin_tools=["shell_exec"])


def test_agent_update_accepts_canonical_ids() -> None:
    updated = AgentUpdate(enabled_builtin_tools=["file_ops", "code_execute"])
    assert updated.enabled_builtin_tools == ["file_ops", "code_execute"]
