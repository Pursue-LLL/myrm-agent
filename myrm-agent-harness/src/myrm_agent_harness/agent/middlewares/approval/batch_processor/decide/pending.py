"""[INPUT]
- myrm_agent_harness.agent.security.approval_reason::is_human_only / is_protected_instruction_write (POS: The seam between the engine, which writes a reason once in English, and the cards (web, channel), which word the same decision in the viewer's language. The code is read by whoever renders the card; the text is never parsed. The same code tells the automatic approvers (YOLO mode, the AI security reviewer, an approval expiry) and the allowlist which asks are not theirs to answer, and the approval stages which ask is a write to an instruction file.)
- myrm_agent_harness.agent.security.audit::record_decision (POS: Security audit log — re-exported from core.security.audit.)
- myrm_agent_harness.agent.security.command_rules::command_text (POS: Pure helpers of ``engine.py``, of the command-egress check in ``guards/taint_tracker.py`` and of the approval stages that read a command: the engine owns the order of the layers, this module owns which tool inputs carry a command, which field of them the tool runs and what a command line means to a rule, so every judge sees the command the shell will run and no other text.)
- myrm_agent_harness.agent.middlewares.approval._allow_always::protected_instruction_file_target (POS: The allow-always half of applying an approval decision, kept apart from the decision branches so the guard list that decides what may be remembered reads in one place. The pending-approval annotation reads the same ``protected_instruction_file_target``, so a card hides "Allow Always" exactly when this guard would refuse it.)
- myrm_agent_harness.core.security.remote_ops_ledger::derive_recovery_hint (POS: Foundation layer in core/security. Zero agent-internal dependencies.)
- myrm_agent_harness.core.security.spend_governance::compute_action_digest / compute_script_content_hash / extract_script_file_target / is_financial_or_spend_tool / is_irreversible_social_action / parse_spend_amount (POS: Foundational Agent Commerce governance module in core/security/.)
- myrm_agent_harness.toolkits.code_execution.security.ast_parser::is_destructive_shell_tool_call (POS: Shell execution security: AST semantic parsing and capability boundary gating.)
- myrm_agent_harness.agent.security.script_operand_verifier::compute_file_content_digest / extract_script_file_operand (POS: Security gate preventing Time-of-Check to Time-of-Use (TOCTOU) attacks on mutable script operands. Protects human-in-the-loop approvals so executing scripts cannot drift after operator review (CVE-2026-32921).)
- myrm_agent_harness.agent.middlewares.approval.batch_processor._workspace_snapshot::pre_destructive_snapshot_id (POS: A destructive command waits for the user's approval with a rollback point; the decision loop and the YOLO branch both take it through this helper.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.state::BatchContext / CallState (POS: Shared state of the decision stages in ``decide/``: the stages read the batch context, write the call state, and settle a call by writing it into the verdict lists.)

[OUTPUT]
- annotate_pending: fill the approval-card context of a call that waits for a person

[POS]
Last decision stage. A call that waits for a person gets the facts the card shows and the approval flow checks again on
resume: risk flags, the batch's impact, a recovery hint, spend or irreversibility markers, the rollback snapshot, and
the content digests of the script files the command would run. A write to an instruction file is recognised by the
engine's code; a tool the engine cannot classify is judged by the file it names, and only when the tool is not read-only.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.security.approval_reason import is_human_only, is_protected_instruction_write
from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.command_rules import command_text
from myrm_agent_harness.core.security.remote_ops_ledger import derive_recovery_hint
from myrm_agent_harness.core.security.spend_governance import (
    compute_action_digest,
    compute_script_content_hash,
    extract_script_file_target,
    is_financial_or_spend_tool,
    is_irreversible_social_action,
    parse_spend_amount,
)
from myrm_agent_harness.toolkits.code_execution.security.ast_parser import (
    is_destructive_shell_tool_call,
)

from ..._allow_always import protected_instruction_file_target
from .._workspace_snapshot import pre_destructive_snapshot_id
from .state import BatchContext, CallState

logger = logging.getLogger(__name__)


def annotate_pending(ctx: BatchContext, call: CallState) -> None:
    """Write everything the approval card and the resume check need into the call's context."""
    if call.reason.startswith("Shell threat"):
        call.context()["high_risk"] = True

    _annotate_batch_risk(ctx, call)

    recovery_hint = derive_recovery_hint(call.tool_name, call.tool_input)
    if recovery_hint:
        call.context()["recovery_hint"] = recovery_hint.recovery_command or recovery_hint.description

    _annotate_spend_or_social(call)
    _annotate_destructive(call)
    _annotate_protected_instruction(call)
    _annotate_human_only(call)
    _annotate_script_digests(ctx, call)


def _annotate_batch_risk(ctx: BatchContext, call: CallState) -> None:
    assessment = ctx.batch_assessment
    if not assessment.is_high_risk:
        return
    extra_ctx = call.context()
    extra_ctx["high_risk"] = True
    extra_ctx["hide_allow_always"] = True
    if assessment.requires_dual_insurance:
        extra_ctx["requires_dual_insurance"] = True
    if assessment.reasons:
        extra_ctx["batch_impact_summary"] = {
            "batch_size": assessment.batch_size,
            "mutating_count": assessment.mutating_count,
            "reasons": list(assessment.reasons),
            "impacted_targets": list(assessment.impacted_targets[:10]),
        }


def _annotate_spend_or_social(call: CallState) -> None:
    tool_name, tool_input = call.tool_name, call.tool_input
    if is_financial_or_spend_tool(tool_name, tool_input):
        extra_ctx = call.context()
        amt, cur = parse_spend_amount(tool_input)
        extra_ctx["is_spend"] = True
        extra_ctx["spend_amount"] = amt
        extra_ctx["spend_currency"] = cur
        extra_ctx["action_digest"] = compute_action_digest(tool_name, tool_input)
        extra_ctx["high_risk"] = True
        extra_ctx["hide_allow_always"] = True
    elif is_irreversible_social_action(tool_name, tool_input):
        extra_ctx = call.context()
        extra_ctx["is_irreversible"] = True
        extra_ctx["socially_irreversible"] = True
        extra_ctx["high_risk"] = True
        extra_ctx["hide_allow_always"] = True


def _annotate_destructive(call: CallState) -> None:
    is_destr, _destr_reason, blast_info = is_destructive_shell_tool_call(call.tool_name, call.tool_input)
    if not is_destr:
        return
    extra_ctx = call.context()
    extra_ctx["is_irreversible"] = True
    extra_ctx["irreversible_destructive"] = True
    extra_ctx["blast_radius"] = blast_info
    extra_ctx["high_risk"] = True
    extra_ctx["hide_allow_always"] = True
    if snapshot_id := pre_destructive_snapshot_id():
        extra_ctx["snapshot_id"] = snapshot_id


def _protected_instruction_target(call: CallState) -> str | None:
    """The protected instruction file the call writes: the engine's coded ask, else a file argument of a tool it cannot classify."""
    if is_protected_instruction_write(call.reason):
        return call.reason.subject
    return protected_instruction_file_target(call.tool_name, call.tool_input)


def _annotate_protected_instruction(call: CallState) -> None:
    target = _protected_instruction_target(call)
    if target is None:
        return
    extra_ctx = call.context()
    extra_ctx["protected_instruction"] = True
    extra_ctx["hide_allow_always"] = True
    extra_ctx["high_risk"] = True
    record_decision(
        call.tool_name,
        "PROTECTED_INSTRUCTION_ATTEMPT",
        f"Attempted mutation of protected instruction file: {target}",
    )
    logger.warning(
        "[PROTECTED_INSTRUCTION] Gate triggered for %s (file=%s): hide_allow_always enforced",
        call.tool_name,
        target,
    )


def _annotate_human_only(call: CallState) -> None:
    """A write only a person may answer is never offered as "Allow Always", whatever paths the batch names."""
    if is_human_only(call.reason):
        extra_ctx = call.context()
        extra_ctx["high_risk"] = True
        extra_ctx["hide_allow_always"] = True


def _annotate_script_digests(ctx: BatchContext, call: CallState) -> None:
    """Pin the script file a command runs, so the resume check refuses it if the file changed after the approval."""
    tool_name, tool_input = call.tool_name, call.tool_input
    script_target = extract_script_file_target(tool_name, tool_input)
    if script_target:
        script_hash = compute_script_content_hash(script_target)
        if script_hash:
            extra_ctx = call.context()
            extra_ctx["script_target"] = script_target
            extra_ctx["script_content_hash"] = script_hash
            extra_ctx["high_risk"] = True

    # TOCTOU Defense: extract mutable script operand and compute content digest (CVE-2026-32921)
    command = command_text(call.permission_type, tool_input)
    if command:
        from myrm_agent_harness.agent.security.script_operand_verifier import (
            compute_file_content_digest,
            extract_script_file_operand,
        )

        script_path = extract_script_file_operand(command, workspace_root=ctx.workspace_root)
        if script_path:
            script_digest = compute_file_content_digest(script_path)
            if script_digest:
                extra_ctx = call.context()
                extra_ctx["script_operand_path"] = script_path
                extra_ctx["script_operand_hash"] = script_digest
                extra_ctx["hide_allow_always"] = True
                logger.info(
                    "[SCRIPT_OPERAND] Snapshotted script operand for %s: path=%s, sha256=%s",
                    tool_name,
                    script_path,
                    script_digest[:12],
                )
