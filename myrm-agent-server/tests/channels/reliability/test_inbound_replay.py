"""A message replayed from the inbound journal is the message the user sent, not just its text.

Follows a message the way production does: ``create_journal_entry_from_inbound`` at turn start, SQLite, then
``ChannelGateway._recover_journal`` at the next start handing it to the router's gate.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock

from app.channels.core.gateway import ChannelGateway
from app.channels.reliability.inbound_journal import JournalEntry, SqliteInboundJournal, create_journal_entry_from_inbound
from app.channels.types import InboundMessage, MediaAttachment, MediaType
from tests.channels.inbound_message_testkit import full_message

# A journal table of another column set: one column per message field instead of the whole message.
_OTHER_SHAPE_TABLE = """
    CREATE TABLE inbound_journal (
        id TEXT PRIMARY KEY, channel TEXT NOT NULL, chat_id TEXT NOT NULL, sender_id TEXT NOT NULL,
        user_id TEXT NOT NULL DEFAULT '', content TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
        media_json TEXT NOT NULL DEFAULT '[]', thread_id TEXT, is_group INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL, ttl_seconds INTEGER NOT NULL DEFAULT 600, extra_json TEXT NOT NULL DEFAULT '{}'
    )
"""


def _journal(tmp_path: Path) -> SqliteInboundJournal:
    return SqliteInboundJournal(db_path=tmp_path / "journal.db")


def _park(journal: SqliteInboundJournal, msg: InboundMessage) -> str:
    entry = create_journal_entry_from_inbound(msg)
    journal.write(entry)
    return entry.id


async def _replay(journal: SqliteInboundJournal) -> list[InboundMessage]:
    gateway = ChannelGateway(inbound_journal=journal)
    router = MagicMock()
    gateway._router = router
    await gateway._recover_journal()
    return [call.args[0] for call in router._gate.submit.call_args_list]


async def test_a_replayed_message_carries_every_field_of_the_original(tmp_path: Path) -> None:
    image = tmp_path / "a.png"
    image.write_bytes(b"png")
    original = full_message(image_path=str(image))
    journal = _journal(tmp_path)
    entry_id = _park(journal, original)

    replayed = await _replay(journal)

    marked = {**original.metadata, "is_recovery": True, "recovery_entry_id": entry_id}
    assert replayed == [dataclasses.replace(original, metadata=marked)]


async def test_a_message_without_a_chat_id_replays_without_one(tmp_path: Path) -> None:
    original = InboundMessage(channel="slack", sender_id="u1", content="hi", sent_at=1.0)
    journal = _journal(tmp_path)
    _park(journal, original)

    [replayed] = await _replay(journal)

    assert (replayed.chat_id, replayed.user_id) == (None, None)


async def test_the_yolo_window_is_not_carried_across_a_restart(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    _park(journal, InboundMessage(channel="slack", sender_id="u1", content="hi", metadata={"yolo_state": (1.0, 300), "k": "v"}))

    [replayed] = await _replay(journal)

    assert "yolo_state" not in replayed.metadata
    assert replayed.metadata["k"] == "v"


async def test_an_attachment_whose_file_is_gone_becomes_a_note_in_the_text(tmp_path: Path) -> None:
    gone = tmp_path / "gone.pdf"
    kept = MediaAttachment(media_type=MediaType.DOCUMENT, url="https://files.test/b.pdf", filename="b.pdf")
    lost = MediaAttachment(media_type=MediaType.DOCUMENT, path=str(gone), filename="gone.pdf")
    journal = _journal(tmp_path)
    _park(journal, InboundMessage(channel="feishu", sender_id="u1", content="see these", media=(kept, lost)))

    [replayed] = await _replay(journal)

    assert replayed.media == (kept,)
    assert replayed.content.startswith("see these")
    assert "gone.pdf" in replayed.content


async def test_an_attachment_with_a_url_outlives_its_local_file(tmp_path: Path) -> None:
    both = MediaAttachment(media_type=MediaType.IMAGE, url="https://files.test/a.png", path=str(tmp_path / "gone.png"))
    journal = _journal(tmp_path)
    _park(journal, InboundMessage(channel="feishu", sender_id="u1", content="look", media=(both,)))

    [replayed] = await _replay(journal)

    assert replayed.media == (dataclasses.replace(both, path=None),)
    assert replayed.content == "look"


async def test_an_entry_that_cannot_be_read_does_not_block_the_ones_after_it(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    now = time.time()
    journal.write(JournalEntry(id="broken", payload_json="{not json", created_at=now - 5))
    fine = create_journal_entry_from_inbound(InboundMessage(channel="slack", sender_id="u1", content="fine"))
    journal.write(dataclasses.replace(fine, created_at=now - 1))

    replayed = await _replay(journal)

    assert [msg.content for msg in replayed] == ["fine"]


def test_a_table_of_another_shape_is_rebuilt_so_the_journal_keeps_working(tmp_path: Path) -> None:
    db_path = tmp_path / "journal.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(_OTHER_SHAPE_TABLE)
        conn.execute(
            "INSERT INTO inbound_journal (id, channel, chat_id, sender_id, content, created_at) "
            "VALUES ('old', 'slack', 'c', 's', 'queued under the other shape', strftime('%s','now'))"
        )
    journal = SqliteInboundJournal(db_path=db_path)

    assert journal.scan_pending() == []
    entry_id = _park(journal, InboundMessage(channel="slack", sender_id="u1", content="after the rebuild"))
    assert [entry.id for entry in journal.scan_pending()] == [entry_id]
