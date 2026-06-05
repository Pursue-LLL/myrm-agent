"""Dead Letter Queue (DLQ) storage and automatic retry mechanism.

[INPUT]
- channels.types.messages::OutboundMessage (POS: Core message type definitions. All cross-channel communication data structures are defined here; zero I/O, pure data.)
- channels.core.bus::MessageBus (POS: Event Bus Implementation)

[OUTPUT]
- DLQStorage: Abstract interface for DLQ persistence
- SQLiteDLQStorage: SQLite-based implementation for Sandbox environments
- AutoRetryWorker: Background task that polls DLQ and retries messages

[POS]
Provides persistent storage for messages that failed to send after all retries.
Includes an automatic retry worker that uses exponential backoff to recover
messages when transient issues (e.g., network outages) are resolved.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.channels.types.messages import OutboundMessage

logger = logging.getLogger(__name__)


@dataclass
class FailedMessage:
    """A message that failed to send and is stored in the DLQ."""

    id: str
    channel: str
    recipient_id: str
    content: str
    error_reason: str
    status: str  # 'pending', 'retrying', 'success', 'failed_permanently'
    retry_count: int
    next_retry_at: float
    created_at: float
    payload: dict[str, object]


class DLQStorage(ABC):
    """Abstract interface for DLQ persistence."""

    @abstractmethod
    def save(self, msg: OutboundMessage, error_reason: str) -> str:
        """Save a failed message to the DLQ. Returns the assigned ID."""
        pass

    @abstractmethod
    def get_pending(self, limit: int = 100) -> list[FailedMessage]:
        """Get messages that are ready for automatic retry."""
        pass

    @abstractmethod
    def update_status(
        self, msg_id: str, status: str, error_reason: str | None = None, next_retry_at: float | None = None
    ) -> None:
        """Update the status of a message after a retry attempt."""
        pass

    @abstractmethod
    def get_all(self, limit: int = 50, offset: int = 0, status: str | None = None) -> tuple[list[FailedMessage], int]:
        """Get all messages for the management UI. Returns (messages, total_count)."""
        pass

    @abstractmethod
    def get_by_id(self, msg_id: str) -> FailedMessage | None:
        """Get a specific message by ID."""
        pass

    @abstractmethod
    def delete(self, msg_id: str) -> bool:
        """Delete a message from the DLQ. Returns True if deleted."""
        pass


class SQLiteDLQStorage(DLQStorage):
    """SQLite-based DLQ storage, ideal for single-instance Sandbox environments."""

    def __init__(self, db_path: str | Path = "~/.myrm/dlq.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        # Use WAL mode for better concurrency
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failed_messages (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    content TEXT,
                    error_reason TEXT,
                    status TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    next_retry_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status_next_retry ON failed_messages(status, next_retry_at)")
            conn.commit()

    def save(self, msg: OutboundMessage, error_reason: str) -> str:
        import uuid

        msg_id = str(uuid.uuid4())
        now = time.time()
        # Initial retry after 1 minute
        next_retry_at = now + 60.0

        # Serialize payload safely
        # Note: We might need a more robust serializer if OutboundMessage contains complex types
        # For now, we assume simple types or that dataclasses.asdict handles it mostly ok
        try:
            payload_dict = msg.to_dict()
            payload_str = json.dumps(payload_dict)
        except Exception as e:
            logger.error("Failed to serialize OutboundMessage for DLQ: %s", e)
            payload_str = "{}"  # Fallback, though this means the message is lost

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO failed_messages
                (id, channel, recipient_id, content, error_reason, status, retry_count, next_retry_at, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg_id,
                    msg.channel,
                    msg.recipient_id,
                    msg.content[:500] if msg.content else "",  # Store a snippet for UI
                    error_reason,
                    "pending",
                    0,
                    next_retry_at,
                    now,
                    payload_str,
                ),
            )
            conn.commit()
        return msg_id

    def get_pending(self, limit: int = 100) -> list[FailedMessage]:
        now = time.time()
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM failed_messages
                WHERE status = 'pending' AND next_retry_at <= ?
                ORDER BY next_retry_at ASC LIMIT ?
                """,
                (now, limit),
            )
            rows = cursor.fetchall()

        return [self._row_to_model(row) for row in rows]

    def update_status(
        self, msg_id: str, status: str, error_reason: str | None = None, next_retry_at: float | None = None
    ) -> None:
        with self._get_conn() as conn:
            if status == "retrying":
                conn.execute(
                    "UPDATE failed_messages SET status = ?, retry_count = retry_count + 1 WHERE id = ?",
                    (status, msg_id),
                )
            elif status == "pending":
                # It failed again, but we will retry later
                conn.execute(
                    "UPDATE failed_messages SET status = ?, error_reason = ?, next_retry_at = ? WHERE id = ?",
                    (status, error_reason, next_retry_at or time.time() + 300, msg_id),
                )
            else:
                # success or failed_permanently
                conn.execute(
                    "UPDATE failed_messages SET status = ?, error_reason = COALESCE(?, error_reason) WHERE id = ?",
                    (status, error_reason, msg_id),
                )
            conn.commit()

    def get_all(self, limit: int = 50, offset: int = 0, status: str | None = None) -> tuple[list[FailedMessage], int]:
        with self._get_conn() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT * FROM failed_messages WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset),
                )
                count_cursor = conn.execute("SELECT COUNT(*) FROM failed_messages WHERE status = ?", (status,))
            else:
                cursor = conn.execute("SELECT * FROM failed_messages ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
                count_cursor = conn.execute("SELECT COUNT(*) FROM failed_messages")

            rows = cursor.fetchall()
            total = count_cursor.fetchone()[0]

        return [self._row_to_model(row) for row in rows], total

    def get_by_id(self, msg_id: str) -> FailedMessage | None:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM failed_messages WHERE id = ?", (msg_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_model(row)
        return None

    def delete(self, msg_id: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM failed_messages WHERE id = ?", (msg_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_model(self, row: sqlite3.Row) -> FailedMessage:
        return FailedMessage(
            id=row["id"],
            channel=row["channel"],
            recipient_id=row["recipient_id"],
            content=row["content"],
            error_reason=row["error_reason"],
            status=row["status"],
            retry_count=row["retry_count"],
            next_retry_at=row["next_retry_at"],
            created_at=row["created_at"],
            payload=json.loads(row["payload"]),
        )


class AutoRetryWorker:
    """Background worker that polls the DLQ and retries pending messages."""

    def __init__(self, storage: DLQStorage, bus: object, poll_interval: float = 60.0):
        self.storage = storage
        self.bus = bus  # MessageBus type hint omitted to avoid circular import
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("DLQ AutoRetryWorker started (interval: %.1fs)", self.poll_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("DLQ AutoRetryWorker stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._process_pending()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in DLQ AutoRetryWorker loop: %s", e)

            await asyncio.sleep(self.poll_interval)

    async def _process_pending(self) -> None:
        # Run DB query in thread pool to avoid blocking event loop
        pending_msgs = await asyncio.to_thread(self.storage.get_pending, 50)

        if not pending_msgs:
            return

        logger.info("DLQ AutoRetryWorker: Found %d pending messages to retry", len(pending_msgs))

        for msg in pending_msgs:
            if not self._running:
                break

            # Mark as retrying
            await asyncio.to_thread(self.storage.update_status, msg.id, "retrying")

            try:
                outbound_msg = OutboundMessage.from_dict(msg.payload)

                # Better approach: Send directly via channel to control the retry lifecycle here
                channel = self.bus.get_channel(outbound_msg.channel)
                if not channel:
                    raise ValueError(f"Channel {outbound_msg.channel} not found")

                logger.info("DLQ AutoRetryWorker: Retrying message %s for channel %s", msg.id, msg.channel)

                # Send it
                # We don't use send_with_retry here because we are already the outer retry loop
                # But we could use it if we want immediate short-term retries too.
                await channel.send(outbound_msg)

                # Success!
                await asyncio.to_thread(self.storage.update_status, msg.id, "success")
                logger.info("DLQ AutoRetryWorker: Successfully retried message %s", msg.id)

            except Exception as e:
                logger.warning("DLQ AutoRetryWorker: Retry failed for message %s: %s", msg.id, e)

                # Calculate next backoff
                # 1m, 5m, 15m, 1h, 6h
                backoffs = [60, 300, 900, 3600, 21600]
                retry_count = msg.retry_count + 1  # +1 because we just tried

                if retry_count >= len(backoffs):
                    # Max retries reached
                    await asyncio.to_thread(self.storage.update_status, msg.id, "failed_permanently", str(e))
                    logger.error("DLQ AutoRetryWorker: Message %s failed permanently after %d retries", msg.id, retry_count)
                else:
                    next_retry_at = time.time() + backoffs[retry_count]
                    await asyncio.to_thread(self.storage.update_status, msg.id, "pending", str(e), next_retry_at)
