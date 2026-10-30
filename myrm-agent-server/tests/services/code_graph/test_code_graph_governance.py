"""How code_graph_tool is governed: permission type, safety attributes and the skill permission it needs.

[INPUT]
- app.services.code_graph.agent_tool (POS: SKILL_NAME of the skill whose enablement mounts the tool)
- app.ai_agents.general_agent.tools._tool_layer_bootstrap (POS: declares the tool's permission type and safety attributes)
- myrm_agent_harness: permission engine, per-turn tool gate and skill boundary guardrail

[OUTPUT]
- pytest suite proving the tool is a workspace read: it asks for nothing under the default and read-only profiles,
  stays available in a read-only turn, and passes the skill boundary exactly when its skill holds ``file_read``.

[POS]
myrm-agent-server/tests/services/code_graph/test_code_graph_governance.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.middlewares.guardrails import SkillBoundaryProvider
from myrm_agent_harness.agent.middlewares.guardrails.core import GuardrailRequest
from myrm_agent_harness.agent.middlewares.tooling._runtime_tool_governance import derive_runtime_allowed_tools
from myrm_agent_harness.agent.security.engine import evaluate_tool_call
from myrm_agent_harness.agent.security.types import PermissionAction, SecurityConfig
from myrm_agent_harness.api.skills import parse_skill_frontmatter
from myrm_agent_harness.backends.skills import SkillPermission, check_permission_for_tool_call
from myrm_agent_harness.core.security.tool_registry import resolve_permission_type, resolve_safety_metadata

from app.ai_agents.general_agent.tools._tool_layer_bootstrap import register_server_tools
from app.services.code_graph.agent_tool import SKILL_NAME

TOOL = "code_graph_tool"
ARGS: dict[str, object] = {"action": "callers", "query": "parse_args"}
_SKILL_MD = Path(__file__).resolve().parents[3] / "assets" / "prebuilt_skills" / SKILL_NAME / "SKILL.md"


def _loaded_skill() -> SimpleNamespace:
    return SimpleNamespace(name=SKILL_NAME, storage_skill_id=None)


def _boundary_allows(granted: set[SkillPermission]) -> bool:
    async def checker(_skill_id: str, permission_type: str, _operation: str) -> tuple[bool, str]:
        return check_permission_for_tool_call(permission_type, granted)

    provider = SkillBoundaryProvider(permission_checker=checker)
    request = GuardrailRequest(tool_name=TOOL, tool_input=ARGS)
    with patch("myrm_agent_harness.agent.skill_agent.context.get_loaded_skills", return_value=[_loaded_skill()]):
        return asyncio.run(provider.aevaluate(request)).allow


def test_the_tool_is_governed_as_a_read_of_the_workspace() -> None:
    register_server_tools()

    safety = resolve_safety_metadata(TOOL)

    assert resolve_permission_type(TOOL, ARGS) == "file_read"
    assert (safety.is_read_only, safety.is_concurrent_safe, safety.is_idempotent) == (True, True, True)
    assert not safety.is_destructive


@pytest.mark.parametrize("config", [SecurityConfig(), SecurityConfig.readonly()], ids=["default", "readonly"])
def test_a_call_needs_no_approval(config: SecurityConfig) -> None:
    action, _reason = evaluate_tool_call(
        resolve_permission_type(TOOL, ARGS), ARGS, config, workspace_root="/workspace", tool_name=TOOL
    )

    assert action == PermissionAction.ALLOW


@pytest.mark.parametrize("config", [SecurityConfig(), SecurityConfig.readonly()], ids=["default", "readonly"])
@pytest.mark.parametrize(
    "query",
    ["Settings.key", "config.env", "app.config.env", "app.core.db", "../outside.py", "pkg.module.pem"],
)
def test_a_symbol_name_that_looks_like_a_sensitive_file_is_not_checked_as_a_path(query: str, config: SecurityConfig) -> None:
    """The query names a symbol, so it must not share an argument name the engine reads as a file path."""
    args: dict[str, object] = {"action": "callers", "query": query}

    action, _reason = evaluate_tool_call(
        resolve_permission_type(TOOL, args), args, config, workspace_root="/workspace", tool_name=TOOL
    )

    assert action == PermissionAction.ALLOW


def test_the_tool_stays_available_when_the_user_only_asks_a_question() -> None:
    allowed, _reasons = derive_runtime_allowed_tools(tool_names=[TOOL, "grep_tool"], recent_human_text="what calls parse_args?")

    assert allowed is None


def test_the_skill_declares_the_file_permission_its_tool_and_steps_need() -> None:
    frontmatter = parse_skill_frontmatter(_SKILL_MD.read_text(encoding="utf-8"), SKILL_NAME)

    assert frontmatter.required_permissions == [SkillPermission.FILE_READ]


def test_the_skill_boundary_lets_the_tool_through_once_the_skill_holds_file_read() -> None:
    assert _boundary_allows({SkillPermission.FILE_READ})
    assert not _boundary_allows(set())
