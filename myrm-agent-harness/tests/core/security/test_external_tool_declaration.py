"""A tool defined outside the harness states its permission type and safety attributes explicitly.

An undeclared tool resolves to ``mcp_invoke`` (ask) with fail-closed safety attributes. A declaration is the only way a
tool the harness does not ship joins a permission type the built-in tools already use.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from myrm_agent_harness.agent.middlewares.tooling._runtime_tool_governance import derive_runtime_allowed_tools
from myrm_agent_harness.agent.security.engine import evaluate_tool_call
from myrm_agent_harness.agent.security.types import PermissionAction, SecurityConfig
from myrm_agent_harness.core.security.tool_registry import (
    DYNAMICALLY_RESOLVED_TOOL_NAMES,
    EXPLICIT_MCP_FALLBACK_TOOLS,
    SafetyMetadata,
    declare_external_tool,
    external_tools,
    resolve_permission_type,
    resolve_safety_metadata,
)

ALLOW, ASK = PermissionAction.ALLOW, PermissionAction.ASK

READ_ONLY = SafetyMetadata(is_read_only=True, is_concurrent_safe=True, is_idempotent=True)
PROBE = "probe_navigation_tool"


@pytest.fixture(autouse=True)
def _isolated_declarations(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(external_tools, "_DECLARATIONS", {})
    yield


def _decision(tool_name: str, config: SecurityConfig) -> PermissionAction:
    args: dict[str, object] = {"action": "resolve", "target": "main"}
    action, _reason = evaluate_tool_call(
        resolve_permission_type(tool_name, args), args, config, workspace_root="/ws", tool_name=tool_name
    )
    return action


def test_an_undeclared_tool_keeps_the_ask_baseline_and_fail_closed_safety() -> None:
    assert resolve_permission_type(PROBE) == "mcp_invoke"
    assert resolve_safety_metadata(PROBE) == SafetyMetadata()
    assert _decision(PROBE, SecurityConfig()) == ASK


def test_a_declared_tool_resolves_to_its_permission_type_and_safety_attributes() -> None:
    declare_external_tool(PROBE, "file_read", READ_ONLY)

    assert resolve_permission_type(PROBE) == "file_read"
    assert resolve_safety_metadata(PROBE) == READ_ONLY


@pytest.mark.parametrize("config", [SecurityConfig(), SecurityConfig.readonly()], ids=["default", "readonly"])
def test_a_declared_read_tool_is_allowed_without_asking(config: SecurityConfig) -> None:
    declare_external_tool(PROBE, "file_read", READ_ONLY)

    assert _decision(PROBE, config) == ALLOW


def test_a_declared_read_tool_stays_available_in_a_read_only_turn() -> None:
    names = [PROBE, "grep_tool"]
    question = "what calls parse_args?"

    kept_before, _ = derive_runtime_allowed_tools(tool_names=names, recent_human_text=question)
    declare_external_tool(PROBE, "file_read", READ_ONLY)
    kept_after, _ = derive_runtime_allowed_tools(tool_names=names, recent_human_text=question)

    assert kept_before == frozenset({"grep_tool"})
    assert kept_after is None


def test_declaring_the_same_tool_twice_with_the_same_values_is_idempotent() -> None:
    declare_external_tool(PROBE, "file_read", READ_ONLY)
    declare_external_tool(PROBE, "file_read", READ_ONLY)

    assert resolve_permission_type(PROBE) == "file_read"


def test_declaring_a_tool_with_different_values_is_rejected() -> None:
    declare_external_tool(PROBE, "file_read", READ_ONLY)

    with pytest.raises(ValueError, match="already declared"):
        declare_external_tool(PROBE, "file_write", SafetyMetadata())

    assert resolve_permission_type(PROBE) == "file_read"


@pytest.mark.parametrize("tool_name", ["file_read_tool", "web_search_tool", "mcp__server__tool", ""])
def test_a_built_in_or_mcp_tool_name_cannot_be_declared(tool_name: str) -> None:
    with pytest.raises(ValueError, match="cannot be declared"):
        declare_external_tool(tool_name, "file_read", READ_ONLY)


@pytest.mark.parametrize("tool_name", sorted(EXPLICIT_MCP_FALLBACK_TOOLS | DYNAMICALLY_RESOLVED_TOOL_NAMES))
def test_a_tool_the_resolver_governs_by_name_cannot_be_declared(tool_name: str) -> None:
    """A deliberate ask or a sub-action decision belongs to the resolver, so a declaration cannot take the name over."""
    with pytest.raises(ValueError, match="cannot be declared"):
        declare_external_tool(tool_name, "file_read", READ_ONLY)

    assert external_tools.declared_permission_type(tool_name) is None


def test_the_resolver_governed_name_sets_are_not_empty() -> None:
    assert EXPLICIT_MCP_FALLBACK_TOOLS
    assert DYNAMICALLY_RESOLVED_TOOL_NAMES


@pytest.mark.parametrize("permission_type", ["mcp_invoke", "file_raed", ""])
def test_a_permission_type_no_built_in_tool_uses_is_rejected(permission_type: str) -> None:
    with pytest.raises(ValueError, match="permission type"):
        declare_external_tool(PROBE, permission_type, READ_ONLY)

    assert resolve_permission_type(PROBE) == "mcp_invoke"
