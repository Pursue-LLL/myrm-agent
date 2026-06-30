"""Unit tests for create_channel_notify_tool."""

from __future__ import annotations

import pytest

from app.channels.types.messages import MediaAttachment
from app.services.agent.outbound_notify import (
    NotifyResult,
    NotifyTarget,
    NotifyToolConfig,
    create_channel_notify_tool,
)


class FakeSender:
    def __init__(self, *, should_fail: bool = False, error: str = "") -> None:
        self._should_fail = should_fail
        self._error = error
        self.calls: list[tuple[NotifyTarget, str, tuple[MediaAttachment, ...]]] = []

    async def send(
        self,
        target: NotifyTarget,
        body: str,
        media: tuple[MediaAttachment, ...] = (),
    ) -> NotifyResult:
        self.calls.append((target, body, media))
        if self._should_fail:
            return NotifyResult(success=False, channel=target.channel, error=self._error)
        return NotifyResult(success=True, channel=target.channel)

    async def list_available_targets(self) -> list[NotifyTarget]:
        return []


@pytest.fixture
def single_target_config() -> NotifyToolConfig:
    return NotifyToolConfig(
        allowed_targets=(
            NotifyTarget(channel="telegram", recipient_id="chat_123", label="My TG"),
        ),
        rate_limit_per_session=3,
        max_body_length=100,
    )


@pytest.mark.asyncio
async def test_empty_body_rejected(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({"channel": "telegram", "target": "", "body": "   "})
    assert "empty" in result.lower()
    assert len(sender.calls) == 0


@pytest.mark.asyncio
async def test_no_targets_configured() -> None:
    config = NotifyToolConfig(allowed_targets=())
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, config)
    result = await tool.ainvoke({"channel": "telegram", "target": "", "body": "hello"})
    assert "no notification targets configured" in result.lower()


@pytest.mark.asyncio
async def test_rate_limit_enforced(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)

    for _ in range(3):
        result = await tool.ainvoke({"channel": "", "target": "", "body": "msg"})
        assert "success" in result.lower()

    result = await tool.ainvoke({"channel": "", "target": "", "body": "over limit"})
    assert "rate limit" in result.lower()
    assert len(sender.calls) == 3


@pytest.mark.asyncio
async def test_body_truncation(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    long_body = "x" * 200
    await tool.ainvoke({"channel": "", "target": "", "body": long_body})
    assert len(sender.calls) == 1
    sent_body = sender.calls[0][1]
    assert len(sent_body) <= 100 + len("\n\n[...truncated]")
    assert sent_body.endswith("[...truncated]")


@pytest.mark.asyncio
async def test_successful_send(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({"channel": "telegram", "target": "chat_123", "body": "hello"})
    assert "success" in result.lower()
    assert "telegram" in result.lower()
    assert len(sender.calls) == 1
    assert sender.calls[0][0].recipient_id == "chat_123"


@pytest.mark.asyncio
async def test_failed_send_error(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender(should_fail=True, error="connection timeout")
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({"channel": "", "target": "", "body": "hello"})
    assert "error" in result.lower()
    assert "connection timeout" in result


@pytest.mark.asyncio
async def test_target_not_found(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({"channel": "discord", "target": "", "body": "hello"})
    assert "not found" in result.lower() or "not allowed" in result.lower()
    assert "telegram:chat_123" in result
    assert len(sender.calls) == 0


@pytest.mark.asyncio
async def test_attachment_with_local_file(single_target_config: NotifyToolConfig) -> None:
    import tempfile

    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"fake pdf content")
        tmp_file = f.name

    try:
        result = await tool.ainvoke({
            "channel": "",
            "target": "",
            "body": "Report attached",
            "attachments": [tmp_file],
        })
        assert "success" in result.lower()
        assert "1 attachment" in result.lower()
        assert len(sender.calls) == 1
        _, _, media = sender.calls[0]
        assert len(media) == 1
        assert media[0].path == tmp_file
        assert media[0].media_type.value == "document"
    finally:
        import os

        os.unlink(tmp_file)


@pytest.mark.asyncio
async def test_attachment_with_url(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({
        "channel": "",
        "target": "",
        "body": "Check this image",
        "attachments": ["https://example.com/photo.png"],
    })
    assert "success" in result.lower()
    assert "1 attachment" in result.lower()
    assert len(sender.calls) == 1
    _, _, media = sender.calls[0]
    assert len(media) == 1
    assert media[0].url == "https://example.com/photo.png"
    assert media[0].media_type.value == "image"


@pytest.mark.asyncio
async def test_attachment_file_not_found(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({
        "channel": "",
        "target": "",
        "body": "Report",
        "attachments": ["/nonexistent/file.pdf"],
    })
    assert "file not found" in result.lower()
    assert len(sender.calls) == 0


@pytest.mark.asyncio
async def test_no_body_with_attachment_only(single_target_config: NotifyToolConfig) -> None:
    import tempfile

    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(b"fake image")
        tmp_file = f.name

    try:
        result = await tool.ainvoke({
            "channel": "",
            "target": "",
            "body": "",
            "attachments": [tmp_file],
        })
        assert "success" in result.lower()
    finally:
        import os

        os.unlink(tmp_file)


@pytest.mark.asyncio
async def test_empty_body_and_no_attachments_rejected(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({"channel": "", "target": "", "body": "   ", "attachments": []})
    assert "empty" in result.lower()
    assert len(sender.calls) == 0
