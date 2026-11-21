"""[INPUT]
- myrm_agent_harness.agent.security.command_rules::command_text (POS: Pure helpers of ``engine.py``, of the command-egress check in ``guards/taint_tracker.py`` and of the approval stages that read a command: the engine owns the order of the layers, this module owns which tool inputs carry a command, which field of them the tool runs and what a command line means to a rule, so every judge sees the command the shell will run and no other text.)
- myrm_agent_harness.agent.security.engine::evaluate_tool_call (POS: Layers 1–5 of the security architecture. Pure deterministic evaluation — no side effects, no I/O, trivially testable.)
- myrm_agent_harness.agent.security.tool_registry::resolve_permission_type / get_ptc_safety_metadata (POS: Tool safety registry — re-exported from core.security.tool_registry.)
- myrm_agent_harness.agent.security.checks::check_path_policy (POS: Layers 2 and 2.5 of the permission engine's deterministic evaluation: per-call checks the engine composes with its rule lookup.)
- myrm_agent_harness.agent.security.ptc_verifier::extract_ptc_intent (POS: AST-based static analysis for PTC scripts. Extracts MCP intent so the path policy and the approval card see the tool a script calls.)
- myrm_agent_harness.agent.security.types::PermissionAction (POS: Security type definitions — re-exported from core.security.types.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.state::BatchContext / CallState (POS: Shared state of the decision stages in ``decide/``: the stages read the batch context, write the call state, and settle a call by writing it into the verdict lists.)

[OUTPUT]
- evaluate_policy: set a call's permission type and first verdict

[POS]
Second decision stage. The permission engine gives the first verdict; a shell call that is a PTC proxy call to an MCP
tool is narrowed by the path policy of its argument and carries the server's cautionary claims for the approval card.
Nothing here widens a verdict: a server's own statement about a tool never turns a prompt into an ALLOW.
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.command_rules import command_text
from myrm_agent_harness.agent.security.engine import evaluate_tool_call
from myrm_agent_harness.agent.security.tool_registry import resolve_permission_type
from myrm_agent_harness.agent.security.types import PermissionAction

from .state import BatchContext, CallState


def evaluate_policy(ctx: BatchContext, call: CallState) -> None:
    """Resolve the call's permission type and write the engine's verdict, narrowed for a PTC proxy call."""
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


def _apply_ptc_intent(ctx: BatchContext, call: CallState) -> None:
    """Apply the path policy and attach the server's cautionary claims when the shell call is a PTC proxy call."""
    from myrm_agent_harness.agent.security.checks import check_path_policy
    from myrm_agent_harness.agent.security.ptc_verifier import (
        extract_ptc_intent,
    )
    from myrm_agent_harness.agent.security.tool_registry import (
        get_ptc_safety_metadata,
    )

    ptc_intent = extract_ptc_intent(command_text(call.permission_type, call.tool_input))
    if not ptc_intent:
        return

    skill_name, ptc_tool_name, arguments = ptc_intent
    ptc_tool_name_full = f"ptc:{skill_name}.{ptc_tool_name}"
    call.extra_ctx = {"ptc_tool_name_full": ptc_tool_name_full}

    ptc_meta = get_ptc_safety_metadata(skill_name, ptc_tool_name)
    if ptc_meta:
        call.extra_ctx["ptc_annotations"] = ptc_meta[1]

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
