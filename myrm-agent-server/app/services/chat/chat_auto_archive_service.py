"""Account-wide idle chat auto-archive service.

[INPUT]
- myrm_agent_harness.agent.context_management: AccountWideIdleChatAutoArchivePolicySuite,
  AutoArchivePolicyConfig, ChatSessionMetadata, ArchiveEvaluationResult, ArchiveSweepSummary.

[OUTPUT]
- ChatAutoArchiveService: Business service for policy persistence and sweep orchestration.

[POS]
- Service layer: myrm-agent-server.app.services.chat
- Module: chat_auto_archive_service.py
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Sequence

from myrm_agent_harness.agent.context_management import (
    AccountWideIdleChatAutoArchivePolicySuite,
    ArchiveEligibilityVerdict,
    ArchiveEvaluationResult,
    ArchiveSweepSummary,
    AutoArchivePolicyConfig,
    ChatSessionMetadata,
)

logger = logging.getLogger(__name__)


class ChatAutoArchiveService:
    """Manages account-wide auto-archive policies and executes background session sweeps."""

    def __init__(self, policy: AutoArchivePolicyConfig | None = None) -> None:
        self._suite = AccountWideIdleChatAutoArchivePolicySuite(policy)

    @property
    def policy(self) -> AutoArchivePolicyConfig:
        """Returns the currently active archive policy."""
        return self._suite.config

    def update_policy(self, new_policy: AutoArchivePolicyConfig) -> AutoArchivePolicyConfig:
        """Updates and clamps account-wide archive policy configuration."""
        sanitized = self._suite.clamp_policy(new_policy)
        self._suite = AccountWideIdleChatAutoArchivePolicySuite(sanitized)
        logger.info(
            "Updated auto-archive policy: enabled=%s, threshold=%ds, include_user_created=%s",
            sanitized.enabled,
            sanitized.idle_threshold_seconds,
            sanitized.include_user_created,
        )
        return sanitized

    def evaluate_session(
        self, session: ChatSessionMetadata, now_timestamp: float | None = None
    ) -> ArchiveEvaluationResult:
        """Evaluates a single session against current policy without side effects."""
        return self._suite.evaluate_session(session, now_timestamp)

    def execute_sweep(
        self,
        sessions: Sequence[ChatSessionMetadata],
        now_timestamp: float | None = None,
        archive_executor: Callable[[str], bool] | None = None,
    ) -> tuple[ArchiveSweepSummary, tuple[ArchiveEvaluationResult, ...]]:
        """Sweeps candidate sessions, executing persistent soft-archiving on eligible ones.

        Args:
            sessions: Snapshot list of sessions to evaluate.
            now_timestamp: Reference unix timestamp (defaults to current time).
            archive_executor: Optional callback to perform database or storage archive transition.

        Returns:
            Tuple of (ArchiveSweepSummary, tuple of all evaluation results).
        """
        ref_time = now_timestamp if now_timestamp is not None else time.time()
        summary, results = self._suite.run_sweep(
            sessions=sessions,
            now_timestamp=ref_time,
            archive_action=archive_executor,
        )

        logger.info(
            "Completed chat auto-archive sweep: scanned=%d, eligible=%d, archived=%d, elapsed=%.3fs",
            summary.total_scanned,
            summary.eligible_count,
            summary.archived_count,
            summary.elapsed_seconds,
        )
        return summary, results
