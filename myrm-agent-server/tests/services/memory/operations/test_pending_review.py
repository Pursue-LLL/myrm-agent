"""Tests for the approval-queue review service and its audit trail."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.memory import MemoryNotFoundError, MemoryOperationKind
from myrm_agent_harness.toolkits.memory.types import MemoryType, PendingRecord, PendingResolutionAction

from app.services.memory.operations import pending_review as review
from app.services.memory.operations.pending_review import PendingReviewSource
from app.services.skills.experience_ledger import ExperienceEventType

_MODULE = "app.services.memory.operations.pending_review"


def _record(
    pending_id: str = "p-1",
    *,
    action: PendingResolutionAction = PendingResolutionAction.STORE,
    status: str = "pending",
) -> PendingRecord:
    return PendingRecord(
        id=pending_id,
        memory_type=MemoryType.SEMANTIC,
        content="User now prefers Go",
        memory_data={},
        status=status,  # type: ignore[arg-type]
        resolution_action=action,
        target_memory_id="old-1" if action != PendingResolutionAction.STORE else None,
    )


def _manager(*records: PendingRecord) -> AsyncMock:
    store = {record.id: record for record in records}
    manager = AsyncMock()
    manager.get_pending = AsyncMock(side_effect=lambda pending_id: store.get(pending_id))
    manager.approve = AsyncMock(return_value=None)
    manager.reject = AsyncMock(return_value=None)
    manager._store = store
    return manager


@pytest.fixture
def ledgers():
    with (
        patch(f"{_MODULE}.record_experience_event", AsyncMock()) as experience,
        patch(f"{_MODULE}.record_pending_event", AsyncMock()) as timeline,
    ):
        yield experience, timeline


class TestApprovePending:
    @pytest.mark.asyncio
    async def test_audits_forget_proposal_with_trash_note(self, ledgers) -> None:
        experience, timeline = ledgers
        manager = _manager(_record(action=PendingResolutionAction.DELETE))

        await review.approve_pending(manager, "p-1", source=PendingReviewSource.CHANNEL)

        manager.approve.assert_awaited_once_with("p-1", edited_content=None)
        write = experience.await_args.args[0]
        assert write.event_type == ExperienceEventType.REVIEW_APPROVED
        assert write.detail["resolution_action"] == "delete"
        assert write.detail["target_memory_id"] == "old-1"
        assert write.detail["batch"] is False
        timeline_kwargs = timeline.await_args.kwargs
        assert timeline_kwargs["kind"] == MemoryOperationKind.APPROVE
        assert timeline_kwargs["source"] == PendingReviewSource.CHANNEL
        assert timeline_kwargs["memory_type"] == "semantic"
        assert "moved to trash" in timeline_kwargs["summary"]

    @pytest.mark.asyncio
    async def test_records_that_the_reviewer_edited_the_wording(self, ledgers) -> None:
        experience, _ = ledgers
        manager = _manager(_record())

        await review.approve_pending(manager, "p-1", source=PendingReviewSource.WEB_API, edited_content="User prefers Go")

        manager.approve.assert_awaited_once_with("p-1", edited_content="User prefers Go")
        assert experience.await_args.args[0].detail["edited"] is True

    @pytest.mark.asyncio
    async def test_already_resolved_record_is_not_audited_again(self, ledgers) -> None:
        experience, timeline = ledgers
        manager = _manager(_record(status="approved"))

        await review.approve_pending(manager, "p-1", source=PendingReviewSource.WEB_API)

        experience.assert_not_awaited()
        timeline.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_approval_is_not_audited_and_error_propagates(self, ledgers) -> None:
        experience, timeline = ledgers
        manager = _manager(_record())
        manager.approve = AsyncMock(side_effect=MemoryNotFoundError("gone"))

        with pytest.raises(MemoryNotFoundError):
            await review.approve_pending(manager, "p-1", source=PendingReviewSource.WEB_API)

        experience.assert_not_awaited()
        timeline.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_audit_failure_never_fails_an_applied_approval(self, ledgers) -> None:
        experience, timeline = ledgers
        experience.side_effect = RuntimeError("ledger down")
        manager = _manager(_record())

        await review.approve_pending(manager, "p-1", source=PendingReviewSource.WEB_API)

        manager.approve.assert_awaited_once()
        timeline.assert_awaited_once()


class TestRejectPending:
    @pytest.mark.asyncio
    async def test_audits_rejection(self, ledgers) -> None:
        experience, timeline = ledgers
        manager = _manager(_record())

        await review.reject_pending(manager, "p-1", source=PendingReviewSource.COMMAND_CENTER)

        manager.reject.assert_awaited_once_with("p-1")
        assert experience.await_args.args[0].event_type == ExperienceEventType.REVIEW_REJECTED
        assert timeline.await_args.kwargs["kind"] == MemoryOperationKind.REJECT
        assert timeline.await_args.kwargs["source"] == PendingReviewSource.COMMAND_CENTER
        assert "moved to trash" not in timeline.await_args.kwargs["summary"]


class TestBatchReview:
    @pytest.mark.asyncio
    async def test_batch_approve_audits_only_applied_records(self, ledgers) -> None:
        experience, timeline = ledgers
        manager = _manager(_record("p-1"), _record("p-2"))
        manager.batch_approve = AsyncMock(return_value=(1, ["p-2"]))

        result = await review.batch_approve_pending(manager, ["p-1", "p-2"], source=PendingReviewSource.WEB_API)

        assert result == (1, ["p-2"])
        assert [call.args[0].entity_id for call in experience.await_args_list] == ["p-1"]
        assert experience.await_args.args[0].detail["batch"] is True
        assert timeline.await_count == 1

    @pytest.mark.asyncio
    async def test_batch_reject_audits_only_records_that_flipped(self, ledgers) -> None:
        experience, _ = ledgers
        manager = _manager(_record("p-1"), _record("p-2"))

        async def _batch_reject(pending_ids: list[str]) -> int:
            manager._store["p-1"] = _record("p-1", status="rejected")
            return 1

        manager.batch_reject = AsyncMock(side_effect=_batch_reject)

        count = await review.batch_reject_pending(manager, ["p-1", "p-2"], source=PendingReviewSource.WEB_API)

        assert count == 1
        assert [call.args[0].entity_id for call in experience.await_args_list] == ["p-1"]

    @pytest.mark.asyncio
    async def test_unknown_ids_are_ignored_by_the_audit(self, ledgers) -> None:
        experience, _ = ledgers
        manager = _manager()
        manager.batch_approve = AsyncMock(return_value=(0, ["ghost"]))

        await review.batch_approve_pending(manager, ["ghost"], source=PendingReviewSource.WEB_API)

        experience.assert_not_awaited()
