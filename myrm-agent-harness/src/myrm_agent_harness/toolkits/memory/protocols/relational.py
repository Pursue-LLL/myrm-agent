"""Relational store protocol — Profile, Procedural, and Pending memory backend.


[INPUT]
- memory.types::{MemoryScope, MemorySearchResult, PendingRecord, ProceduralMemory, ProfileEntry} (POS: memory data models)

[OUTPUT]
- RelationalStoreProtocol: Protocol for relational storage (Profile/Procedural/Pending backends)

[POS]
Relational store protocol. Defines the relational storage interface for Profile, Procedural,
and Pending memories. Implementations may use PostgreSQL, SQLite, DynamoDB, etc.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from myrm_agent_harness.toolkits.memory.types import (
    MemoryScope,
    MemorySearchResult,
    PendingRecord,
    ProceduralMemory,
    ProfileAttributeSnapshot,
    ProfileEntry,
)


@runtime_checkable
class RelationalStoreProtocol(Protocol):
    """Protocol for relational storage of Profile, Procedural, and Pending memories.

    Implementations may use PostgreSQL, SQLite, DynamoDB, etc.
    """

    # ── Profile ──────────────────────────────────────────────────────

    async def get_profile(self, key: str, *, namespaces: list[str] | None = None) -> str | None: ...

    async def get_profile_snapshot(
        self, key: str, *, namespaces: list[str] | None = None
    ) -> ProfileAttributeSnapshot: ...

    async def set_profile(self, key: str, value: str, *, scope: MemoryScope | None = None) -> None: ...

    async def delete_profile(self, key: str, *, namespaces: list[str] | None = None) -> bool: ...

    async def list_profiles(
        self, *, limit: int = 1000, offset: int = 0, namespaces: list[str] | None = None
    ) -> list[ProfileEntry]: ...

    async def count_profiles(self, *, namespaces: list[str] | None = None) -> int: ...

    # ── Procedural rules ─────────────────────────────────────────────

    async def create_rule(self, rule: ProceduralMemory) -> ProceduralMemory: ...

    async def get_rule(self, rule_id: str, *, namespaces: list[str] | None = None) -> ProceduralMemory | None: ...

    async def search_rules(
        self, query: str, *, limit: int = 10, namespaces: list[str] | None = None
    ) -> list[ProceduralMemory]: ...

    async def list_rules(
        self, *, active_only: bool = True, limit: int = 1000, offset: int = 0, namespaces: list[str] | None = None
    ) -> list[ProceduralMemory]: ...

    async def count_rules(self, *, active_only: bool = True, namespaces: list[str] | None = None) -> int: ...

    async def update_rule(self, rule_id: str, rule: ProceduralMemory) -> ProceduralMemory: ...

    async def delete_rule(self, rule_id: str) -> bool: ...

    async def delete_all(self) -> int: ...

    # ── Pending (approval queue) ─────────────────────────────────────

    async def submit_pending(self, record: PendingRecord) -> str:
        """Persist a pending record. Returns the record ID."""
        ...

    async def get_pending(self, pending_id: str) -> PendingRecord | None:
        """Retrieve a single pending record by ID."""
        ...

    async def pending_exists(self, memory_type: str, content: str) -> bool:
        """Check if an identical pending record already exists (deduplication)."""
        ...

    async def mark_pending(self, pending_id: str, status: str) -> None:
        """Update a pending record's status (approved / rejected)."""
        ...

    async def list_pending(self, *, limit: int = 50) -> list[PendingRecord]:
        """List pending records for a user, newest first."""
        ...

    async def count_pending(self) -> int:
        """Count pending records for a user."""
        ...

    async def batch_mark_pending(self, pending_ids: list[str], status: str) -> int:
        """Batch update status. Returns number of records updated."""
        ...

    async def delete_pending_by_source_chat_id(self, source_chat_id: str) -> int:
        """Delete the pending records raised from one chat. Returns the number removed."""
        ...

    async def count_pending_by_source_chat_id(self, source_chat_id: str) -> int:
        """Count the pending records raised from one chat."""
        ...

    # ── Exact facts & full-text index ────────────────────────────────

    async def record_exact_fact(
        self,
        *,
        memory_id: str,
        user_id: str,
        content: str,
        identifiers: list[str],
        primary_namespace: str = "",
        namespaces: list[str] | None = None,
    ) -> None:
        """Index a memory's exact identifiers and its text for full-text search."""
        ...

    async def delete_exact_fact(self, memory_id: str) -> None:
        """Remove a memory's exact-identifier and full-text index entries."""
        ...

    async def search_fts5(
        self,
        query: str,
        limit: int = 10,
        since: datetime | None = None,
        until: datetime | None = None,
        *,
        namespaces: list[str] | None = None,
    ) -> list[MemorySearchResult]:
        """Match exact identifiers, then full-text search, within the time window."""
        ...

    # ── Diagnostics ──────────────────────────────────────────────────

    async def check_integrity(self) -> tuple[bool, str]:
        """Check the physical and index integrity. Returns ``(is_intact, detail_message)``."""
        ...

    async def close(self) -> None:
        """Release underlying resources (e.g. database session)."""
        ...
