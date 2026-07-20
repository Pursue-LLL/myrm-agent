"""Tests for canonical enabled_builtin_tools SSOT."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError
from unittest.mock import patch

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
    assert set(frontend_ids) == set(BUILTIN_TOOL_IDS)
    assert list(DEFAULT_ENABLED_BUILTIN_TOOLS) == frontend_defaults


def test_default_tools_match_frontend_contract() -> None:
    assert DEFAULT_ENABLED_BUILTIN_TOOLS == (
        "web_search",
        "memory",
        "structured_clarify",
    )
    assert len(BUILTIN_TOOL_ID_SET) == 17
    assert len(BUILTIN_TOOL_IDS) == 15


def test_normalize_strips_agent_baseline_ids() -> None:
    assert normalize_enabled_builtin_tools(
        ["web_search", "memory", "file_ops", "code_execute"]
    ) == ["web_search", "memory"]


def test_normalize_rejects_legacy_ids() -> None:
    with pytest.raises(InvalidBuiltinToolIdsError, match="image_gen"):
        normalize_enabled_builtin_tools(["web_search", "image_gen"])


def test_strip_legacy_task_tracking_on_read_path() -> None:
    from app.services.agent.builtin_tool_ids import (
        normalize_enabled_builtin_tools,
        strip_legacy_builtin_tool_ids,
    )

    assert normalize_enabled_builtin_tools(
        strip_legacy_builtin_tool_ids(["web_search", "task_tracking"])
    ) == ["web_search"]


def test_strip_deploy_incompatible_removes_computer_use_when_unsupported() -> None:
    from app.services.agent.builtin_tool_ids import strip_deploy_incompatible_builtin_tools

    with patch(
        "app.config.computer_use_deploy.is_computer_use_deploy_supported",
        return_value=False,
    ):
        assert strip_deploy_incompatible_builtin_tools(["web_search", "computer_use"]) == [
            "web_search"
        ]


def test_strip_deploy_incompatible_keeps_computer_use_when_supported() -> None:
    from app.services.agent.builtin_tool_ids import strip_deploy_incompatible_builtin_tools

    with patch(
        "app.config.computer_use_deploy.is_computer_use_deploy_supported",
        return_value=True,
    ):
        assert strip_deploy_incompatible_builtin_tools(["browser", "computer_use"]) == [
            "browser",
            "computer_use",
        ]


def test_strip_deploy_incompatible_removes_external_cli_when_unsupported() -> None:
    from app.services.agent.builtin_tool_ids import strip_deploy_incompatible_builtin_tools

    with patch(
        "app.config.external_cli_deploy.is_external_cli_deploy_supported",
        return_value=False,
    ):
        assert strip_deploy_incompatible_builtin_tools(["web_search", "external_cli"]) == [
            "web_search",
        ]


def test_strip_deploy_incompatible_keeps_external_cli_when_supported() -> None:
    from app.services.agent.builtin_tool_ids import strip_deploy_incompatible_builtin_tools

    with patch(
        "app.config.external_cli_deploy.is_external_cli_deploy_supported",
        return_value=True,
    ):
        assert strip_deploy_incompatible_builtin_tools(["memory", "external_cli"]) == [
            "memory",
            "external_cli",
        ]


def test_normalize_rejects_legacy_task_tracking() -> None:
    with pytest.raises(InvalidBuiltinToolIdsError, match="task_tracking"):
        normalize_enabled_builtin_tools(["web_search", "task_tracking"])


def test_normalize_rejects_unknown_ids() -> None:
    with pytest.raises(InvalidBuiltinToolIdsError, match="unknown IDs"):
        normalize_enabled_builtin_tools(["web_search", "not_a_real_tool"])


def test_normalize_deduplicates_preserving_order() -> None:
    assert normalize_enabled_builtin_tools(
        ["memory", "web_search", "memory", "file_ops"]
    ) == ["memory", "web_search"]


def test_agent_config_request_rejects_legacy_id() -> None:
    with pytest.raises(ValidationError):
        AgentConfigRequest(enabled_builtin_tools=["code_interpreter"])


def test_agent_create_rejects_legacy_id() -> None:
    with pytest.raises(ValidationError):
        AgentCreate(name="Bad Agent", enabled_builtin_tools=["shell_exec"])


def test_agent_update_accepts_canonical_ids() -> None:
    updated = AgentUpdate(enabled_builtin_tools=["wiki", "kanban"])
    assert updated.enabled_builtin_tools == ["wiki", "kanban"]


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

    assert coerce_enabled_builtin_tools(["wiki", "wiki"]) == ["wiki"]


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


def test_builtin_initializer_specs_exclude_agent_baseline_tools() -> None:
    from app.services.agent.builtin_initializer import _BUILTIN_AGENTS
    from app.services.agent.builtin_tool_ids import AGENT_BASELINE_BUILTIN_TOOLS

    baseline = set(AGENT_BASELINE_BUILTIN_TOOLS)
    for spec in _BUILTIN_AGENTS:
        if spec.enabled_builtin_tools is None:
            continue
        overlap = baseline.intersection(spec.enabled_builtin_tools)
        assert not overlap, f"{spec.id!r} must not persist baseline tools {sorted(overlap)}"


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
