"""Inbound Message Journal — WAL-style persistence for inbound messages that have not finished processing.

Symmetric to the outbound dead-letter queue (harness ``DeadLetterQueue``, driven by the
MessageBus): the DLQ handles outbound delivery failures, while the Inbound Journal lets inbound
user messages survive a process crash mid-turn and a stop of the router with messages still queued.

Lifecycle:
1. Router writes a journal entry BEFORE starting agent execution; a stopping router writes the
   entries of the messages its gate holds that have not started a turn
2. Router acknowledges the entry when the turn ends, however it ends (completed, failed, ended by
   ``/stop``, cancelled by a stop): only a process that dies mid-turn leaves its entry behind
3. On start, Gateway scans un-acknowledged entries within their TTL and re-submits them as
   ``restore_inbound`` rebuilds them

[INPUT]
- channels.types.messages::InboundMessage (POS: inbound message data)
- channels.types.inbound_wire::inbound_to_wire, inbound_from_wire (POS: the persistable form of an inbound message)

[OUTPUT]
- InboundJournal: Protocol for journal persistence
- METADATA_IS_RECOVERY, METADATA_RECOVERY_ENTRY_ID: the metadata keys that mark a replayed message and name its entry
- JournalEntry: one persisted message (its wire form as JSON) with its age limit
- SqliteInboundJournal: SQLite implementation (framework default)
- create_journal_entry_from_inbound, restore_inbound: message to entry, and entry back to the message

[POS]
Inbound reliability layer. A crash replays the turn it interrupted; a stop replays the messages
its gate held that had not started one (a message that reaches the bus after the stop began is not journaled).
An entry holds the whole message except ``channel_capabilities`` and the yolo window (both re-derived when the
replayed turn starts), so a replay is the message the user sent, not just its text.
Write-Ahead Log pattern: record before processing, delete when the turn ends.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from app.channels.types.inbound_wire import InboundWire, inbound_from_wire, inbound_to_wire

if TYPE_CHECKING:
    from app.channels.types import InboundMessage, MediaAttachment

logger = logging.getLogger(__name__)

# Set on a replayed message by ``restore_inbound``; the turn keeps its entry instead of writing a new one, and the agent is told.
METADATA_IS_RECOVERY = "is_recovery"
METADATA_RECOVERY_ENTRY_ID = "recovery_entry_id"

_DEFAULT_TTL_SECONDS = 600  # 10 minutes
_COLUMNS = ("id", "payload_json", "created_at", "ttl_seconds")
# Re-granted from the live session when the replayed turn starts; a stale window must not outlive its restart.
_NOT_PERSISTED_METADATA = frozenset({"yolo_state"})


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """A persisted inbound message awaiting processing completion."""

    id: str
    payload_json: str
    created_at: float
    ttl_seconds: int = _DEFAULT_TTL_SECONDS


class InboundJournal(Protocol):
    """Protocol for inbound message journal persistence.

    Implementations must ensure write/acknowledge are atomic with respect
    to crash recovery (e.g., SQLite transactions, fsync).
    """

    def write(self, entry: JournalEntry) -> None:
        """Record a message before processing begins.

        Must be synchronous and fast (< 1ms typical).
        Implementations should NOT raise on failure — log and continue.
        """
        ...

    def acknowledge(self, entry_id: str) -> None:
        """Mark a message as successfully processed (delete from journal).

        Called in the finally block after agent execution completes.
        """
        ...

    def scan_pending(self, max_age_seconds: float | None = None) -> list[JournalEntry]:
        """Scan un-acknowledged entries for recovery.

        Args:
            max_age_seconds: Override TTL filter. If None, uses each entry's own TTL.

        Returns entries that are pending AND not expired.
        """
        ...

    def prune_expired(self) -> int:
        """Remove entries that have exceeded their TTL.

        Returns the number of pruned entries.
        """
        ...


class SqliteInboundJournal:
    """SQLite-backed inbound journal with WAL mode for crash safety.

    Uses synchronous sqlite3 (not aiosqlite) because:
    - write/acknowledge are called on the hot path and must be fast
    - SQLite WAL mode writes are ~0.1ms, negligible vs LLM latency
    - Avoids async overhead for trivial operations

    Single persistent connection (check_same_thread=False) is safe because
    the framework runs in a single-process model (agent-in-sandbox).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = self._create_conn()
        self._init_db()

    def _create_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=5.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def close(self) -> None:
        """Close the database connection. Safe to call multiple times."""
        try:
            self._conn.close()
        except Exception:
            pass

    def _init_db(self) -> None:
        columns = [row["name"] for row in self._conn.execute("PRAGMA table_info(inbound_journal)")]
        if columns and columns != list(_COLUMNS):
            # An entry lives ten minutes at most: a table of another column set is replaced, not migrated.
            queued = self._conn.execute("SELECT COUNT(*) FROM inbound_journal").fetchone()[0]
            logger.warning("InboundJournal: replacing a journal table of another shape, dropping %d queued entries", queued)
            self._conn.execute("DROP TABLE inbound_journal")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS inbound_journal (
                id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                ttl_seconds INTEGER NOT NULL DEFAULT 600
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_created ON inbound_journal(created_at)")
        self._conn.commit()

    def write(self, entry: JournalEntry) -> None:
        """Record entry. Catches all exceptions to avoid blocking main flow."""
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO inbound_journal (id, payload_json, created_at, ttl_seconds) VALUES (?, ?, ?, ?)",
                    (entry.id, entry.payload_json, entry.created_at, entry.ttl_seconds),
                )
                self._conn.commit()
        except Exception as e:
            logger.warning("InboundJournal: failed to write entry %s: %s", entry.id, e)

    def acknowledge(self, entry_id: str) -> None:
        """Delete entry after successful processing."""
        try:
            with self._lock:
                self._conn.execute("DELETE FROM inbound_journal WHERE id = ?", (entry_id,))
                self._conn.commit()
        except Exception as e:
            logger.warning("InboundJournal: failed to acknowledge %s: %s", entry_id, e)

    def scan_pending(self, max_age_seconds: float | None = None) -> list[JournalEntry]:
        """Return non-expired pending entries."""
        now = time.time()
        entries: list[JournalEntry] = []
        try:
            with self._lock:
                rows = self._conn.execute("SELECT * FROM inbound_journal ORDER BY created_at ASC").fetchall()

            for row in rows:
                effective_max = max_age_seconds if max_age_seconds is not None else row["ttl_seconds"]
                if now - row["created_at"] > effective_max:
                    continue
                entries.append(
                    JournalEntry(
                        id=row["id"],
                        payload_json=row["payload_json"],
                        created_at=row["created_at"],
                        ttl_seconds=row["ttl_seconds"],
                    )
                )
        except Exception as e:
            logger.warning("InboundJournal: scan_pending failed: %s", e)

        return entries

    def prune_expired(self) -> int:
        """Remove entries older than their individual TTL."""
        now = time.time()
        try:
            with self._lock:
                cursor = self._conn.execute(
                    "DELETE FROM inbound_journal WHERE (? - created_at) > ttl_seconds",
                    (now,),
                )
                self._conn.commit()
                pruned = cursor.rowcount
            if pruned > 0:
                logger.info("InboundJournal: pruned %d expired entries", pruned)
            return pruned
        except Exception as e:
            logger.warning("InboundJournal: prune_expired failed: %s", e)
            return 0


def create_journal_entry_from_inbound(msg: InboundMessage, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> JournalEntry:
    """The journal entry for ``msg``: its wire form, minus the metadata a restart must not carry over."""
    persisted = replace(msg, metadata={k: v for k, v in msg.metadata.items() if k not in _NOT_PERSISTED_METADATA})
    return JournalEntry(
        id=str(uuid.uuid4()),
        payload_json=json.dumps(inbound_to_wire(persisted), default=str),
        created_at=time.time(),
        ttl_seconds=ttl_seconds,
    )


def _surviving_media(media: tuple[MediaAttachment, ...]) -> tuple[tuple[MediaAttachment, ...], list[str]]:
    """Split ``media`` into what can still be fetched and the names of what cannot.

    A local temp file does not outlive the restart; an attachment that also has a url is still fetchable from it.
    """
    kept: list[MediaAttachment] = []
    lost: list[str] = []
    for item in media:
        if not item.path or Path(item.path).exists():
            kept.append(item)
        elif item.url:
            kept.append(replace(item, path=None))
        else:
            lost.append(item.filename or Path(item.path).name)
    return tuple(kept), lost


def restore_inbound(entry: JournalEntry) -> InboundMessage:
    """The message ``entry`` was written from, marked ``is_recovery`` so the turn knows it is a replay.

    An attachment that can no longer be fetched is dropped and named in the text, so the agent does not wait for a
    file that cannot arrive.
    """
    msg = inbound_from_wire(cast("InboundWire", json.loads(entry.payload_json)))
    media, lost = _surviving_media(msg.media)
    content = msg.content
    if lost:
        notes = [f"[Attachment: {name}] (file lost in the restart)" for name in lost]
        content = "\n".join(filter(None, [content, *notes]))
    metadata = {**msg.metadata, METADATA_IS_RECOVERY: True, METADATA_RECOVERY_ENTRY_ID: entry.id}
    return replace(msg, content=content, media=media, metadata=metadata)
