"""What the model reads when the completion guard holds an answer back.

The guard decides *whether* to hold an answer back; this module decides *what the model reads*: one actionable
fix per blocking reason (produce the evidence, or state exactly what was not done), the forced-finish warning
once the rejection budget is spent, and, with no reason named, the task-aware verification checklist built from
this run's tool records.

[INPUT]
- agent.middlewares.completion.completion_guard.checklist::build_checklist (POS: task-aware verification checklist)
- agent.security.guards.loop_guard::CallRecord (POS: one recorded tool call)

[OUTPUT]
- BlockReasons: why one completion attempt was held back
- render_completion_directive(): the model-facing instruction for a set of reasons

[POS]
The only place the guard's model-facing wording is defined. The directive reaches the model as a request-only
message after the held-back draft (see ``directive_middleware``), never as a tool call or a stored message.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from myrm_agent_harness.agent.middlewares.completion.completion_guard.checklist import build_checklist
from myrm_agent_harness.agent.security.guards.loop_guard import CallRecord


@dataclass(frozen=True, slots=True)
class BlockReasons:
    """Why the guard held one completion attempt back; an empty field means that check did not fire.

    ``verification`` is set when the verification checklist found the run's work unproven (never verified, failed,
    empty or stale verification), as opposed to a failure that still stands or an unfinished todo.
    """

    evidence: str = ""
    evidence_unreachable: bool = False
    deliverable_write: str = ""
    execution_claim: str = ""
    query_grounding: str = ""
    verification: bool = False
    staged_artifacts: tuple[Mapping[str, object], ...] = ()
    forced_finish: bool = False

    def names(self) -> tuple[str, ...]:
        """The checks that fired, by name; ``checklist`` when the verification checklist alone held the answer."""
        fired = (
            ("evidence_unreachable" if self.evidence_unreachable else "evidence", self.evidence),
            ("deliverable_write", self.deliverable_write),
            ("execution_claim", self.execution_claim),
            ("query_grounding", self.query_grounding),
        )
        return tuple(name for name, reason in fired if reason) or ("checklist",)


def _forced_finish_directive(reasons: BlockReasons) -> str:
    if reasons.verification:
        text = (
            "CRITICAL SYSTEM DIRECTIVE: You have failed to verify your work multiple times. "
            "You are now permitted to finish the task, but you MUST include a clear warning "
            "in your final response to the user stating that you were unable to successfully "
            "verify the changes (e.g., tests failed or were not run) and that they should "
            "manually review the work."
        )
    else:
        text = (
            "CRITICAL SYSTEM DIRECTIVE: Your answer was held back several times and its checks still do not pass. "
            "You are now permitted to finish the task, but you MUST include a clear warning "
            "in your final response to the user stating exactly what you could not complete or confirm "
            "and that they should manually review the work."
        )
    if reasons.staged_artifacts:
        staged_names = ", ".join(str(item.get("filename", "")) for item in reasons.staged_artifacts)
        text += (
            f"\nNOTICE: Unwritten deliverables were automatically staged to .myrm/staged_artifacts/ [{staged_names}]."
        )
    if reasons.execution_claim.strip():
        text += (
            "\nNOTICE: Your draft claimed work that this run's execution record does not support. "
            "The warning in your final response must state that explicitly."
        )
    for unresolved in (reasons.evidence, reasons.deliverable_write, reasons.query_grounding):
        if unresolved.strip():
            text += (
                f"\nNOTICE: Still unresolved ({unresolved.strip()}). The warning in your final response must state it."
            )
    return text


def render_completion_directive(
    reasons: BlockReasons,
    *,
    records: Sequence[CallRecord],
    workspace_root: str | None,
) -> str:
    """The instruction the model reads for one held-back completion attempt."""
    if reasons.forced_finish:
        return _forced_finish_directive(reasons)

    if reasons.evidence.strip() and reasons.evidence_unreachable:
        return (
            "CRITICAL COMPLETION CHECK: This response appears to depend on current external information, "
            "and this run has no tool that can look it up.\n"
            f"Reason: {reasons.evidence}\n"
            "Do not present the answer as verified. Revise it to say plainly that you could not check current "
            "information and that what you give comes from prior knowledge and may be out of date, then finish."
        )

    if reasons.evidence.strip():
        return (
            "CRITICAL COMPLETION CHECK: This response appears to require external evidence, "
            "but no successful evidence-gathering tools were observed in this run.\n"
            f"Reason: {reasons.evidence}\n"
            "Before finishing, run at least one successful evidence step (web_search_tool, "
            "web_fetch_tool, browser evidence tools, or MCP tools), then synthesize the answer."
        )

    if reasons.deliverable_write.strip():
        return (
            "CRITICAL COMPLETION CHECK: Deliverable write claim without tool evidence.\n"
            f"Reason: {reasons.deliverable_write}\n"
            "Before finishing, call file_write_tool or file_edit_tool to persist the file, "
            "or revise the response to remove the false write claim."
        )

    if reasons.execution_claim.strip():
        return (
            "CRITICAL COMPLETION CHECK: Completion claim without executed evidence.\n"
            f"Reason: {reasons.execution_claim}\n"
            "Two acceptable fixes: (1) perform the action now so its tool result proves it, or "
            "(2) revise the response to state exactly what was done and what was not. "
            "Evidence proves an action ran; it does not by itself prove the result is correct."
        )

    if reasons.query_grounding.strip():
        return (
            "CRITICAL COMPLETION CHECK: Entity query observation ungrounded.\n"
            f"Reason: {reasons.query_grounding}\n"
            "Before finishing, execute the appropriate query or MCP tool to retrieve verified data, "
            "or revise the response to honestly state the missing status or tool failure to the user."
        )

    checklist, _ = build_checklist(list(records), workspace_root=workspace_root)
    return checklist
