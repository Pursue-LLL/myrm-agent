"""A wake turn's reply goes back to the conversation its chat lives in, and only when there is one."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.types import InboundMessage
from app.core.channel_bridge.agent_executor import deliverable
from app.core.channel_bridge.wake_return import ChannelWakeReplyReturner, WakeOrigins

_MSG = InboundMessage(channel="telegram", sender_id="u1", content="research it", chat_id="room-1", metadata={"locale": "en"})


@pytest.fixture(autouse=True)
def chat_without_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    """No chat has a workspace unless a test gives it one: the lookup is a database read."""
    monkeypatch.setattr(deliverable, "resolve_chat_workspace_root", AsyncMock(return_value=None))


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """The chat's workspace, holding the report the research produced."""
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "report.pdf").write_bytes(b"%PDF-1.4 findings")
    (tmp_path / "secret.txt").write_text("outside the workspace")
    monkeypatch.setattr(deliverable, "resolve_chat_workspace_root", AsyncMock(return_value=str(root)))
    yield root


def _returner(origins: WakeOrigins, *, delivered: bool = True) -> tuple[ChannelWakeReplyReturner, AsyncMock]:
    deliver = AsyncMock(return_value=delivered)
    return ChannelWakeReplyReturner(MagicMock(deliver_followup=deliver), origins), deliver


@pytest.mark.asyncio
async def test_the_reply_is_delivered_into_the_conversation_the_chat_was_last_talked_in() -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    returner, deliver = _returner(origins)

    await returner.return_reply("chat-db-1", "The research is done.")

    deliver.assert_awaited_once()
    assert deliver.await_args is not None
    origin, reply, media = deliver.await_args.args
    assert (origin.channel, origin.chat_id, reply, media) == ("telegram", "room-1", "The research is done.", ())


@pytest.mark.asyncio
async def test_a_chat_that_was_not_started_from_a_channel_gets_nothing_sent() -> None:
    returner, deliver = _returner(WakeOrigins())

    await returner.return_reply("chat-db-1", "The research is done.")

    deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_reply_the_router_withheld_is_not_an_error() -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    returner, deliver = _returner(origins, delivered=False)

    await returner.return_reply("chat-db-1", "[SILENT]")

    deliver.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_boundary_markers_a_model_echoed_do_not_reach_the_chat() -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    returner, deliver = _returner(origins)

    await returner.return_reply(
        "chat-db-1",
        '<<<UNTRUSTED_DATA id="a1b2">>>The research is done.<<<END_UNTRUSTED_DATA>>> [[SANITIZED]]',
    )

    assert deliver.await_args is not None
    assert deliver.await_args.args[1] == "The research is done."


@pytest.mark.asyncio
async def test_a_reply_that_was_only_markers_is_not_sent() -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    returner, deliver = _returner(origins)

    await returner.return_reply("chat-db-1", "<<<TOOL_OUTPUT>>><<<END_TOOL_OUTPUT>>> [[SANITIZED]]")

    deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_workspace_file_the_reply_names_is_attached_and_its_path_left_out_of_the_text(workspace: Path) -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    returner, deliver = _returner(origins)

    await returner.return_reply("chat-db-1", "The research is done, the report is report.pdf.")

    assert deliver.await_args is not None
    _origin, content, media = deliver.await_args.args
    assert "report.pdf" not in content
    assert [(m.filename, m.path) for m in media] == [("report.pdf", str(workspace / "report.pdf"))]


@pytest.mark.asyncio
async def test_a_reply_that_is_only_a_file_name_is_sent_as_the_file_with_a_line_saying_so(workspace: Path) -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    returner, deliver = _returner(origins)

    await returner.return_reply("chat-db-1", "report.pdf")

    assert deliver.await_args is not None
    _origin, content, media = deliver.await_args.args
    assert (content, len(media)) == ("Deliverable attached.", 1)


@pytest.mark.asyncio
async def test_a_file_outside_the_workspace_is_not_attached(workspace: Path) -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    returner, deliver = _returner(origins)
    reply = "See ../secret.txt and /etc/passwd.txt for the raw data."

    await returner.return_reply("chat-db-1", reply)

    assert deliver.await_args is not None
    assert deliver.await_args.args[1:] == (reply, ())


@pytest.mark.asyncio
async def test_a_chat_without_a_workspace_gets_the_reply_as_text() -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    returner, deliver = _returner(origins)

    await returner.return_reply("chat-db-1", "The report is report.pdf.")

    assert deliver.await_args is not None
    assert deliver.await_args.args[1:] == ("The report is report.pdf.", ())


@pytest.mark.asyncio
async def test_a_scan_that_fails_still_sends_the_reply_as_text(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(deliverable, "collect_deliverable_paths_from_text", MagicMock(side_effect=OSError("disk gone")))
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    returner, deliver = _returner(origins)

    with caplog.at_level(logging.WARNING):
        await returner.return_reply("chat-db-1", "The report is report.pdf.")

    assert deliver.await_args is not None
    assert deliver.await_args.args[1:] == ("The report is report.pdf.", ())
    assert "chat-db-1" in caplog.text
