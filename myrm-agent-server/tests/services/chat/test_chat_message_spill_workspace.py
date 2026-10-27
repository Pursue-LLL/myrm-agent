"""``ChatService.append_message`` parks an oversized user message in the workspace the caller names."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import MessageDTO
from app.services.chat.chat_service import ChatService

_PASTE = "meeting-line: the decision was to keep watching and review next week\n" * 400


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The default spill directory lives under the home directory; keep it away from the real one."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


async def _append(chat_id: str, role: str, content: str, *, spill_workspace: Path) -> MessageDTO:
    return await ChatService.append_message(chat_id, role, content, datetime.now(UTC), "UTC", spill_workspace=spill_workspace)


async def _channel_chat_id() -> str:
    return (await ChatService.get_or_create_channel_chat("test:spill-workspace", "test")).id


@pytest.mark.asyncio
async def test_oversized_user_message_is_parked_in_the_named_workspace(
    db_session: AsyncSession, tmp_path: Path, fake_home: Path
) -> None:
    del db_session
    workspace = tmp_path / "agent-workspace"
    message = await _append(await _channel_chat_id(), "user", _PASTE, spill_workspace=workspace)

    spill_dir = workspace / ".myrm" / "spillover"
    (parked,) = list(spill_dir.glob("payload_*.md"))
    assert parked.read_text(encoding="utf-8") == _PASTE
    assert message.content.startswith("<file_spillover")
    assert str(parked.resolve()) in message.content
    assert "file_read_tool" in message.content
    assert message.extra_data is not None
    spillover = message.extra_data["spillover"]
    assert isinstance(spillover, dict)
    assert spillover["spillover_path"] == str(parked.resolve())
    assert not (fake_home / ".myrm").exists()


@pytest.mark.asyncio
async def test_small_user_message_is_stored_verbatim_and_writes_nothing(
    db_session: AsyncSession, tmp_path: Path, fake_home: Path
) -> None:
    del db_session
    workspace = tmp_path / "agent-workspace"
    message = await _append(await _channel_chat_id(), "user", "short question", spill_workspace=workspace)

    assert message.content == "short question"
    assert message.extra_data is None
    assert not workspace.exists()
    assert not (fake_home / ".myrm").exists()


@pytest.mark.asyncio
async def test_assistant_message_is_never_spilled(db_session: AsyncSession, tmp_path: Path, fake_home: Path) -> None:
    del db_session
    workspace = tmp_path / "agent-workspace"
    message = await _append(await _channel_chat_id(), "assistant", _PASTE, spill_workspace=workspace)

    assert message.content == _PASTE
    assert not workspace.exists()
    assert not (fake_home / ".myrm").exists()
