"""`/memory` pending review in IM: correct/forget proposals disclose their target."""

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


async def _render_pending_list(records: list[PendingRecord], *, locale: str) -> str:
    manager = MagicMock()
    manager.list_pending = AsyncMock(return_value=records)
    host = MagicMock()
    host._bus.publish_outbound = AsyncMock()
    msg = InboundMessage(channel="test", sender_id="u1", chat_id="chat_1", content="/memory", metadata={"locale": locale})

    with (
        patch("app.services.agent.platform_config.require_platform_embedding_config", AsyncMock()),
        patch("app.core.memory.adapters.setup.create_memory_manager", AsyncMock(return_value=manager)),
    ):
        await RouterCommandsMemoryMixin._handle_memory_command(host, msg, "")

    return str(host._bus.publish_outbound.await_args.args[0].content)


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
    assert "Forgets:" in content and "User lives in Berlin" in content
    # Plain additions get no target line: exactly one line per kind of disclosure.
    assert content.count("Replaces:") == 1
    assert content.count("Forgets:") == 1


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
