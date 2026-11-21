"""[INPUT]
- myrm_agent_harness.agent.security.managed_approval_policy::ManagedApprovalPolicy (POS: Harness SSOT for org floor rules that constrain allowlist honor, YOLO, auto-review, and allow-always UI.)
- myrm_agent_harness.agent.security.types::PermissionAction / RecentToolCall / SecurityConfig (POS: Security type definitions — re-exported from core.security.types.)
- myrm_agent_harness.core.security.device_policy::BatchRiskAssessment (POS: Foundation layer in core/security. Zero internal dependencies on agent runtime.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.state::BatchContext / CallState / Verdicts (POS: Shared state of the decision stages in ``decide/``: the stages read the batch context, write the call state, and settle a call by writing it into the verdict lists.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.preflight::deny_before_policy (POS: First decision stage. Three gates that apply before any policy is read and that no rule, allowlist entry or YOLO setting lifts: a lone printable operator as a vision key name, a tool denied under untrusted ingress, and a write blocked by the read-only research lease.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.policy::evaluate_policy (POS: Second decision stage. The permission engine gives the first verdict; a shell call that is a PTC proxy call to an MCP tool is narrowed by the path policy of its argument and carries the server's cautionary claims for the approval card. Nothing here widens a verdict: a server's own statement about a tool never turns a prompt into an ALLOW.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.allowlist::apply_allowlist (POS: Third decision stage. Only an ASK is looked up. A match is an entry of the user's allowlist or, for a command the call starts in a trusted workspace, a prefix the repository declared and the user saw. Either kind of match is dropped when a gate that "always allow" must never lift applies (batch dual insurance, financial spend, irreversible social action, protected instruction file), and when the organization policy ignores the allowlist for the agent's model.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.allow_gates::regate_allowed (POS: Fourth decision stage. An ALLOW can come from the engine or the allowlist; neither may lift a socially irreversible action, a financial spend or an irreversible destructive shell command, and neither may outlast a breached denial threshold in auto mode.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.taint::find_taint_conflict / escalate_tainted (POS: Fifth decision stage, for an ALLOW only. A tool whose sink policy conflicts with what the session has ingested is not auto-approved: it goes to a person, unless auto mode's security reviewer, shown the labels and their sources, settles it.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.allow_review::settle_allowed (POS: Fifth decision stage, for an ALLOW the taint check left alone. In auto mode a delegation to an external agent and a shell command that is not trivially safe still go through the security reviewer, so a broad user ALLOW rule or a prompt-injected delegation cannot skip the review; everything else is approved here.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.hitl::settle_denied / settle_cron_ask / settle_runtime_domain / review_before_asking (POS: Last settling stages of the decision loop, for a call that is not approved: a DENY is refused, an ASK of a scheduled run is answered by its job, and an ASK of an attended run may still be approved by a session domain grant or by the security reviewer before a person is asked.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.pending::annotate_pending (POS: Last decision stage. A call that waits for a person gets the facts the card shows and the approval flow checks again on resume: risk flags, the batch's impact, a recovery hint, spend or irreversibility markers, the rollback snapshot, and the content digests of the script files the command would run.)

[OUTPUT]
- evaluate_calls: sort every tool call of a batch into approved, denied or pending

[POS]
The per-call decision loop of batch_processor. Runs the stages in order for each call; the first stage that settles a
call ends its turn, and a call no stage settles waits for a person.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.security.managed_approval_policy import ManagedApprovalPolicy
from myrm_agent_harness.agent.security.types import (
    PermissionAction,
    RecentToolCall,
    SecurityConfig,
)
from myrm_agent_harness.core.security.device_policy import BatchRiskAssessment

from .allow_gates import regate_allowed
from .allow_review import settle_allowed
from .allowlist import apply_allowlist
from .hitl import review_before_asking, settle_cron_ask, settle_denied, settle_runtime_domain
from .pending import annotate_pending
from .policy import evaluate_policy
from .preflight import deny_before_policy
from .state import BatchContext, CallState, Verdicts
from .taint import escalate_tainted, find_taint_conflict


async def evaluate_calls(
    tool_calls: list[ToolCall],
    config: SecurityConfig,
    is_cron: bool,
    workspace_root: str | None,
    session_key: str,
    args_hashes: dict[int, str | None],
    intent_context: str | None,
    recent_tool_calls: tuple[RecentToolCall, ...],
    taint_labels: frozenset[str] | None,
    is_interactive: bool,
    auto_mode_enabled: bool,
    map_policy: ManagedApprovalPolicy,
    map_honor_allowlist: Callable[[ManagedApprovalPolicy, str], bool],
    agent_primary_model: str,
    batch_assessment: BatchRiskAssessment,
    auto_approved: list[tuple[int, ToolCall]],
    auto_denied: list[tuple[int, ToolCall, str]],
    pending_approval: list[tuple[int, ToolCall, str, str, dict[str, object] | None]],
) -> tuple[
    list[tuple[int, ToolCall]],
    list[tuple[int, ToolCall, str]],
    list[tuple[int, ToolCall, str, str, dict[str, object] | None]],
]:
    """Fill the three lists with every call of the batch and return them."""
    ctx = BatchContext(
        config=config,
        is_cron=is_cron,
        workspace_root=workspace_root,
        session_key=session_key,
        args_hashes=args_hashes,
        intent_context=intent_context,
        recent_tool_calls=recent_tool_calls,
        taint_labels=taint_labels,
        is_interactive=is_interactive,
        auto_mode_enabled=auto_mode_enabled,
        map_policy=map_policy,
        map_honor_allowlist=map_honor_allowlist,
        agent_primary_model=agent_primary_model,
        batch_assessment=batch_assessment,
    )
    verdicts = Verdicts(auto_approved, auto_denied, pending_approval)

    for idx, tool_call in enumerate(tool_calls):
        call = CallState.begin(idx, tool_call)

        if deny_before_policy(ctx, verdicts, call):
            continue

        evaluate_policy(ctx, call)
        await apply_allowlist(ctx, call)
        regate_allowed(ctx, call)

        if call.action == PermissionAction.ALLOW:
            taint_conflict = find_taint_conflict(ctx, call)
            if not taint_conflict:
                await settle_allowed(ctx, verdicts, call)
                continue
            if await escalate_tainted(ctx, verdicts, call, taint_conflict):
                continue

        if call.action == PermissionAction.DENY:
            settle_denied(ctx, verdicts, call)
            continue

        if ctx.is_cron:
            settle_cron_ask(ctx, verdicts, call)
            continue

        if settle_runtime_domain(ctx, verdicts, call):
            continue

        if await review_before_asking(ctx, verdicts, call):
            continue

        annotate_pending(ctx, call)
        verdicts.hold(call, call.reason)

    return auto_approved, auto_denied, pending_approval
