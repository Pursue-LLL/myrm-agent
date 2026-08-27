"""Builtin tool flags resolution shared by all agent entry points.

[INPUT]
- app.services.agent.builtin_specs.builtin_tool_ids::strip_deploy_incompatible_builtin_tools (POS: 部署不兼容工具裁剪)
- app.config.computer_use_deploy::is_computer_use_deploy_supported (POS: computer_use 部署能力开关)
- app.config.external_cli_deploy::is_external_cli_deploy_supported (POS: external_cli 部署能力开关)
- app.services.agent.params.mcp_selection::coerce_tool_selections (POS: mcp tool selections 规范化)

[OUTPUT]
- BuiltinToolFlags: enabled_builtin_tools → enable_xxx 标志 TypedDict
- resolve_builtin_tool_flags: 统一映射函数（Web/Channel/Cron/Kanban/Eval/Voice 共用）

[POS]
将 `enabled_builtin_tools` 列表映射为 GeneralAgentParams 布尔标志的唯一入口，
保证所有入口工具开关一致性。
"""

from __future__ import annotations

from typing import Sequence, TypedDict

from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode


class BuiltinToolFlags(TypedDict):
    """Boolean flags derived from enabled_builtin_tools for GeneralAgentParams."""

    enable_browser: bool
    enable_computer_use: bool
    file_access_mode: FileAccessMode
    enable_shell_tools: bool
    enable_wiki: bool
    enable_kanban: bool
    enable_cron_eager: bool
    enable_answer_tool: bool
    enable_render_ui: bool
    enable_planning: bool
    enable_structured_clarify: bool
    enable_external_cli: bool
    enable_skill_market: bool
    enable_skill_manage: bool


def resolve_builtin_tool_flags(
    tools: Sequence[str],
    *,
    allow_answer_tool: bool = False,
) -> BuiltinToolFlags:
    """Map enabled_builtin_tools list to GeneralAgentParams boolean flags.

    All entry points (Web, Channel, Cron, Kanban, Eval, Voice) must use this
    function to ensure parity. Adding a new tool flag requires only a single
    change here.

    ``answer_tool`` is only mounted for Fast Search via ``allow_answer_tool=True``
    in ``converter.py``; profile opt-in is ignored.
    """
    from app.services.agent.builtin_specs.builtin_tool_ids import (
        strip_deploy_incompatible_builtin_tools,
    )

    effective_tools = strip_deploy_incompatible_builtin_tools(tools)
    if not allow_answer_tool:
        effective_tools = [tool for tool in effective_tools if tool != "answer_tool"]
    from app.config.computer_use_deploy import is_computer_use_deploy_supported
    from app.config.external_cli_deploy import is_external_cli_deploy_supported

    deploy_supports_computer_use = is_computer_use_deploy_supported()
    deploy_supports_external_cli = is_external_cli_deploy_supported()
    return BuiltinToolFlags(
        enable_browser="browser" in effective_tools,
        enable_computer_use=("computer_use" in effective_tools and deploy_supports_computer_use),
        file_access_mode=(FileAccessMode.FULL if "file_ops" in effective_tools else FileAccessMode.NONE),
        enable_shell_tools="code_execute" in effective_tools,
        enable_wiki="wiki" in effective_tools,
        enable_kanban="kanban" in effective_tools,
        enable_cron_eager="cron" in effective_tools,
        enable_answer_tool="answer_tool" in effective_tools,
        enable_render_ui="render_ui" in effective_tools,
        enable_planning="planning" in effective_tools,
        enable_structured_clarify="structured_clarify" in effective_tools,
        enable_external_cli=("external_cli" in effective_tools and deploy_supports_external_cli),
        enable_skill_market="skill_market" in effective_tools,
        enable_skill_manage="skill_manage" in effective_tools,
    )


def is_sandbox_capable_tools(
    tools: Sequence[str],
    *,
    has_sandbox_dir: bool = False,
    declared_capabilities: Sequence[str] = (),
) -> bool:
    """Check if the resolved tool set or capabilities indicate a sandbox/coding capable agent.

    Agents with code execution, file ops, external CLI, terminal access, or explicit
    sandbox directory/capabilities require strict memory write gating to avoid L3 pollution.
    """
    if has_sandbox_dir:
        return True
    if any(cap in declared_capabilities for cap in ("code_execution", "sandbox", "terminal", "coding")):
        return True
    sandbox_tool_identifiers = {"code_execute", "external_cli"}
    return any(t in sandbox_tool_identifiers for t in tools)


def coerce_str_tuple(val: object) -> tuple[str, ...]:
    """Normalize metadata list/tuple/scalar values into a tuple of strings."""
    if val is None:
        return ()
    if isinstance(val, str):
        return (val,)
    if isinstance(val, (list, tuple)):
        return tuple(str(x) for x in val)
    return (str(val),)


def coerce_tool_selections(val: object) -> dict[str, tuple[str, ...]]:
    """Normalize metadata ``mcp_tool_selections`` into {server: (tool, ...)}.

    Delegates to ``mcp_selection.coerce_tool_selections`` (canonical impl).
    Returns ``{}`` instead of ``None`` for dataclass default compatibility.
    """
    from app.services.agent.params.mcp_selection import coerce_tool_selections as _coerce

    return _coerce(val) or {}
