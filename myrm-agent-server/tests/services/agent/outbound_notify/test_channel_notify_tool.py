"""Unit tests for create_channel_notify_tool."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.channels.types.messages import MediaAttachment
from app.services.agent.outbound_notify import (
    NotifyResult,
    NotifyTarget,
    NotifyToolConfig,
    create_channel_notify_tool,
)

DESTINATION = "telegram:My TG"
TARGET = NotifyTarget(channel="telegram", recipient_id="chat_123", label="My TG")


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
    return NotifyToolConfig(destinations={DESTINATION: TARGET}, rate_limit_per_session=3, max_body_length=100)


@pytest.mark.asyncio
async def test_empty_body_rejected(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({"destination": DESTINATION, "body": "   "})
    assert "empty" in result.lower()
    assert len(sender.calls) == 0


def test_tool_needs_at_least_one_destination() -> None:
    with pytest.raises(ValueError, match="at least one destination"):
        create_channel_notify_tool(FakeSender(), NotifyToolConfig(destinations={}))


def test_destination_is_the_only_required_choice_and_an_enum() -> None:
    config = NotifyToolConfig(
        destinations={DESTINATION: TARGET, "slack#2": NotifyTarget(channel="slack", recipient_id="C9")},
    )
    schema = create_channel_notify_tool(FakeSender(), config).get_input_jsonschema()
    assert schema["required"] == ["destination"]
    assert set(schema["properties"]) == {"destination", "body", "attachments"}
    assert schema["properties"]["destination"]["enum"] == [DESTINATION, "slack#2"]


def test_description_tells_the_model_to_ask_when_the_destination_is_not_clear(single_target_config: NotifyToolConfig) -> None:
    description = create_channel_notify_tool(FakeSender(), single_target_config).description
    assert "not one of the destinations" in description
    assert "ask the user instead" in description


@pytest.mark.asyncio
async def test_rate_limit_enforced(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)

    for _ in range(3):
        result = await tool.ainvoke({"destination": DESTINATION, "body": "msg"})
        assert "success" in result.lower()

    result = await tool.ainvoke({"destination": DESTINATION, "body": "over limit"})
    assert "rate limit" in result.lower()
    assert len(sender.calls) == 3


@pytest.mark.asyncio
async def test_body_truncation(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    long_body = "x" * 200
    await tool.ainvoke({"destination": DESTINATION, "body": long_body})
    assert len(sender.calls) == 1
    sent_body = sender.calls[0][1]
    assert len(sent_body) <= 100 + len("\n\n[...truncated]")
    assert sent_body.endswith("[...truncated]")


@pytest.mark.asyncio
async def test_successful_send(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({"destination": DESTINATION, "body": "hello"})
    assert result == f"Notification sent successfully to {DESTINATION}."
    assert len(sender.calls) == 1
    assert sender.calls[0][0] == TARGET


@pytest.mark.asyncio
async def test_failed_send_error(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender(should_fail=True, error="connection timeout")
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({"destination": DESTINATION, "body": "hello"})
    assert "error" in result.lower()
    assert "connection timeout" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("destination", ["telegram:chat_123", "Telegram:My TG", "telegram", "My TG", ""])
async def test_destination_outside_the_configured_set_is_rejected_listing_the_choices(
    single_target_config: NotifyToolConfig, destination: str
) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    with pytest.raises(ValidationError, match=DESTINATION):
        await tool.ainvoke({"destination": destination, "body": "hello"})
    assert len(sender.calls) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [{"body": "hello"}, {"channel": "telegram", "target": "chat_123", "body": "hello"}])
async def test_call_without_a_destination_is_rejected(single_target_config: NotifyToolConfig, args: dict[str, str]) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    with pytest.raises(ValidationError, match="destination"):
        await tool.ainvoke(args)
    assert len(sender.calls) == 0


@pytest.mark.asyncio
async def test_attachment_with_local_file(single_target_config: NotifyToolConfig) -> None:
    import os
    import tempfile
    from pathlib import Path

    sender = FakeSender()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"fake pdf content")
        tmp_file = f.name

    tool = create_channel_notify_tool(
        sender,
        single_target_config,
        allowed_roots=(str(Path(tmp_file).parent),),
    )

    try:
        result = await tool.ainvoke(
            {
                "destination": DESTINATION,
                "body": "Report attached",
                "attachments": [tmp_file],
            }
        )
        assert "success" in result.lower()
        assert "1 attachment" in result.lower()
        assert len(sender.calls) == 1
        _, _, media = sender.calls[0]
        assert len(media) == 1
        assert media[0].path == tmp_file
        assert media[0].media_type.value == "document"
    finally:
        os.unlink(tmp_file)


@pytest.mark.asyncio
async def test_attachment_with_url(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke(
        {
            "destination": DESTINATION,
            "body": "Check this image",
            "attachments": ["https://example.com/photo.png"],
        }
    )
    assert "success" in result.lower()
    assert "1 attachment" in result.lower()
    assert len(sender.calls) == 1
    _, _, media = sender.calls[0]
    assert len(media) == 1
    assert media[0].url == "https://example.com/photo.png"
    assert media[0].media_type.value == "image"


@pytest.mark.asyncio
async def test_url_with_query_params_resolves_correct_type(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke(
        {
            "destination": DESTINATION,
            "body": "AI generated chart",
            "attachments": [
                "https://oaidalleapiprodscus.blob.core.windows.net/chart.png?se=2024-01-01&sp=r&sv=2023-11-03&sig=xxx"
            ],
        }
    )
    assert "success" in result.lower()
    assert len(sender.calls) == 1
    _, _, media = sender.calls[0]
    assert len(media) == 1
    assert media[0].media_type.value == "image"
    assert media[0].filename == "chart.png"


@pytest.mark.asyncio
async def test_attachment_file_not_found(single_target_config: NotifyToolConfig, tmp_path) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config, allowed_roots=(str(tmp_path),))
    missing = str(tmp_path / "missing-report.pdf")
    result = await tool.ainvoke(
        {
            "destination": DESTINATION,
            "body": "Report",
            "attachments": [missing],
        }
    )
    assert "file not found" in result.lower()
    assert len(sender.calls) == 0


@pytest.mark.asyncio
async def test_attachment_rejects_path_outside_workspace(
    single_target_config: NotifyToolConfig,
    tmp_path,
) -> None:
    import os
    import tempfile

    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config, allowed_roots=(str(tmp_path),))

    with tempfile.NamedTemporaryFile(delete=False) as outside:
        outside_path = outside.name

    try:
        result = await tool.ainvoke(
            {
                "destination": DESTINATION,
                "body": "Report",
                "attachments": [outside_path],
            }
        )
        assert "not allowed" in result.lower()
        assert len(sender.calls) == 0
    finally:
        os.unlink(outside_path)


@pytest.mark.asyncio
async def test_no_body_with_attachment_only(single_target_config: NotifyToolConfig) -> None:
    import os
    import tempfile
    from pathlib import Path

    sender = FakeSender()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(b"fake image")
        tmp_file = f.name

    tool = create_channel_notify_tool(
        sender,
        single_target_config,
        allowed_roots=(str(Path(tmp_file).parent),),
    )

    try:
        result = await tool.ainvoke(
            {
                "destination": DESTINATION,
                "body": "",
                "attachments": [tmp_file],
            }
        )
        assert "success" in result.lower()
    finally:
        os.unlink(tmp_file)


@pytest.mark.asyncio
async def test_empty_body_and_no_attachments_rejected(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({"destination": DESTINATION, "body": "   ", "attachments": []})
    assert "empty" in result.lower()
    assert len(sender.calls) == 0


@pytest.mark.asyncio
async def test_blank_attachment_entries_are_not_attachments(single_target_config: NotifyToolConfig) -> None:
    """An empty body with only blank attachment entries has nothing to send, so it is not sent as an empty message."""
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke({"destination": DESTINATION, "body": "", "attachments": ["  ", ""]})
    assert "cannot both be empty" in result
    assert len(sender.calls) == 0


@pytest.mark.asyncio
async def test_multiple_attachments(single_target_config: NotifyToolConfig) -> None:
    import os
    import tempfile
    from pathlib import Path

    sender = FakeSender()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"a,b,c")
        tmp_file = f.name

    tool = create_channel_notify_tool(
        sender,
        single_target_config,
        allowed_roots=(str(Path(tmp_file).parent),),
    )

    try:
        result = await tool.ainvoke(
            {
                "destination": DESTINATION,
                "body": "Multiple files",
                "attachments": [tmp_file, "https://example.com/logo.jpg"],
            }
        )
        assert "success" in result.lower()
        assert "2 attachment" in result.lower()
        assert len(sender.calls) == 1
        _, _, media = sender.calls[0]
        assert len(media) == 2
        assert media[0].path == tmp_file
        assert media[1].url == "https://example.com/logo.jpg"
        assert media[1].media_type.value == "image"
    finally:
        os.unlink(tmp_file)


@pytest.mark.asyncio
async def test_relative_attachment_path_auto_resolved_under_allowed_root(
    single_target_config: NotifyToolConfig,
    tmp_path: Path,
) -> None:
    sender = FakeSender()
    sub_dir = tmp_path / "reports"
    sub_dir.mkdir(parents=True, exist_ok=True)
    report_file = sub_dir / "summary.pdf"
    report_file.write_text("dummy report content")

    tool = create_channel_notify_tool(
        sender,
        single_target_config,
        allowed_roots=(str(tmp_path),),
    )

    result = await tool.ainvoke(
        {
            "destination": DESTINATION,
            "body": "Here is the report",
            "attachments": ["reports/summary.pdf"],
        }
    )
    assert "success" in result.lower()
    assert len(sender.calls) == 1
    _, _, media = sender.calls[0]
    assert len(media) == 1
    assert media[0].path == str(report_file)
    assert media[0].filename == "summary.pdf"


@pytest.mark.asyncio
async def test_empty_attachment_entry_skipped(single_target_config: NotifyToolConfig) -> None:
    sender = FakeSender()
    tool = create_channel_notify_tool(sender, single_target_config)
    result = await tool.ainvoke(
        {
            "destination": DESTINATION,
            "body": "test",
            "attachments": ["  ", "", "https://example.com/file.png"],
        }
    )
    assert "success" in result.lower()
    assert "1 attachment" in result.lower()
    assert len(sender.calls) == 1
    _, _, media = sender.calls[0]
    assert len(media) == 1


def test_factory_wiring_respects_readonly_mode() -> None:
    from app.services.agent.outbound_notify.factory_wiring import (
        append_channel_notify_tool,
    )

    tools: list = []
    targets = ({"channel": "telegram", "recipient_id": "123", "label": "TG"},)

    # When readonly is True, tool should NOT be appended
    count = append_channel_notify_tool(targets, tools, is_readonly=True)
    assert count == 0
    assert len(tools) == 0

    # When readonly is False, tool should be appended
    count = append_channel_notify_tool(targets, tools, is_readonly=False)
    assert count == 1
    assert len(tools) == 1
