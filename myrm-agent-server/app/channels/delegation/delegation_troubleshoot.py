"""Autonomous troubleshooting budget manager and self-healing strategy state machine.

Manages strategy retry budgets, prevents oscillation loops between competing fallback
heuristics, maps diagnostic error patterns to autonomous remediation recipes (mirror fallback,
port rebind, polyfill injection, privilege boundary adaptation), and coordinates with
delegation beacons and remote approval gates when budget is exhausted.

[INPUT]
- task_id, error_text, current_exit_code, attempted_actions
- .delegation_models::RiskLevel, ApprovalRequest

[OUTPUT]
- TroubleshootStrategyType: Enum of automated self-healing remediation strategies.
- TroubleshootDecision: Actionable decision descriptor (retry with strategy vs escalate to approval).
- TroubleshootingBudgetManager: State machine coordinating task-level troubleshooting limits.

[POS]
Domain subsystem for autonomous DevOps and long-running task self-healing in app/channels/delegation/.
"""

from __future__ import annotations

import enum
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Sequence

logger = logging.getLogger("myrm.channels.delegation.troubleshoot")


class TroubleshootStrategyType(str, enum.Enum):
    """Categorized autonomous remediation strategy types."""

    MIRROR_FALLBACK = "mirror_fallback"
    PORT_REBIND = "port_rebind"
    DEPENDENCY_PROVISION = "dependency_provision"
    PRIVILEGE_ADAPTATION = "privilege_adaptation"
    CONFIG_POLYFILL = "config_polyfill"
    RETRY_TRANSIENT = "retry_transient"
    MANUAL_APPROVAL_REQUIRED = "manual_approval_required"


@dataclass(frozen=True)
class TroubleshootAttempt:
    """Record of a single troubleshooting attempt."""

    strategy: TroubleshootStrategyType
    command_or_action: str
    error_summary: str
    attempt_timestamp: float = field(default_factory=time.time)
    strategy_hash: str = ""

    def __post_init__(self) -> None:
        if not self.strategy_hash:
            raw = f"{self.strategy.value}:{self.command_or_action}"
            computed = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
            object.__setattr__(self, "strategy_hash", computed)


@dataclass
class TroubleshootDecision:
    """Actionable decision produced by the troubleshooting budget engine."""

    should_retry: bool
    strategy: TroubleshootStrategyType
    remediation_hint: str
    remaining_budget: int
    attempt_count: int
    beacon_message: str
    requires_human_approval: bool = False
    approval_reason: str = ""


# Diagnostic matchers for automated strategy classification
_STRATEGY_CLASSIFIERS: tuple[tuple[TroubleshootStrategyType, re.Pattern[str], str], ...] = (
    (
        TroubleshootStrategyType.MIRROR_FALLBACK,
        re.compile(r"\b(?:ETIMEDOUT|ESOCKETTIMEDOUT|fetch\s+failed|Connection\s+timed\s+out|registry\.npmjs\.org)\b", re.IGNORECASE),
        "Detected network/registry timeout. Switching to domestic mirror registry (npmmirror/tsinghua/aliyun)...",
    ),
    (
        TroubleshootStrategyType.PORT_REBIND,
        re.compile(r"\b(?:EADDRINUSE|address\s+already\s+in\s+use|port\s+is\s+already\s+allocated)\b", re.IGNORECASE),
        "Detected port collision. Probing next available ephemeral port and updating bind configuration...",
    ),
    (
        TroubleshootStrategyType.DEPENDENCY_PROVISION,
        re.compile(r"\b(?:command\s+not\s+found|ModuleNotFoundError|Cannot\s+find\s+module|No\s+module\s+named)\b", re.IGNORECASE),
        "Detected missing runtime dependency. Auto-provisioning required packages/binaries...",
    ),
    (
        TroubleshootStrategyType.PRIVILEGE_ADAPTATION,
        re.compile(r"\b(?:EACCES|Permission\s+denied|trustedHosts|Invalid\s+Host\s+header)\b", re.IGNORECASE),
        "Detected privilege/host fence restriction. Adjusting non-destructive config & trusted host parameters...",
    ),
    (
        TroubleshootStrategyType.CONFIG_POLYFILL,
        re.compile(r"\b(?:426\s+Upgrade\s+Required|401\s+Unauthorized|manifest\.webmanifest|AbortSignal\.timeout)\b", re.IGNORECASE),
        "Detected protocol/proxy negotiation barrier. Generating reverse proxy and polyfill compatibility patch...",
    ),
)

# High-risk destructive action detector
_HIGH_RISK_ACTION_RE = re.compile(
    r"\b(?:rm\s+-rf\s+[/~]|drop\s+database|format\s+[a-z]:|mkfs|fdisk|chmod\s+-R\s+777\s+/)\b",
    re.IGNORECASE,
)


class TroubleshootingBudgetManager:
    """Manages autonomous error remediation budget and prevents retry oscillation."""

    def __init__(self, *, default_max_budget: int = 5) -> None:
        self._default_max_budget = default_max_budget
        self._task_budgets: dict[str, int] = {}
        self._task_history: dict[str, list[TroubleshootAttempt]] = {}

    def get_remaining_budget(self, task_id: str) -> int:
        """Get remaining retry attempts for a given task."""
        used = len(self._task_history.get(task_id, []))
        total = self._task_budgets.get(task_id, self._default_max_budget)
        return max(0, total - used)

    def set_task_budget(self, task_id: str, max_budget: int) -> None:
        """Configure explicit troubleshooting budget for a specific task."""
        self._task_budgets[task_id] = max(1, max_budget)

    def evaluate_and_consume(
        self,
        task_id: str,
        error_text: str,
        *,
        proposed_action: str = "",
        exit_code: int = 1,
    ) -> TroubleshootDecision:
        """Evaluate failure diagnostics, allocate budget, and determine remediation path.

        Args:
            task_id: Active delegated task ID.
            error_text: Distilled error text or exception trace.
            proposed_action: Optional next command/action proposed for self-healing.
            exit_code: Subprocess exit code.

        Returns:
            TroubleshootDecision with retry instructions or escalation directives.
        """
        history = self._task_history.setdefault(task_id, [])
        max_budget = self._task_budgets.get(task_id, self._default_max_budget)
        remaining = max(0, max_budget - len(history))

        # 1. Hard Security Check: Intercept high-risk destructive actions immediately
        if proposed_action and _HIGH_RISK_ACTION_RE.search(proposed_action):
            return TroubleshootDecision(
                should_retry=False,
                strategy=TroubleshootStrategyType.MANUAL_APPROVAL_REQUIRED,
                remediation_hint="Proposed remediation involves potentially destructive operations.",
                remaining_budget=remaining,
                attempt_count=len(history),
                beacon_message="High-risk command detected. Escalated for human authorization.",
                requires_human_approval=True,
                approval_reason=f"Dangerous command intercepted: {proposed_action}",
            )

        # 2. Check if troubleshooting budget is exhausted
        if remaining <= 0:
            logger.warning("Task %s exhausted troubleshooting budget (%d/%d attempts)", task_id, len(history), max_budget)
            return TroubleshootDecision(
                should_retry=False,
                strategy=TroubleshootStrategyType.MANUAL_APPROVAL_REQUIRED,
                remediation_hint="Troubleshooting budget exhausted. Escalating to user for guidance.",
                remaining_budget=0,
                attempt_count=len(history),
                beacon_message=f"Troubleshooting budget exhausted ({max_budget}/{max_budget} attempts). Awaiting instructions.",
                requires_human_approval=True,
                approval_reason=f"Exhausted {max_budget} autonomous self-healing attempts without resolution.",
            )

        # 3. Match error signatures against strategy classifiers
        selected_strategy = TroubleshootStrategyType.RETRY_TRANSIENT
        remediation_hint = "Transient error detected. Attempting idempotent retry..."

        for strat, pattern, hint in _STRATEGY_CLASSIFIERS:
            if pattern.search(error_text):
                selected_strategy = strat
                remediation_hint = hint
                break

        # 4. Prevent duplicate strategy oscillation (anti-oscillation guard)
        raw_signature = f"{selected_strategy.value}:{proposed_action or error_text[:60]}"
        strat_hash = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()[:12]

        already_tried = any(att.strategy_hash == strat_hash for att in history)
        if already_tried and selected_strategy != TroubleshootStrategyType.RETRY_TRANSIENT:
            logger.info("Task %s strategy %s already attempted, falling back to TRANSIENT retry", task_id, selected_strategy.value)
            selected_strategy = TroubleshootStrategyType.RETRY_TRANSIENT
            remediation_hint = "Previous specific remediation failed. Attempting alternative clean retry..."

        # 5. Record attempt and consume budget
        attempt = TroubleshootAttempt(
            strategy=selected_strategy,
            command_or_action=proposed_action or remediation_hint,
            error_summary=error_text[:120],
            strategy_hash=strat_hash,
        )
        history.append(attempt)
        remaining_after = max(0, max_budget - len(history))

        beacon_msg = f"[Self-Healing {len(history)}/{max_budget}] {remediation_hint}"

        return TroubleshootDecision(
            should_retry=True,
            strategy=selected_strategy,
            remediation_hint=remediation_hint,
            remaining_budget=remaining_after,
            attempt_count=len(history),
            beacon_message=beacon_msg,
            requires_human_approval=False,
        )

    def reset_task(self, task_id: str) -> None:
        """Clear troubleshooting history and reset budget for a completed/cancelled task."""
        self._task_history.pop(task_id, None)
        self._task_budgets.pop(task_id, None)
