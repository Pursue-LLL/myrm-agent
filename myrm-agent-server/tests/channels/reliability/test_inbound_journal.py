"""Tests for InboundJournal — WAL-style inbound message crash recovery."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from app.channels.reliability.inbound_journal import (
    JournalEntry,
    SqliteInboundJournal,
    create_journal_entry_from_inbound,
)
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
)
from app.channels.types.inbound_wire import inbound_to_wire


@pytest.fixture
def journal(tmp_path: Path) -> SqliteInboundJournal:
    return SqliteInboundJournal(db_path=tmp_path / "test_journal.db")


def _make_entry(
    entry_id: str = "entry-001",
    payload: str = "Hello agent",
    ttl_seconds: int = 600,
    created_at: float | None = None,
) -> JournalEntry:
    """The journal treats the payload as opaque text; it is decoded only by ``restore_inbound``."""
    return JournalEntry(
        id=entry_id,
        payload_json=json.dumps({"content": payload}),
        created_at=created_at or time.time(),
        ttl_seconds=ttl_seconds,
    )


class TestSqliteInboundJournal:
    """Core CRUD tests for SqliteInboundJournal."""

    def test_write_and_scan(self, journal: SqliteInboundJournal) -> None:
        entry = _make_entry()
        journal.write(entry)

        pending = journal.scan_pending()
        assert len(pending) == 1
        assert pending[0].id == "entry-001"
        assert json.loads(pending[0].payload_json) == {"content": "Hello agent"}

    def test_acknowledge_removes_entry(self, journal: SqliteInboundJournal) -> None:
        entry = _make_entry()
        journal.write(entry)
        assert len(journal.scan_pending()) == 1

        journal.acknowledge("entry-001")
        assert len(journal.scan_pending()) == 0

    def test_acknowledge_nonexistent_id(self, journal: SqliteInboundJournal) -> None:
        journal.acknowledge("nonexistent-id")

    def test_scan_excludes_expired(self, journal: SqliteInboundJournal) -> None:
        fresh = _make_entry(entry_id="fresh", ttl_seconds=600)
        expired = _make_entry(entry_id="expired", ttl_seconds=1, created_at=time.time() - 100)

        journal.write(fresh)
        journal.write(expired)

        pending = journal.scan_pending()
        assert len(pending) == 1
        assert pending[0].id == "fresh"

    def test_scan_with_max_age_override(self, journal: SqliteInboundJournal) -> None:
        old = _make_entry(entry_id="old", ttl_seconds=3600, created_at=time.time() - 120)
        journal.write(old)

        assert len(journal.scan_pending(max_age_seconds=60)) == 0
        assert len(journal.scan_pending(max_age_seconds=300)) == 1

    def test_prune_expired(self, journal: SqliteInboundJournal) -> None:
        fresh = _make_entry(entry_id="fresh", ttl_seconds=600)
        expired1 = _make_entry(entry_id="exp1", ttl_seconds=1, created_at=time.time() - 100)
        expired2 = _make_entry(entry_id="exp2", ttl_seconds=5, created_at=time.time() - 100)

        journal.write(fresh)
        journal.write(expired1)
        journal.write(expired2)

        pruned = journal.prune_expired()
        assert pruned == 2

        pending = journal.scan_pending()
        assert len(pending) == 1
        assert pending[0].id == "fresh"

    def test_write_same_id_replaces(self, journal: SqliteInboundJournal) -> None:
        journal.write(_make_entry(payload="original"))
        journal.write(_make_entry(payload="updated"))

        pending = journal.scan_pending()
        assert len(pending) == 1
        assert json.loads(pending[0].payload_json) == {"content": "updated"}

    def test_multiple_entries_ordered_by_created_at(self, journal: SqliteInboundJournal) -> None:
        now = time.time()
        journal.write(_make_entry(entry_id="c", created_at=now - 10))
        journal.write(_make_entry(entry_id="a", created_at=now - 30))
        journal.write(_make_entry(entry_id="b", created_at=now - 20))

        pending = journal.scan_pending()
        assert [e.id for e in pending] == ["a", "b", "c"]


class TestJournalEntryModel:
    """Tests for JournalEntry dataclass."""

    def test_frozen_dataclass(self) -> None:
        entry = _make_entry()
        with pytest.raises(AttributeError):
            entry.payload_json = "modified"  # type: ignore[misc]


class TestCreateJournalEntryFromInbound:
    """Tests for the helper function that converts InboundMessage to JournalEntry."""

    def test_entry_holds_the_message_as_its_wire_form(self) -> None:
        msg = InboundMessage(
            channel="discord",
            sender_id="user-123",
            content="Hello world",
            chat_id="chat-456",
            user_id="user-123",
            metadata={"key": "val"},
            thread_id="thread-1",
        )

        entry = create_journal_entry_from_inbound(msg)

        assert json.loads(entry.payload_json) == inbound_to_wire(msg)
        assert entry.ttl_seconds == 600

    def test_strips_yolo_state(self) -> None:
        msg = InboundMessage(
            channel="telegram",
            sender_id="s",
            content="cmd",
            metadata={"yolo_state": (1.0, 300), "other": "keep"},
        )

        entry = create_journal_entry_from_inbound(msg)

        assert json.loads(entry.payload_json)["metadata"] == {"other": "keep"}
        assert "yolo_state" in msg.metadata

    def test_media_keeps_its_local_path(self) -> None:
        msg = InboundMessage(
            channel="slack",
            sender_id="s",
            content="image",
            media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.png", path="/tmp/img.png"),),
        )

        [media] = json.loads(create_journal_entry_from_inbound(msg).payload_json)["media"]

        assert (media["url"], media["path"]) == ("https://example.com/img.png", "/tmp/img.png")

    def test_custom_ttl(self) -> None:
        msg = InboundMessage(channel="c", sender_id="s", content="x")
        entry = create_journal_entry_from_inbound(msg, ttl_seconds=120)
        assert entry.ttl_seconds == 120


class TestThreadSafety:
    """Verify concurrent access safety."""

    def test_concurrent_writes(self, journal: SqliteInboundJournal) -> None:
        errors: list[Exception] = []

        def write_batch(batch_id: int) -> None:
            try:
                for i in range(20):
                    entry = _make_entry(
                        entry_id=f"batch-{batch_id}-{i}",
                        payload=f"msg-{batch_id}-{i}",
                    )
                    journal.write(entry)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_batch, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        pending = journal.scan_pending()
        assert len(pending) == 80

    def test_concurrent_write_and_acknowledge(self, journal: SqliteInboundJournal) -> None:
        for i in range(20):
            journal.write(_make_entry(entry_id=f"pre-{i}"))

        errors: list[Exception] = []

        def ack_batch() -> None:
            try:
                for i in range(20):
                    journal.acknowledge(f"pre-{i}")
            except Exception as e:
                errors.append(e)

        def write_new() -> None:
            try:
                for i in range(20):
                    journal.write(_make_entry(entry_id=f"new-{i}"))
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=ack_batch)
        t2 = threading.Thread(target=write_new)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        pending = journal.scan_pending()
        assert len(pending) == 20
        assert all(e.id.startswith("new-") for e in pending)


class TestErrorHandling:
    """Test graceful error handling (never raises, only logs)."""

    def test_write_survives_db_error(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        journal = SqliteInboundJournal(db_path=tmp_path / "test.db")
        journal._conn.close()

        entry = _make_entry()
        journal.write(entry)
        assert "failed to write" in caplog.text

    def test_acknowledge_survives_db_error(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        journal = SqliteInboundJournal(db_path=tmp_path / "test.db")
        journal._conn.close()

        journal.acknowledge("some-id")
        assert "failed to acknowledge" in caplog.text

    def test_scan_survives_db_error(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        journal = SqliteInboundJournal(db_path=tmp_path / "test.db")
        journal._conn.close()

        result = journal.scan_pending()
        assert result == []
        assert "scan_pending failed" in caplog.text

    def test_prune_survives_db_error(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        journal = SqliteInboundJournal(db_path=tmp_path / "test.db")
        journal._conn.close()

        result = journal.prune_expired()
        assert result == 0
        assert "prune_expired failed" in caplog.text


class TestDbInitialization:
    """Test database creation and persistence."""

    def test_creates_db_directory(self, tmp_path: Path) -> None:
        db_path = tmp_path / "nested" / "dir" / "journal.db"
        journal = SqliteInboundJournal(db_path=db_path)
        journal.write(_make_entry())
        assert db_path.exists()

    def test_persistence_across_instances(self, tmp_path: Path) -> None:
        db_path = tmp_path / "journal.db"

        journal1 = SqliteInboundJournal(db_path=db_path)
        journal1.write(_make_entry(entry_id="persist-1"))

        journal2 = SqliteInboundJournal(db_path=db_path)
        pending = journal2.scan_pending()
        assert len(pending) == 1
        assert pending[0].id == "persist-1"
