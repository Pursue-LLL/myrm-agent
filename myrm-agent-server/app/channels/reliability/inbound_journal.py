"""Inbound Message Journal — WAL-style persistence for in-flight message processing.

Symmetric to the Outbound DLQ (dlq.py): DLQ handles outbound delivery failures,
while the Inbound Journal ensures inbound user messages are not lost when the
process crashes or restarts mid-processing.

Lifecycle:
1. Router writes a journal entry BEFORE starting agent execution
2. Router acknowledges the entry AFTER successful completion
3. On restart, Gateway scans un-acknowledged entries and re-submits them

[INPUT]
- channels.types.messages::InboundMessage (POS: inbound message data)

[OUTPUT]
- InboundJournal: Protocol for journal persistence
- JournalEntry: Persisted message data
- SqliteInboundJournal: SQLite implementation (framework default)

[POS]
Inbound reliability layer. Ensures no user message is lost due to process crash.
Uses Write-Ahead Log pattern: record before processing, delete after completion.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 600  # 10 minutes


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """A persisted inbound message awaiting processing completion."""

    id: str
    channel: str
    chat_id: str
    sender_id: str
    user_id: str
    content: str
    metadata_json: str
    media_json: str
    thread_id: str | None
    is_group: bool
    created_at: float
    ttl_seconds: int = _DEFAULT_TTL_SECONDS
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds


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
        conn = sqlite3.connect(
            str(self._db_path), timeout=5.0, check_same_thread=False
        )
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
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS inbound_journal (
                id TEXT PRIMARY KEY,
                channel TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                media_json TEXT NOT NULL DEFAULT '[]',
                thread_id TEXT,
                is_group INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                ttl_seconds INTEGER NOT NULL DEFAULT 600,
                extra_json TEXT NOT NULL DEFAULT '{}'
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_journal_created "
            "ON inbound_journal(created_at)"
        )
        self._conn.commit()

    def write(self, entry: JournalEntry) -> None:
        """Record entry. Catches all exceptions to avoid blocking main flow."""
        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO inbound_journal
                    (id, channel, chat_id, sender_id, user_id, content,
                     metadata_json, media_json, thread_id, is_group,
                     created_at, ttl_seconds, extra_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.id,
                        entry.channel,
                        entry.chat_id,
                        entry.sender_id,
                        entry.user_id,
                        entry.content,
                        entry.metadata_json,
                        entry.media_json,
                        entry.thread_id,
                        1 if entry.is_group else 0,
                        entry.created_at,
                        entry.ttl_seconds,
                        json.dumps(entry.extra),
                    ),
                )
                self._conn.commit()
        except Exception as e:
            logger.warning("InboundJournal: failed to write entry %s: %s", entry.id, e)

    def acknowledge(self, entry_id: str) -> None:
        """Delete entry after successful processing."""
        try:
            with self._lock:
                self._conn.execute(
                    "DELETE FROM inbound_journal WHERE id = ?", (entry_id,)
                )
                self._conn.commit()
        except Exception as e:
            logger.warning(
                "InboundJournal: failed to acknowledge %s: %s", entry_id, e
            )

    def scan_pending(self, max_age_seconds: float | None = None) -> list[JournalEntry]:
        """Return non-expired pending entries."""
        now = time.time()
        entries: list[JournalEntry] = []
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM inbound_journal ORDER BY created_at ASC"
                ).fetchall()

            for row in rows:
                created_at = row["created_at"]
                ttl = row["ttl_seconds"]
                age = now - created_at

                effective_max = max_age_seconds if max_age_seconds is not None else ttl
                if age > effective_max:
                    continue

                extra_raw = row["extra_json"]
                extra = json.loads(extra_raw) if extra_raw else {}

                entries.append(
                    JournalEntry(
                        id=row["id"],
                        channel=row["channel"],
                        chat_id=row["chat_id"],
                        sender_id=row["sender_id"],
                        user_id=row["user_id"] or "",
                        content=row["content"],
                        metadata_json=row["metadata_json"],
                        media_json=row["media_json"],
                        thread_id=row["thread_id"],
                        is_group=bool(row["is_group"]),
                        created_at=created_at,
                        ttl_seconds=ttl,
                        extra=extra,
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


def create_journal_entry_from_inbound(
    msg: object,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> JournalEntry:
    """Create a JournalEntry from an InboundMessage.

    Accepts `object` to avoid importing InboundMessage at module level
    (prevents circular imports in the reliability subpackage).
    """
    from app.channels.types import InboundMessage

    assert isinstance(msg, InboundMessage)

    metadata = dict(msg.metadata) if msg.metadata else {}
    metadata.pop("yolo_state", None)

    media_refs: list[dict[str, str]] = []
    for m in msg.media:
        media_refs.append({"url": m.url or "", "mime_type": m.mime_type or ""})

    return JournalEntry(
        id=str(uuid.uuid4()),
        channel=msg.channel,
        chat_id=msg.chat_id or msg.sender_id,
        sender_id=msg.sender_id,
        user_id=msg.user_id or "",
        content=msg.content,
        metadata_json=json.dumps(metadata, default=str),
        media_json=json.dumps(media_refs),
        thread_id=msg.thread_id,
        is_group=msg.is_group,
        created_at=time.time(),
        ttl_seconds=ttl_seconds,
    )
