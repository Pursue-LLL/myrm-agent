"""Tests for finalize_channel_stream_reply deliverable-note / deep-link interplay.

Covers the deep-link failure fallback: oversized shareable deliverables must
surface as a textual note when no share button was produced, and must be
suppressed when a button exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)
from app.core.channel_bridge.config_parsers import SessionPolicy
from app.core.channel_bridge.executor_helpers import (
    ShareableArtifact,
    StreamAccumulator,
)


def _make_message() -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="hi",
        sent_timezone="UTC",
        metadata={"platform_locale": "en"},
    )


async def _finalize(
    acc: StreamAccumulator,
    build_result: tuple[tuple, frozenset],
) -> tuple[MagicMock, OutboundMessage]:
    """Run finalize with deep-link build mocked; return (persist_mock, reply)."""
    with (
        patch(
            "app.core.channel_bridge.agent_executor.execute_finalize.resolve_chat_workspace_root",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch(
            "app.core.channel_bridge.agent_executor.execute_finalize.build_artifact_deep_links",
            new_callable=AsyncMock,
            return_value=build_result,
        ),
        patch(
            "app.core.channel_bridge.agent_executor.execute_finalize.persist_assistant_message",
        ) as persist_mock,
    ):
        from app.core.channel_bridge.agent_executor.execute_finalize import (
            finalize_channel_stream_reply,
        )

        reply, _tmp_paths = await finalize_channel_stream_reply(
            _make_message(),
            acc=acc,
            chat_id="chat-1",
            channel_budget_key=None,
            memory_settings={},
            lite_model_cfg=None,
            chat_history=[object()],
            session_was_auto_reset=False,
            session_policy=SessionPolicy(),
        )
    return persist_mock, reply


@pytest.mark.asyncio
async def test_deep_link_success_suppresses_oversized_note() -> None:
    acc = StreamAccumulator()
    acc.oversized_deliverables.append(("report.pdf", "8.0 MB"))
    acc.shareable_artifacts.append(
        ShareableArtifact("art-1", "report.pdf", "application/pdf")
    )
    button = MagicMock()
    persist_mock, reply = await _finalize(acc, ((button,), frozenset({"report.pdf"})))
    persisted = persist_mock.call_args.args[1]
    assert "oversized" not in persisted
    assert "report.pdf" not in persisted
    assert reply.components == (button,)


@pytest.mark.asyncio
async def test_deep_link_failure_keeps_oversized_note() -> None:
    acc = StreamAccumulator()
    acc.oversized_deliverables.append(("report.pdf", "8.0 MB"))
    acc.shareable_artifacts.append(
        ShareableArtifact("art-1", "report.pdf", "application/pdf")
    )
    persist_mock, reply = await _finalize(acc, ((), frozenset()))
    persisted = persist_mock.call_args.args[1]
    assert "8.0 MB" in persisted
    assert "report.pdf" in persisted
    assert reply.components == ()


@pytest.mark.asyncio
async def test_compressed_note_always_kept() -> None:
    """Compression notes are unrelated to deep links and must never be filtered."""
    acc = StreamAccumulator()
    acc.compressed_deliverables.append(("photo.png", "6.0 MB"))
    persist_mock, reply = await _finalize(acc, ((), frozenset()))
    persisted = persist_mock.call_args.args[1]
    assert "6.0 MB" in persisted
    assert "photo.png" in persisted
    assert reply.components == ()


@pytest.mark.asyncio
async def test_empty_content_with_button_uses_deliverable_text() -> None:
    """Empty content with a deep-link button must not fall back to '[No response generated]'."""
    acc = StreamAccumulator()
    button = MagicMock()
    persist_mock, reply = await _finalize(acc, ((button,), frozenset()))
    persisted = persist_mock.call_args.args[1]
    assert persisted == "Deliverable attached."
    assert reply.components == (button,)


@pytest.mark.asyncio
async def test_empty_content_with_plain_attachment_uses_deliverable_text() -> None:
    """Empty content with a plain IM attachment (no button) also gets the deliverable message."""
    acc = StreamAccumulator()
    acc.file_attachments.append(
        MediaAttachment(
            media_type=MediaType.IMAGE,
            path="/tmp/chart.jpg",
            filename="chart.jpg",
            mime_type="image/jpeg",
        )
    )
    persist_mock, reply = await _finalize(acc, ((), frozenset()))
    persisted = persist_mock.call_args.args[1]
    assert persisted == "Deliverable attached."
    assert reply.components == ()
