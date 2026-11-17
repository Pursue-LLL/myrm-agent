"""[INPUT]
- myrm_agent_harness.agent.security.approval_flow::DEFAULT_USER_ID / get_allowlist (POS: Core component for "Always Allow" feature in Human-in-the-Loop approval system.)
- myrm_agent_harness.agent.security.audit::record_decision (POS: Security audit log — re-exported from core.security.audit.)
- myrm_agent_harness.agent.security.path_security::is_protected_instruction_file (POS: Import-path shim. Holds no logic; `core.security.path.__all__` defines exactly what this module re-exports, so the alias never widens the public API.)
- myrm_agent_harness.agent.security.types::PermissionAction (POS: Security type definitions — re-exported from core.security.types.)
- myrm_agent_harness.core.security.spend_governance::is_financial_or_spend_tool / is_irreversible_social_action (POS: Foundational Agent Commerce governance module in core/security/.)
- myrm_agent_harness.agent.security.workspace_trust.context::get_repo_command_prefixes / get_workspace_trust_level (POS: Run-scoped state holder of the workspace_trust gate. ContextVars keep the decision isolated per async task, so concurrent runs on different workspaces never observe each other's trust level. Values are populated by runtime.py from a server-injected lookup.)
- myrm_agent_harness.agent.security.workspace_trust.gate::matches_repo_command_prefix (POS: Pure predicate layer of the workspace_trust gate; no persistence and no server calls. Unknown (None) trust is treated as restricted. Path containment resolves symlinks before comparing, so a workspace symlink cannot be used to escape the trusted boundary.)
- myrm_agent_harness.agent.security.workspace_trust.types::WorkspaceTrustLevel (POS: Leaf type module of the workspace_trust gate. Frozen dataclasses and one str-Enum, so the values are hashable and safe to pass across the async run boundary. No I/O and no imports from sibling modules, which keeps this module the dependency root of the package.)
- myrm_agent_harness.agent.security.command_rules::launch_command (POS: Pure helpers of ``engine.py``, of the command-egress check in ``guards/taint_tracker.py`` and of the approval stages that read a command: the engine owns the order of the layers, this module owns which tool inputs carry a command, which field of them the tool runs and what a command line means to a rule, so every judge sees the command the shell will run and no other text.)
- myrm_agent_harness.agent.middlewares._session_context::get_agent_id / get_approval_session / get_approval_user_id (POS: Middleware session context — shared ContextVars for the middleware chain.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.state::BatchContext / CallState (POS: Shared state of the decision stages in ``decide/``: the stages read the batch context, write the call state, and settle a call by writing it into the verdict lists.)

[OUTPUT]
- apply_allowlist: turn an ASK into an ALLOW when an entry of the user's allowlist, or a command prefix a trusted
  workspace declares, covers the call

[POS]
Third decision stage. Only an ASK is looked up. A match is an entry of the user's allowlist or, for a command the
call starts in a trusted workspace, a prefix the repository declared and the user saw. Either kind of match is dropped
when a gate that "always allow" must never lift applies (batch dual insurance, financial spend, irreversible social
action, protected instruction file), and when the organization policy ignores the allowlist for the agent's model.
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.approval_flow import (
    DEFAULT_USER_ID,
    get_allowlist,
)
from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.command_rules import launch_command
from myrm_agent_harness.agent.security.path_security import (
    is_protected_instruction_file,
)
from myrm_agent_harness.agent.security.types import PermissionAction
from myrm_agent_harness.agent.security.workspace_trust.context import (
    get_repo_command_prefixes,
    get_workspace_trust_level,
)
from myrm_agent_harness.agent.security.workspace_trust.gate import matches_repo_command_prefix
from myrm_agent_harness.agent.security.workspace_trust.types import WorkspaceTrustLevel
from myrm_agent_harness.core.security.spend_governance import (
    is_financial_or_spend_tool,
    is_irreversible_social_action,
)

from .state import BatchContext, CallState


async def apply_allowlist(ctx: BatchContext, call: CallState) -> None:
    """Raise an ASK to ALLOW when an allowlist entry or a declared command prefix covers the call."""
    if call.action != PermissionAction.ASK:
        return

    from myrm_agent_harness.agent.middlewares._session_context import (
        get_agent_id,
        get_approval_session,
        get_approval_user_id,
    )

    tool_name = call.tool_name
    allowlist = get_allowlist()
    user_id = get_approval_user_id() or DEFAULT_USER_ID
    current_agent_id = get_agent_id() or None
    current_session_id = get_approval_session() or None
    await allowlist.load_user(user_id)
    effective_tool_name = str(call.extra_ctx.get("ptc_tool_name_full", tool_name)) if call.extra_ctx else tool_name
    args_hash = ctx.args_hashes.get(call.idx)

    command = launch_command(call.permission_type, call.tool_input)
    matching_allowlist_entry = allowlist.find_matching_entry(
        user_id,
        call.permission_type,
        effective_tool_name,
        args_hash,
        command=command,
        agent_id=current_agent_id,
        session_id=current_session_id,
    )
    declared_prefix_matches = matching_allowlist_entry is None and _covered_by_declared_prefix(command)
    allowlist_would_match = matching_allowlist_entry is not None or declared_prefix_matches
    if allowlist_would_match and _blocked_by_never_lifted_gate(ctx, call, effective_tool_name):
        allowlist_would_match = False

    if not ctx.map_honor_allowlist(ctx.map_policy, ctx.agent_primary_model):
        if allowlist_would_match:
            record_decision(
                tool_name,
                "MAP_ALLOWLIST_SKIPPED",
                f"org policy ignores allowlist for model {ctx.agent_primary_model}",
            )
    elif allowlist_would_match:
        call.action = PermissionAction.ALLOW
        if declared_prefix_matches:
            call.reason = "Repo-declared command prefix auto-approve"
            record_decision(tool_name, "REPO_PREFIX_AUTO_APPROVE", call.reason)
        elif matching_allowlist_entry is not None and matching_allowlist_entry.session_id is not None:
            call.reason = f"Allowlist session-scoped auto-approve: {effective_tool_name}"
            record_decision(tool_name, "ALLOWLIST_SESSION_ALLOW", call.reason)
        else:
            call.reason = f"Allowlist auto-approve: {effective_tool_name}"
            record_decision(tool_name, "ALLOWLIST_AUTO_APPROVE", call.reason)


def _covered_by_declared_prefix(command: str | None) -> bool:
    """Whether a trusted workspace declared a prefix that covers the one plain command the call starts."""
    if command is None or get_workspace_trust_level() != WorkspaceTrustLevel.TRUSTED:
        return False
    return matches_repo_command_prefix(command, get_repo_command_prefixes())


def _blocked_by_never_lifted_gate(ctx: BatchContext, call: CallState, effective_tool_name: str) -> bool:
    """Whether a gate that no allowlist entry can lift applies to the call; the first one that applies is audited."""
    tool_name, tool_input = call.tool_name, call.tool_input
    # If batch assessment marked this batch as high-risk/dual insurance, block allowlist bypass
    if ctx.batch_assessment.allow_always_blocked:
        record_decision(
            tool_name,
            "BATCH_RISK_DUAL_INSURANCE_ESCALATED",
            f"batch high-risk dual insurance blocked allowlist bypass: {effective_tool_name}",
        )
        return True
    if is_financial_or_spend_tool(tool_name, tool_input):
        record_decision(
            tool_name,
            "FINANCIAL_GATE_ALLOWLIST_BLOCKED",
            f"Financial spend tools cannot be bypassed via allowlist: {effective_tool_name}",
        )
        return True
    if is_irreversible_social_action(tool_name, tool_input):
        record_decision(
            tool_name,
            "IRREVERSIBLE_ACTION_ALLOWLIST_BLOCKED",
            f"Socially irreversible actions cannot be bypassed via allowlist: {effective_tool_name}",
        )
        return True
    if "Protected instruction file write requires human approval" in call.reason or (
        call.permission_type in ("file_write", "fs_mutation")
        and is_protected_instruction_file(
            str(tool_input.get("path", "") or tool_input.get("file_path", "") or tool_input.get("filepath", ""))
        )
    ):
        record_decision(
            tool_name,
            "PROTECTED_INSTRUCTION_ALLOWLIST_BLOCKED",
            f"Protected instruction files cannot be bypassed via allowlist: {effective_tool_name}",
        )
        return True
    return False
