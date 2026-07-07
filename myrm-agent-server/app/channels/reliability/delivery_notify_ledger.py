"""SQLite ledger for permanent-failure notification dedupe across restarts.

[INPUT]
- myrm_agent_harness.infra.delivery.notification_ledger::PermanentFailureNotificationLedger (POS)

[OUTPUT]
- SqliteDeliveryNotifyLedger: Persistent delivery_id notify dedupe

[POS]
Outbound reliability companion to inbound_journal / DLQ — prevents duplicate
WebUI toasts when sync send_tracked fails and the server restarts before DLQ retry.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_RETENTION_DAYS = 30


class SqliteDeliveryNotifyLedger:
    """SQLite-backed permanent-failure notification dedupe."""

    __slots__ = ("_conn", "_db_path", "_lock")

    def __init__(self, db_path: str | Path, *, retention_days: int = _DEFAULT_RETENTION_DAYS) -> None:
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = self._create_conn()
        self._init_db()
        self._prune_older_than(retention_days)

    def _create_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=5.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS permanent_failure_notifications (
                delivery_id TEXT PRIMARY KEY,
                notified_at REAL NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pfn_notified_at ON permanent_failure_notifications(notified_at)"
        )
        self._conn.commit()

    def _prune_older_than(self, retention_days: int) -> None:
        if retention_days <= 0:
            return
        cutoff = time.time() - (retention_days * 24 * 3600)
        try:
            with self._lock:
                self._conn.execute(
                    "DELETE FROM permanent_failure_notifications WHERE notified_at < ?",
                    (cutoff,),
                )
                self._conn.commit()
        except Exception as exc:
            logger.warning("Failed to prune delivery notify ledger: %s", exc)

    def was_notified(self, delivery_id: str) -> bool:
        if not delivery_id:
            return False
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT 1 FROM permanent_failure_notifications WHERE delivery_id = ? LIMIT 1",
                    (delivery_id,),
                ).fetchone()
            return row is not None
        except Exception as exc:
            logger.warning("Delivery notify ledger read failed for %s: %s", delivery_id, exc)
            return False

    def mark_notified(self, delivery_id: str) -> None:
        if not delivery_id:
            return
        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO permanent_failure_notifications (delivery_id, notified_at)
                    VALUES (?, ?)
                    """,
                    (delivery_id, time.time()),
                )
                self._conn.commit()
        except Exception as exc:
            logger.warning("Delivery notify ledger write failed for %s: %s", delivery_id, exc)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
