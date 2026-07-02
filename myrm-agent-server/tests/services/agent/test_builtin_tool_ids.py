"""Tests for canonical enabled_builtin_tools SSOT."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.database.dto import AgentCreate, AgentUpdate
from app.services.agent.builtin_tool_ids import (
    BUILTIN_TOOL_IDS,
    BUILTIN_TOOL_ID_SET,
    DEFAULT_ENABLED_BUILTIN_TOOLS,
    InvalidBuiltinToolIdsError,
    normalize_enabled_builtin_tools,
)
from app.services.agent.params.models import AgentConfigRequest

_FRONTEND_BUILTIN_TOOLS_TS = (
    Path(__file__).resolve().parents[4]
    / "myrm-agent-frontend"
    / "src"
    / "store"
    / "chat"
    / "types"
    / "builtinTools.ts"
)


def _parse_frontend_builtin_tool_contract() -> tuple[list[str], list[str]]:
    text = _FRONTEND_BUILTIN_TOOLS_TS.read_text(encoding="utf-8")
    ids_block = re.search(
        r"export const BUILTIN_TOOL_IDS:.*?=\s*\[(.*?)\]\s*as const;",
        text,
        re.DOTALL,
    )
    defaults_block = re.search(
        r"export const DEFAULT_ENABLED_BUILTIN_TOOLS.*?=\s*\[(.*?)\];",
        text,
        re.DOTALL,
    )
    assert ids_block is not None, "BUILTIN_TOOL_IDS block missing in frontend SSOT"
    assert defaults_block is not None, "DEFAULT_ENABLED_BUILTIN_TOOLS block missing"
    ids = re.findall(r"'([^']+)'", ids_block.group(1))
    defaults = re.findall(r"'([^']+)'", defaults_block.group(1))
    return ids, defaults


def test_frontend_builtin_tool_ids_match_server_ssot() -> None:
    frontend_ids, frontend_defaults = _parse_frontend_builtin_tool_contract()
    assert list(BUILTIN_TOOL_IDS) == frontend_ids
    assert set(frontend_ids) == BUILTIN_TOOL_ID_SET
    assert list(DEFAULT_ENABLED_BUILTIN_TOOLS) == frontend_defaults


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


def test_normalize_skips_empty_strings() -> None:
    assert normalize_enabled_builtin_tools(["web_search", "", "  ", "memory"]) == [
        "web_search",
        "memory",
    ]


def test_coerce_enabled_builtin_tools_none_uses_default() -> None:
    from app.services.agent.builtin_tool_ids import coerce_enabled_builtin_tools

    assert coerce_enabled_builtin_tools(None) == list(DEFAULT_ENABLED_BUILTIN_TOOLS)


def test_coerce_enabled_builtin_tools_normalizes() -> None:
    from app.services.agent.builtin_tool_ids import coerce_enabled_builtin_tools

    assert coerce_enabled_builtin_tools(["file_ops", "file_ops"]) == ["file_ops"]


def test_persist_enabled_builtin_tools_none_uses_default() -> None:
    from app.services.agent.builtin_tool_ids import persist_enabled_builtin_tools

    assert persist_enabled_builtin_tools(None) == list(DEFAULT_ENABLED_BUILTIN_TOOLS)


def test_persist_enabled_builtin_tools_rejects_non_list() -> None:
    from app.services.agent.builtin_tool_ids import persist_enabled_builtin_tools

    with pytest.raises(ValueError, match="must be a list"):
        persist_enabled_builtin_tools("web_search")


def test_persist_enabled_builtin_tools_normalizes_list() -> None:
    from app.services.agent.builtin_tool_ids import persist_enabled_builtin_tools

    assert persist_enabled_builtin_tools(["wiki", "kanban"]) == ["wiki", "kanban"]


def test_optional_builtin_tools_validator_accepts_none() -> None:
    from app.services.agent.builtin_tool_validation import _validate_optional_builtin_tools

    assert _validate_optional_builtin_tools(None) is None


def test_optional_builtin_tools_validator_rejects_non_list() -> None:
    from app.services.agent.builtin_tool_validation import _validate_optional_builtin_tools

    with pytest.raises(TypeError, match="must be a list"):
        _validate_optional_builtin_tools("web_search")


def test_required_builtin_tools_validator_defaults_when_none() -> None:
    from app.services.agent.builtin_tool_validation import _validate_required_builtin_tools

    assert _validate_required_builtin_tools(None) == list(DEFAULT_ENABLED_BUILTIN_TOOLS)


def test_required_builtin_tools_validator_rejects_non_list() -> None:
    from app.services.agent.builtin_tool_validation import _validate_required_builtin_tools

    with pytest.raises(TypeError, match="must be a list"):
        _validate_required_builtin_tools({"web_search"})
