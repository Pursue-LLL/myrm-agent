"""Unit tests for ChatAutoArchiveService in server chat layer.

[INPUT]
- ChatAutoArchiveService, AutoArchivePolicyConfig, ChatSessionMetadata, ArchiveEligibilityVerdict.

[OUTPUT]
- Deterministic verification of service policy updates, evaluation, and sweep execution.

[POS]
- Sub-package: myrm-agent-server.tests.services.chat
- Module: test_chat_auto_archive_service.py
"""

from typing import List

from myrm_agent_harness.agent.context_management import (
    ArchiveEligibilityVerdict,
    ArchiveExemptionReason,
    AutoArchivePolicyConfig,
    ChatSessionMetadata,
)

from app.services.chat.chat_auto_archive_service import ChatAutoArchiveService


def test_service_policy_update_and_clamping() -> None:
    """Verifies that policy updates are clamped and reflected on service instance."""
    svc = ChatAutoArchiveService()
    assert svc.policy.enabled is False

    updated = svc.update_policy(
        AutoArchivePolicyConfig(
            enabled=True,
            idle_threshold_seconds=100,  # Clamped to min (3600)
            include_user_created=True,
        )
    )
    assert updated.enabled is True
    assert updated.idle_threshold_seconds == 3600
    assert svc.policy.idle_threshold_seconds == 3600


def test_service_evaluate_session() -> None:
    """Verifies evaluation of a single session through the service facade."""
    svc = ChatAutoArchiveService(
        AutoArchivePolicyConfig(enabled=True, idle_threshold_seconds=7200)
    )
    now = 50_000.0

    session = ChatSessionMetadata(chat_id="chat-1", last_active_timestamp=now - 10_000.0)
    res = svc.evaluate_session(session, now_timestamp=now)

    assert res.verdict == ArchiveEligibilityVerdict.ELIGIBLE
    assert res.reason == ArchiveExemptionReason.NONE
    assert res.idle_duration_seconds == 10_000.0


def test_service_execute_sweep_with_callback() -> None:
    """Verifies sweep execution with actual archiving callback."""
    svc = ChatAutoArchiveService(
        AutoArchivePolicyConfig(enabled=True, idle_threshold_seconds=3600)
    )
    now = 100_000.0
    archived_list: List[str] = []

    def mock_db_archive(chat_id: str) -> bool:
        archived_list.append(chat_id)
        return True

    sessions = [
        ChatSessionMetadata(chat_id="stale-1", last_active_timestamp=now - 5000.0),
        ChatSessionMetadata(chat_id="stale-2", last_active_timestamp=now - 6000.0),
        ChatSessionMetadata(chat_id="active-1", last_active_timestamp=now - 100.0),
        ChatSessionMetadata(chat_id="pinned-1", last_active_timestamp=now - 8000.0, is_pinned=True),
    ]

    summary, results = svc.execute_sweep(
        sessions=sessions,
        now_timestamp=now,
        archive_executor=mock_db_archive,
    )

    assert summary.total_scanned == 4
    assert summary.eligible_count == 2
    assert summary.archived_count == 2
    assert archived_list == ["stale-1", "stale-2"]
    assert len(results) == 4
