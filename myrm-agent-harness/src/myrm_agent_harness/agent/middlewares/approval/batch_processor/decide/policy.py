"""[INPUT]
- myrm_agent_harness.agent.security.engine::evaluate_tool_call (POS: Layers 1–5 of the security architecture. Pure deterministic evaluation — no side effects, no I/O, trivially testable.)
- myrm_agent_harness.agent.security.tool_registry::resolve_permission_type / resolve_safety_metadata / get_ptc_safety_metadata (POS: Tool safety registry — re-exported from core.security.tool_registry.)
- myrm_agent_harness.agent.security.checks::check_path_policy (POS: Layers 2 and 2.5 of the permission engine's deterministic evaluation: per-call checks the engine composes with its rule lookup.)
- myrm_agent_harness.agent.security.ptc_verifier::extract_ptc_intent (POS: AST-based static analysis for PTC scripts. Extracts MCP intent and enables Fast-Path Auto-Approve for read-only tools while preventing RCE bypass.)
- myrm_agent_harness.agent.security.types::PermissionAction (POS: Security type definitions — re-exported from core.security.types.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.state::BatchContext / CallState (POS: Shared state of the decision stages in ``decide/``: the stages read the batch context, write the call state, and settle a call by writing it into the verdict lists.)

[OUTPUT]
- evaluate_policy: set a call's permission type and first verdict

[POS]
Second decision stage. The permission engine gives the first verdict; a shell call that is a PTC proxy call to an MCP
tool is narrowed by the path policy of its argument, and a read-only MCP tool, called directly or through the proxy,
is widened to ALLOW so it needs no approval prompt.
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.engine import evaluate_tool_call
from myrm_agent_harness.agent.security.tool_registry import (
    resolve_permission_type,
    resolve_safety_metadata,
)
from myrm_agent_harness.agent.security.types import PermissionAction

from .state import BatchContext, CallState


def evaluate_policy(ctx: BatchContext, call: CallState) -> None:
    """Resolve the call's permission type and write the engine's verdict, then the read-only fast paths."""
    call.permission_type = resolve_permission_type(call.tool_name, call.tool_input)
    call.action, call.reason = evaluate_tool_call(
        call.permission_type,
        call.tool_input,
        ctx.config,
        workspace_root=ctx.workspace_root,
        tool_name=call.tool_name,
    )

    if call.tool_name == "bash_code_execute_tool":
        _apply_ptc_intent(ctx, call)

    # Fast-Path Auto-Approve for read-only MCP tools (non-PTC path).
    # MCP annotations (readOnlyHint etc.) are registered into
    # _PTC_TOOL_FLAT_INDEX at session init; leverage them here so
    # read-only MCP tools skip the HITL prompt without user config.
    if call.action == PermissionAction.ASK and call.permission_type == "mcp_invoke":
        mcp_safety = resolve_safety_metadata(call.tool_name)
        if mcp_safety.is_read_only and not mcp_safety.is_open_world and not mcp_safety.is_destructive:
            call.action = PermissionAction.ALLOW
            call.reason = f"Fast-Path Auto-Approve for read-only MCP tool: {call.tool_name}"


def _apply_ptc_intent(ctx: BatchContext, call: CallState) -> None:
    """Apply the path policy and the tool's read-only annotations when the shell call is a PTC proxy call."""
    from myrm_agent_harness.agent.security.checks import check_path_policy
    from myrm_agent_harness.agent.security.ptc_verifier import (
        extract_ptc_intent,
    )
    from myrm_agent_harness.agent.security.tool_registry import (
        get_ptc_safety_metadata,
    )

    command = str(call.tool_input.get("command", ""))
    ptc_intent = extract_ptc_intent(command)
    if not ptc_intent:
        return

    skill_name, ptc_tool_name, arguments = ptc_intent
    ptc_tool_name_full = f"ptc:{skill_name}.{ptc_tool_name}"
    call.extra_ctx = {"ptc_tool_name_full": ptc_tool_name_full}

    ptc_meta = get_ptc_safety_metadata(skill_name, ptc_tool_name)
    ptc_safety = None
    if ptc_meta:
        ptc_safety, ptc_annotations = ptc_meta
        call.extra_ctx["ptc_annotations"] = ptc_annotations

    # Path Policy Enforcement for PTC
    ptc_path = str(
        arguments.get("path")
        or arguments.get("file_path")
        or arguments.get("target")
        or arguments.get("destination")
        or arguments.get("filepath")
        or ""
    )
    if ptc_path and ctx.workspace_root:
        path_action, path_reason = check_path_policy(ptc_path, ctx.config.path_policy, ctx.workspace_root)
        if path_action == PermissionAction.DENY:
            call.action = PermissionAction.DENY
            call.reason = f"PTC {path_reason}"
        elif path_action == PermissionAction.ASK and call.action != PermissionAction.DENY:
            call.action = PermissionAction.ASK
            call.reason = f"PTC {path_reason}"

    # Fast-Path Auto-Approve Logic
    if (
        call.action == PermissionAction.ASK
        and ptc_safety
        and ptc_safety.is_read_only
        and not ptc_safety.is_open_world
        and not ptc_safety.is_destructive
    ):
        call.action = PermissionAction.ALLOW
        call.reason = f"Fast-Path Auto-Approve for read-only MCP tool: {ptc_tool_name_full}"
