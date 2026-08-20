"""Tests for finalize_channel_stream_reply deliverable-note / deep-link interplay.

Covers the deep-link failure fallback: oversized shareable deliverables must
surface as a textual note when no share button was produced, and must be
suppressed when a button exists.
"""

from __future__ import annotations

from pathlib import Path
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
    *,
    channel_budget_key: str | None = None,
    memory_settings: dict[str, object] | None = None,
    chat_history: list[object] | None = None,
    session_was_auto_reset: bool = False,
    lite_model_cfg: object | None = None,
    workspace_root: str | None = None,
) -> tuple[MagicMock, OutboundMessage]:
    """Run finalize with deep-link build mocked; return (persist_mock, reply)."""
    with (
        patch(
            "app.core.channel_bridge.agent_executor.execute_finalize.resolve_chat_workspace_root",
            new_callable=AsyncMock,
            return_value=workspace_root or "",
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
            channel_budget_key=channel_budget_key,
            memory_settings=memory_settings or {},
            lite_model_cfg=lite_model_cfg,  # type: ignore[arg-type]
            chat_history=chat_history if chat_history is not None else [object()],
            session_was_auto_reset=session_was_auto_reset,
            session_policy=SessionPolicy(),
        )
    return persist_mock, reply


@pytest.mark.asyncio
async def test_deep_link_success_suppresses_oversized_note() -> None:
    acc = StreamAccumulator()
    acc.oversized_deliverables.append(("report.pdf", "8.0 MB"))
    acc.shareable_artifacts.append(ShareableArtifact("art-1", "report.pdf", "application/pdf"))
    button = MagicMock()
    persist_mock, reply = await _finalize(acc, ((button,), frozenset({"report.pdf"})))
    persisted = persist_mock.call_args.args[1]
    assert "oversized" not in persisted
    assert "report.pdf" not in persisted
    assert reply.components == (button,)


@pytest.mark.asyncio
async def test_deep_link_success_drops_duplicate_attachment() -> None:
    """Linked artifacts get a button, so their plain attachment is removed."""
    acc = StreamAccumulator()
    acc.file_attachments.append(
        MediaAttachment(
            media_type=MediaType.DOCUMENT,
            path="/tmp/report.pdf",
            filename="report.pdf",
            mime_type="application/pdf",
        )
    )
    acc.shareable_artifacts.append(ShareableArtifact("art-1", "report.pdf", "application/pdf"))
    button = MagicMock()
    _persist_mock, reply = await _finalize(acc, ((button,), frozenset({"report.pdf"})))
    assert reply.media == ()
    assert reply.components == (button,)


@pytest.mark.asyncio
async def test_deep_link_failure_keeps_attachment() -> None:
    """When no button is produced, the plain attachment must survive."""
    acc = StreamAccumulator()
    acc.file_attachments.append(
        MediaAttachment(
            media_type=MediaType.DOCUMENT,
            path="/tmp/report.pdf",
            filename="report.pdf",
            mime_type="application/pdf",
        )
    )
    acc.shareable_artifacts.append(ShareableArtifact("art-1", "report.pdf", "application/pdf"))
    _persist_mock, reply = await _finalize(acc, ((), frozenset()))
    assert len(reply.media) == 1
    assert reply.media[0].filename == "report.pdf"
    assert reply.components == ()


@pytest.mark.asyncio
async def test_deep_link_failure_keeps_oversized_note() -> None:
    acc = StreamAccumulator()
    acc.oversized_deliverables.append(("report.pdf", "8.0 MB"))
    acc.shareable_artifacts.append(ShareableArtifact("art-1", "report.pdf", "application/pdf"))
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


@pytest.mark.asyncio
async def test_screenshot_base64_saved_to_temp_file() -> None:
    """A screenshot reported as base64 is decoded into a temp attachment."""
    import base64

    acc = StreamAccumulator()
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"fakedata").decode()
    acc.last_image_base64 = png
    acc.last_image_mime = "image/png"
    acc.chunks.append("Here is the screenshot.")

    _persist_mock, reply = await _finalize(acc, ((), frozenset()))
    assert len(reply.media) == 1
    assert reply.media[0].media_type == MediaType.IMAGE
    assert reply.media[0].filename == "screenshot.png"


@pytest.mark.asyncio
async def test_screenshot_base64_save_failure_is_graceful() -> None:
    """A corrupt base64 payload must not crash finalize."""
    acc = StreamAccumulator()
    acc.last_image_base64 = "not-a-valid-base64!!!"
    acc.last_image_mime = "image/jpeg"
    acc.chunks.append("Screenshot failed but reply continues.")

    _persist_mock, reply = await _finalize(acc, ((), frozenset()))
    assert reply.media == ()


@pytest.mark.asyncio
async def test_screenshot_url_attachment() -> None:
    """A screenshot reported as a URL becomes a URL media attachment."""
    acc = StreamAccumulator()
    acc.last_image_url = "https://example.com/shot.jpg"
    acc.last_image_mime = "image/jpeg"
    acc.chunks.append("See the screenshot.")

    _persist_mock, reply = await _finalize(acc, ((), frozenset()))
    assert len(reply.media) == 1
    assert reply.media[0].url == "https://example.com/shot.jpg"
    assert reply.media[0].filename == "screenshot.jpg"


@pytest.mark.asyncio
async def test_error_message_becomes_error_reply() -> None:
    acc = StreamAccumulator()
    acc.error_message = "tool crashed"
    _persist_mock, reply = await _finalize(acc, ((), frozenset()))
    assert "[Error] tool crashed" in reply.content


@pytest.mark.asyncio
async def test_empty_response_fallback() -> None:
    acc = StreamAccumulator()
    _persist_mock, reply = await _finalize(acc, ((), frozenset()))
    assert reply.content == "[No response generated]"


@pytest.mark.asyncio
async def test_channel_cost_recorded_when_budget_key() -> None:
    acc = StreamAccumulator()
    acc.cost_usd = 0.12
    acc.chunks.append("Done.")
    with patch(
        "app.services.budget.channel_budget.record_channel_cost",
    ) as record_mock:
        await _finalize(acc, ((), frozenset()), channel_budget_key="tg:user-1")
    record_mock.assert_called_once_with("tg:user-1", 0.12)


@pytest.mark.asyncio
async def test_auto_title_generated_for_new_chat() -> None:
    acc = StreamAccumulator()
    acc.chunks.append("First reply.")
    with patch(
        "app.core.channel_bridge.agent_executor.execute_finalize.asyncio.create_task",
    ) as create_task_mock:
        await _finalize(acc, ((), frozenset()), chat_history=[])
    create_task_mock.assert_called_once()
    assert create_task_mock.call_args.args[0].__name__ == "generate_channel_title"


@pytest.mark.asyncio
async def test_no_auto_title_for_existing_chat() -> None:
    acc = StreamAccumulator()
    acc.chunks.append("Follow-up reply.")
    with patch(
        "app.core.channel_bridge.agent_executor.execute_finalize.asyncio.create_task",
    ) as create_task_mock:
        await _finalize(acc, ((), frozenset()), chat_history=[object()])
    create_task_mock.assert_not_called()


@pytest.mark.asyncio
async def test_session_auto_reset_metadata() -> None:
    acc = StreamAccumulator()
    acc.chunks.append("Continuing after reset.")
    _persist_mock, reply = await _finalize(acc, ((), frozenset()), session_was_auto_reset=True)
    assert reply.metadata is not None
    assert "session_auto_reset" in reply.metadata


@pytest.mark.asyncio
async def test_cost_metadata_when_enabled() -> None:
    acc = StreamAccumulator()
    acc.cost_usd = 0.05
    acc.model_name = "agn-2.5"
    acc.total_tokens = 1234
    acc.chunks.append("Done.")
    _persist_mock, reply = await _finalize(
        acc,
        ((), frozenset()),
        memory_settings={"enableCostEstimation": True},
    )
    assert reply.metadata is not None
    assert reply.metadata["cost_metadata"]["cost_usd"] == 0.05


@pytest.mark.asyncio
async def test_sources_sorted_by_index_metadata() -> None:
    acc = StreamAccumulator()
    acc.sources = [
        {"index": 2, "title": "b"},
        {"index": 1, "title": "a"},
        {"index": "not-a-number", "title": "c"},
    ]
    acc.chunks.append("Sourced reply.")
    _persist_mock, reply = await _finalize(acc, ((), frozenset()))
    assert reply.metadata is not None
    titles = [s["title"] for s in reply.metadata["sources"]]  # type: ignore[typeddict-item]
    # Non-numeric index → key 0 → sorts first; numeric 1 then 2 follow.
    assert titles == ["c", "a", "b"]


@pytest.mark.asyncio
async def test_workspace_attachment_scanned_and_stripped(
    tmp_path: Path,
) -> None:
    """A real workspace file referenced in the reply becomes an attachment."""
    report = tmp_path / "report.pdf"
    report.write_bytes(b"%PDF-1.4")
    acc = StreamAccumulator()
    acc.chunks.append("Report saved to workspace/report.pdf")
    _persist_mock, reply = await _finalize(
        acc,
        ((), frozenset()),
        workspace_root=str(tmp_path),
    )
    assert len(reply.media) == 1
    assert reply.media[0].filename == "report.pdf"
    persisted = _persist_mock.call_args.args[1]
    assert "workspace/report.pdf" not in persisted


@pytest.mark.asyncio
async def test_content_and_note_lines_concatenated(tmp_path: Path) -> None:
    """Existing content plus an oversized note is concatenated with a blank line."""
    big = tmp_path / "big.bin"
    big.write_bytes(b"\x00" * 1024)
    acc = StreamAccumulator()
    acc.oversized_deliverables.append(("big.bin", "1.0 KB"))
    acc.chunks.append("Here is the result: workspace/big.bin")
    persist_mock, reply = await _finalize(
        acc,
        ((), frozenset()),
        workspace_root=str(tmp_path),
    )
    persisted = persist_mock.call_args.args[1]
    assert "Here is the result" in persisted
    assert "big.bin" in persisted
    assert "1.0 KB" in persisted
    assert "\n\n" in persisted
