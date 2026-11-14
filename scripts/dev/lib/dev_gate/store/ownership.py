"""Resource ownership rows of a session: set, compare-and-swap and destroy."""

from __future__ import annotations

import json
import sqlite3
import time

from dev_gate.session import SessionOwnership, SessionRecord, SessionState
from dev_gate.store.base import StoreBase
from dev_gate.store.connection import begin_immediate


class OwnershipConflictError(RuntimeError):
    """Raised when an ownership CAS update loses against a newer session version."""


class OwnershipMixin(StoreBase):
    """Operations that record which browser resources a session owns."""

    def set_ownership(
        self,
        session_id: str,
        owner_token: str,
        ownership: SessionOwnership,
        *,
        expected_version: int | None = None,
    ) -> SessionRecord:
        touched_at = time.time()
        with self._connect() as connection:
            begin_immediate(connection)
            row = self._owned_row(connection, session_id, owner_token)
            current_version = int(row["version"])
            if expected_version is not None and current_version != expected_version:
                raise OwnershipConflictError(
                    f"ownership version mismatch: session={session_id} "
                    f"expected={expected_version} actual={current_version}"
                )
            version = current_version + 1
            connection.execute(
                """
                UPDATE sessions SET version=?, browser_context_id=?,
                    page_ids_json=?, lease_id=?, runtime_id=?
                WHERE session_id=?
                """,
                (
                    version,
                    ownership.browser_context_id,
                    json.dumps(ownership.page_ids, separators=(",", ":")),
                    ownership.lease_id,
                    ownership.runtime_id,
                    session_id,
                ),
            )
            self._sync_ownership_resource_rows(
                connection,
                session_id=session_id,
                ownership=ownership,
                version=version,
                updated_at=touched_at,
            )
            return self._record(self._required_row(connection, session_id))

    def cas_add_page_id(
        self,
        session_id: str,
        owner_token: str,
        page_id: str,
        *,
        expected_version: int,
    ) -> SessionRecord:
        """Merge one page id under session-version CAS (P0-D resource-key row)."""
        normalized = page_id.strip()
        if not normalized:
            raise ValueError("page_id must be non-empty")
        touched_at = time.time()
        with self._connect() as connection:
            begin_immediate(connection)
            row = self._owned_row(connection, session_id, owner_token)
            current_version = int(row["version"])
            if current_version != expected_version:
                raise OwnershipConflictError(
                    f"ownership version mismatch: session={session_id} "
                    f"expected={expected_version} actual={current_version}"
                )
            pages_raw = self._load_json_field(row["page_ids_json"], default=[])
            page_ids = (
                tuple(str(item) for item in pages_raw)
                if isinstance(pages_raw, list)
                else ()
            )
            if normalized in page_ids:
                return self._record(row)
            merged = page_ids + (normalized,)
            version = current_version + 1
            connection.execute(
                """
                UPDATE sessions SET version=?, page_ids_json=?
                WHERE session_id=?
                """,
                (
                    version,
                    json.dumps(merged, separators=(",", ":")),
                    session_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO ownership_resources(
                    session_id, resource_key, resource_kind, resource_value,
                    version, updated_at
                ) VALUES (?, ?, 'page', ?, ?, ?)
                ON CONFLICT(session_id, resource_key) DO UPDATE SET
                    resource_value=excluded.resource_value,
                    version=excluded.version,
                    updated_at=excluded.updated_at
                WHERE excluded.version >= ownership_resources.version
                """,
                (
                    session_id,
                    f"page:{normalized}",
                    normalized,
                    version,
                    touched_at,
                ),
            )
            return self._record(self._required_row(connection, session_id))

    @staticmethod
    def _sync_ownership_resource_rows(
        connection: sqlite3.Connection,
        *,
        session_id: str,
        ownership: SessionOwnership,
        version: int,
        updated_at: float,
    ) -> None:
        rows: list[tuple[str, str, str, str]] = []
        if ownership.browser_context_id:
            rows.append(
                (
                    "browser_context",
                    "browser_context",
                    ownership.browser_context_id,
                )
            )
        if ownership.lease_id:
            rows.append(("lease", "lease", ownership.lease_id))
        if ownership.runtime_id:
            rows.append(("runtime", "runtime", ownership.runtime_id))
        for page_id in ownership.page_ids:
            normalized = page_id.strip()
            if normalized:
                rows.append((f"page:{normalized}", "page", normalized))
        for resource_key, resource_kind, resource_value in rows:
            connection.execute(
                """
                INSERT INTO ownership_resources(
                    session_id, resource_key, resource_kind, resource_value,
                    version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, resource_key) DO UPDATE SET
                    resource_value=excluded.resource_value,
                    version=excluded.version,
                    updated_at=excluded.updated_at
                WHERE excluded.version >= ownership_resources.version
                """,
                (
                    session_id,
                    resource_key,
                    resource_kind,
                    resource_value,
                    version,
                    updated_at,
                ),
            )

    def destroy_ownership(
        self,
        session_id: str,
        owner_token: str,
    ) -> SessionRecord:
        """P0-A destroy: clear keyed ownership in one transaction.

        Physical page/context destroy is performed by the pytest process; this
        ledger-side destroy makes the ownership_cleared seal check observably true.
        """
        with self._connect() as connection:
            begin_immediate(connection)
            row = self._owned_row(connection, session_id, owner_token)
            version = int(row["version"]) + 1
            pages_raw = StoreBase._load_json_field(row["page_ids_json"], default=[])
            closed_pages = (
                tuple(str(item) for item in pages_raw)
                if isinstance(pages_raw, list)
                else ()
            )
            closed_context = str(row["browser_context_id"])
            self._clear_session_ownership(connection, session_id=session_id)
            connection.execute(
                "UPDATE sessions SET version=? WHERE session_id=?",
                (version, session_id),
            )
            self._event(
                connection,
                session_id=session_id,
                version=version,
                event_type="DESTROY_SESSION",
                state=SessionState(str(row["state"])),
                detail={
                    "closed_page_ids": closed_pages,
                    "closed_context_id": closed_context,
                },
                now=time.time(),
            )
            return self._record(self._required_row(connection, session_id))
