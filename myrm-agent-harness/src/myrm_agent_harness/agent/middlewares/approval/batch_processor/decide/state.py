"""[INPUT]
- myrm_agent_harness.agent.security.managed_approval_policy::ManagedApprovalPolicy (POS: Harness SSOT for org floor rules that constrain allowlist honor, YOLO, auto-review, and allow-always UI.)
- myrm_agent_harness.agent.security.types::PermissionAction / RecentToolCall / SecurityConfig (POS: Security type definitions — re-exported from core.security.types.)
- myrm_agent_harness.core.security.device_policy::BatchRiskAssessment (POS: Foundation layer in core/security. Zero internal dependencies on agent runtime.)

[OUTPUT]
- BatchContext: what every call of a batch is judged against
- CallState: one call's verdict and approval-card context while it moves through the stages
- Verdicts: the three result lists of a batch and the three ways a stage settles a call

[POS]
Shared state of the decision stages in ``decide/``: the stages read the batch context, write the call state, and settle a
call by writing it into the verdict lists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.security.managed_approval_policy import ManagedApprovalPolicy
from myrm_agent_harness.agent.security.types import (
    PermissionAction,
    RecentToolCall,
    SecurityConfig,
)
from myrm_agent_harness.core.security.device_policy import BatchRiskAssessment


@dataclass(frozen=True, slots=True)
class BatchContext:
    """What every call of one batch is judged against; fixed while the batch runs."""

    config: SecurityConfig
    is_cron: bool
    workspace_root: str | None
    session_key: str
    args_hashes: dict[int, str | None]
    intent_context: str | None
    recent_tool_calls: tuple[RecentToolCall, ...]
    taint_labels: frozenset[str] | None
    is_interactive: bool
    auto_mode_enabled: bool
    map_policy: ManagedApprovalPolicy
    map_honor_allowlist: Callable[[ManagedApprovalPolicy, str], bool]
    agent_primary_model: str
    batch_assessment: BatchRiskAssessment


@dataclass(slots=True)
class CallState:
    """One tool call on its way through the stages.

    ``action`` and ``reason`` are the verdict so far. ``extra_ctx`` is what the approval card shows besides the reason;
    it stays None until a stage has something to add.
    """

    idx: int
    tool_call: ToolCall
    tool_name: str
    tool_input: dict[str, object]
    permission_type: str = ""
    action: PermissionAction = PermissionAction.ASK
    reason: str = ""
    extra_ctx: dict[str, object] | None = None

    @classmethod
    def begin(cls, idx: int, tool_call: ToolCall) -> CallState:
        return cls(
            idx=idx,
            tool_call=tool_call,
            tool_name=tool_call.get("name", "unknown"),
            tool_input=tool_call.get("args", {}),
        )

    def context(self) -> dict[str, object]:
        """The approval-card context, created on first use."""
        if not self.extra_ctx:
            self.extra_ctx = {}
        return self.extra_ctx


@dataclass(slots=True)
class Verdicts:
    """The three lists a batch is sorted into; the caller's lists are appended to in place."""

    auto_approved: list[tuple[int, ToolCall]]
    auto_denied: list[tuple[int, ToolCall, str]]
    pending_approval: list[tuple[int, ToolCall, str, str, dict[str, object] | None]]

    def approve(self, call: CallState) -> None:
        self.auto_approved.append((call.idx, call.tool_call))

    def deny(self, call: CallState, message: str) -> None:
        """Refuse the call; ``message`` is the text the model reads."""
        self.auto_denied.append((call.idx, call.tool_call, message))

    def hold(self, call: CallState, reason: str) -> None:
        """Park the call for a person; ``reason`` is the line the approval card shows."""
        self.pending_approval.append((call.idx, call.tool_call, call.permission_type, reason, call.extra_ctx))
