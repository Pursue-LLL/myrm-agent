"""Read-only views of sessions, ownership resources and the event journal."""

from __future__ import annotations

from dev_gate.session import SessionRecord, SessionState
from dev_gate.store.base import StoreBase
from dev_gate.store.schema import DEFAULT_JOURNAL_RETENTION_SEC


class QueryMixin(StoreBase):
    """Read operations of the store."""

    def get(self, session_id: str) -> SessionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return None if row is None else self._record(row)

    def list_active(self) -> tuple[SessionRecord, ...]:
        terminal = tuple(
            state.value
            for state in (
                SessionState.SUCCEEDED,
                SessionState.FAILED,
                SessionState.CANCELLED,
            )
        )
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sessions
                WHERE state NOT IN (?, ?, ?)
                ORDER BY submitted_at, session_id
                """,
                terminal,
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def latest_event_id(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(event_id), 0) AS max_id
                FROM events WHERE session_id=?
                """,
                (session_id,),
            ).fetchone()
        return 0 if row is None else int(row["max_id"])

    def fetch_events_after(
        self,
        session_id: str,
        *,
        after_event_id: int,
        event_types: frozenset[str] | None = None,
    ) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            if event_types:
                placeholders = ",".join("?" for _ in event_types)
                rows = connection.execute(
                    f"""
                    SELECT event_id, event_type, state, created_at, detail_json, version
                    FROM events
                    WHERE session_id=? AND event_id>? AND event_type IN ({placeholders})
                    ORDER BY event_id ASC
                    """,
                    (session_id, after_event_id, *sorted(event_types)),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT event_id, event_type, state, created_at, detail_json, version
                    FROM events
                    WHERE session_id=? AND event_id>?
                    ORDER BY event_id ASC
                    """,
                    (session_id, after_event_id),
                ).fetchall()
        events: list[dict[str, object]] = []
        for row in rows:
            detail_raw = self._load_json_field(row["detail_json"], default={})
            detail = detail_raw if isinstance(detail_raw, dict) else {}
            events.append(
                {
                    "event_id": int(row["event_id"]),
                    "event_type": str(row["event_type"]),
                    "state": str(row["state"]),
                    "created_at": float(row["created_at"]),
                    "version": int(row["version"]),
                    "detail": detail,
                }
            )
        return tuple(events)

    def list_recent_sessions(self, *, limit: int = 200) -> tuple[SessionRecord, ...]:
        bounded = max(1, min(int(limit), 2000))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sessions
                ORDER BY submitted_at DESC, session_id DESC
                LIMIT ?
                """,
                (bounded,),
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def fetch_recent_events(
        self,
        *,
        limit: int = 2000,
        session_ids: tuple[str, ...] | None = None,
    ) -> tuple[dict[str, object], ...]:
        bounded = max(1, min(int(limit), 10000))
        with self._connect() as connection:
            if session_ids:
                placeholders = ",".join("?" for _ in session_ids)
                rows = connection.execute(
                    f"""
                    SELECT event_id, session_id, event_type, state, created_at,
                           detail_json, version
                    FROM events
                    WHERE session_id IN ({placeholders})
                    ORDER BY event_id DESC
                    LIMIT ?
                    """,
                    (*session_ids, bounded),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT event_id, session_id, event_type, state, created_at,
                           detail_json, version
                    FROM events
                    ORDER BY event_id DESC
                    LIMIT ?
                    """,
                    (bounded,),
                ).fetchall()
        events: list[dict[str, object]] = []
        for row in reversed(rows):
            detail_raw = self._load_json_field(row["detail_json"], default={})
            detail = detail_raw if isinstance(detail_raw, dict) else {}
            events.append(
                {
                    "event_id": int(row["event_id"]),
                    "session_id": str(row["session_id"]),
                    "event_type": str(row["event_type"]),
                    "state": str(row["state"]),
                    "created_at": float(row["created_at"]),
                    "version": int(row["version"]),
                    "detail": detail,
                }
            )
        return tuple(events)

    def list_ownership_resources(
        self,
        *,
        session_ids: tuple[str, ...] | None = None,
    ) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            if session_ids:
                placeholders = ",".join("?" for _ in session_ids)
                rows = connection.execute(
                    f"""
                    SELECT session_id, resource_key, resource_kind, resource_value,
                           version, updated_at
                    FROM ownership_resources
                    WHERE session_id IN ({placeholders})
                    ORDER BY session_id, resource_key
                    """,
                    session_ids,
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT session_id, resource_key, resource_kind, resource_value,
                           version, updated_at
                    FROM ownership_resources
                    ORDER BY session_id, resource_key
                    """
                ).fetchall()
        return tuple(
            {
                "session_id": str(row["session_id"]),
                "resource_key": str(row["resource_key"]),
                "resource_kind": str(row["resource_kind"]),
                "resource_value": str(row["resource_value"]),
                "version": int(row["version"]),
                "updated_at": float(row["updated_at"]),
            }
            for row in rows
        )

    def journal_stats(self) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS event_count,
                       MIN(created_at) AS oldest_at,
                       MAX(created_at) AS newest_at
                FROM events
                """
            ).fetchone()
        if row is None:
            return {"event_count": 0, "oldest_at": None, "newest_at": None}
        oldest = row["oldest_at"]
        newest = row["newest_at"]
        return {
            "event_count": int(row["event_count"]),
            "oldest_at": None if oldest is None else float(oldest),
            "newest_at": None if newest is None else float(newest),
            "retention_sec": DEFAULT_JOURNAL_RETENTION_SEC,
        }
