"""SQLite-backed ledger of memoised model calls.

[INPUT]
- __future__
- json::dumps, json::loads
- sqlite3
- threading::Lock
- time::time
- pathlib::Path

[OUTPUT]
- MemoLedger: persistent store of model-call outcomes, keyed by memo key digest

[POS]
Framework-level persistence for the model-call memo ledger. One row per model call, in the
same shape as the durable tool ledger (`runtime/tool_ledger`): a row is written *before* the
call is dispatched, so a crash leaves the truth behind, and the completed answer is written
afterwards, so a repeated call can read it back instead of paying for the model again.

This ledger stores answers, not telemetry: the recorded response is the model's own output.
Callers decide where the file lives and whether the data may be persisted at all.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from myrm_agent_harness.infra.memo.memo_types import MemoEntry, MemoStatus

# A response larger than this is not memoised: replaying it would cost more to store and
# read back than the call is worth, and the row stays `started` so the call is retried.
MAX_RESPONSE_BYTES = 1_000_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_memo (
    key TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    response TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1
)
"""


class MemoLedger:
    """Persistent store of model-call outcomes."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None or str(db_path) == ":memory:":
            self.db_path = ":memory:"
        else:
            resolved = Path(db_path).resolve()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(resolved)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self._conn.close()

    def get(self, key: str) -> MemoEntry | None:
        """The recorded outcome of one call, or None when the call was never memoised."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM llm_memo WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        response: dict[str, object] | None = None
        if row["response"]:
            try:
                loaded = json.loads(row["response"])
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                response = loaded
        try:
            status = MemoStatus(row["status"])
        except ValueError:
            status = MemoStatus.STARTED
        return MemoEntry(
            key=row["key"],
            status=status,
            model=row["model"],
            response=response,
            created_at=row["created_at"],
            attempt=row["attempt"],
        )

    def record_started(self, key: str, model: str) -> None:
        """Record that the call is about to be dispatched."""
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO llm_memo (key, model, status, response, error, created_at, updated_at, attempt)
                VALUES (?, ?, ?, NULL, NULL, ?, ?, 1)
                ON CONFLICT(key) DO UPDATE SET
                    status = excluded.status,
                    response = NULL,
                    error = NULL,
                    updated_at = excluded.updated_at,
                    attempt = llm_memo.attempt + 1
                """,
                (key, model, MemoStatus.STARTED.value, now, now),
            )

    def record_completed(self, key: str, model: str, response: dict[str, object]) -> bool:
        """Record the answer. Returns False when the answer was too large to memoise."""
        payload = json.dumps(response, ensure_ascii=False, default=str)
        if len(payload.encode("utf-8")) > MAX_RESPONSE_BYTES:
            return False
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE llm_memo
                   SET status = ?, response = ?, error = NULL, model = ?, updated_at = ?
                 WHERE key = ?
                """,
                (MemoStatus.COMPLETED.value, payload, model, now, key),
            )
        return True

    def record_failed(self, key: str, model: str, error: str) -> None:
        """Record that the call failed; the next attempt starts over."""
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE llm_memo
                   SET status = ?, response = NULL, error = ?, model = ?, updated_at = ?
                 WHERE key = ?
                """,
                (MemoStatus.FAILED.value, error[:2000], model, now, key),
            )
