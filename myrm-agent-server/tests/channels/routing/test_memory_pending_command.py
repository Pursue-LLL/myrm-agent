"""`/memory` pending review in IM: proposals disclose their target and approvals go through the audited review service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.types import (
    MemoryType,
    PendingRecord,
    PendingResolutionAction,
)

from app.channels.routing.commands.router_commands_memory import RouterCommandsMemoryMixin
from app.channels.types.messages import InboundMessage
from app.services.memory.operations.pending_review import PendingReviewSource


def _record(
    pending_id: str,
    content: str,
    *,
    action: PendingResolutionAction = PendingResolutionAction.STORE,
    target_content: str | None = None,
) -> PendingRecord:
    return PendingRecord(
        id=pending_id,
        memory_type=MemoryType.SEMANTIC,
        content=content,
        resolution_action=action,
        target_memory_id="mem-old" if target_content else None,
        target_content=target_content,
    )


async def _run_memory_command(records: list[PendingRecord], raw_args: str, *, locale: str = "en") -> tuple[str, MagicMock]:
    manager = MagicMock()
    manager.list_pending = AsyncMock(return_value=records)
    host = MagicMock()
    host._bus.publish_outbound = AsyncMock()
    msg = InboundMessage(channel="test", sender_id="u1", chat_id="chat_1", content="/memory", metadata={"locale": locale})

    with (
        patch("app.services.agent.platform_config.require_platform_embedding_config", AsyncMock()),
        patch("app.core.memory.adapters.setup.create_memory_manager", AsyncMock(return_value=manager)),
    ):
        await RouterCommandsMemoryMixin._handle_memory_command(host, msg, raw_args)

    return str(host._bus.publish_outbound.await_args.args[0].content), manager


async def _render_pending_list(records: list[PendingRecord], *, locale: str) -> str:
    content, _ = await _run_memory_command(records, "", locale=locale)
    return content


@pytest.mark.asyncio
async def test_pending_list_discloses_correct_and_forget_targets() -> None:
    records = [
        _record("aaaaaaaa-1", "User now works at Google"),
        _record(
            "bbbbbbbb-2",
            "User works at Google",
            action=PendingResolutionAction.CORRECT,
            target_content="User works at ByteDance",
        ),
        _record(
            "cccccccc-3",
            "User no longer lives in Berlin",
            action=PendingResolutionAction.DELETE,
            target_content="User lives in Berlin",
        ),
    ]

    content = await _render_pending_list(records, locale="en")

    assert "Replaces:" in content and "User works at ByteDance" in content
    assert "Moves to trash:" in content and "User lives in Berlin" in content
    # Plain additions get no target line: exactly one line per kind of disclosure.
    assert content.count("Replaces:") == 1
    assert content.count("Moves to trash:") == 1


@pytest.mark.asyncio
async def test_pending_list_target_lines_are_localised() -> None:
    record = _record(
        "bbbbbbbb-2",
        "User works at Google",
        action=PendingResolutionAction.CORRECT,
        target_content="User works at ByteDance",
    )

    content = await _render_pending_list([record], locale="zh-CN")

    assert "将替换：" in content
    assert "Replaces:" not in content


@pytest.mark.asyncio
async def test_approve_by_short_id_goes_through_the_audited_review_service() -> None:
    records = [_record("aaaaaaaa-1", "User now works at Google")]

    with (
        patch("app.services.memory.operations.pending_review.approve_pending", AsyncMock()) as approve,
        patch("app.services.memory.operations.pending_review.reject_pending", AsyncMock()) as reject,
    ):
        content, manager = await _run_memory_command(records, "approve aaaaaaaa")

    approve.assert_awaited_once_with(manager, "aaaaaaaa-1", source=PendingReviewSource.CHANNEL)
    reject.assert_not_awaited()
    assert "aaaaaaaa" in content


@pytest.mark.asyncio
async def test_reject_and_approve_all_use_the_review_service() -> None:
    records = [_record("aaaaaaaa-1", "one"), _record("bbbbbbbb-2", "two")]

    with (
        patch("app.services.memory.operations.pending_review.approve_pending", AsyncMock()) as approve,
        patch("app.services.memory.operations.pending_review.reject_pending", AsyncMock()) as reject,
    ):
        _, manager = await _run_memory_command(records, "reject bbbbbbbb")
        await _run_memory_command(records, "approve all")

    reject.assert_awaited_once_with(manager, "bbbbbbbb-2", source=PendingReviewSource.CHANNEL)
    assert [call.args[1] for call in approve.await_args_list] == ["aaaaaaaa-1", "bbbbbbbb-2"]
