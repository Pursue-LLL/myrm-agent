"""CLI session records — which CLI-native conversation a harness session resumes, across turns and restarts.

A CLI backend spawns one process per turn, so context only continues through the CLI's own session id
(``claude --resume <id>``). ``CliSessionBook`` keeps those ids in memory and, when the host supplies a
``CliSessionStore``, writes them through so a new process resumes the same conversation. Persistence is the
host's concern (the harness stays storage-agnostic) and strictly best-effort: a store that fails costs the
conversation its continuity, never the turn.

[INPUT]
- toolkits.acp.types::CliSessionRecord, CliSessionStore (POS: ACP runtime type definitions layer. Provides all ACP-related core abstractions and data structures, serving as the foundation for the entire ACP module.)

[OUTPUT]
- CliSessionBook: memory-first record keeping with best-effort write-through to an optional store

[POS]
Session continuity state of CliRuntime. Owns the bounded in-memory record cache and every store interaction
so the runtime only decides when to remember, persist or forget.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.acp.types import CliSessionRecord, CliSessionStore

logger = logging.getLogger(__name__)

# One record per conversation the backend has served; the oldest is evicted (and stays loadable from the store).
_MAX_RECORDS = 512


class CliSessionBook:
    """The session records of one CLI backend: memory first, an optional store behind it.

    Not thread-safe by design: a backend serves one turn at a time (``RuntimePool`` serializes per backend).
    """

    def __init__(self, owner: str, store: CliSessionStore | None = None) -> None:
        self._owner = owner
        self._store = store
        self._records: dict[str, CliSessionRecord] = {}
        # The record last known to be in the store, so an unchanged record is not rewritten on every turn.
        self._stored: dict[str, CliSessionRecord] = {}
        # Sessions the CLI rejected whose store copy could not be deleted: reading it back would make every turn
        # resume the same dead conversation.
        self._undeleted: set[str] = set()

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, session_id: object) -> bool:
        return session_id in self._records

    def remember(self, session_id: str, record: CliSessionRecord) -> None:
        """Keep ``record`` in memory for ``session_id`` (not persisted until ``persist``)."""
        self._undeleted.discard(session_id)
        if session_id not in self._records and len(self._records) >= _MAX_RECORDS:
            oldest = next(iter(self._records))
            del self._records[oldest]
            self._stored.pop(oldest, None)
        self._records[session_id] = record

    async def resumable(self, session_id: str, cwd: str) -> CliSessionRecord | None:
        """Return the record a turn started in ``cwd`` can resume, loading it from the store on a memory miss."""
        record = self._records.get(session_id)
        if record is None:
            record = await self._load(session_id)
        if record is None:
            return None
        if record.cwd != cwd:
            logger.info(
                "cli_session_cwd_changed name=%s session=%s recorded_cwd=%s cwd=%s",
                self._owner,
                session_id,
                record.cwd,
                cwd,
            )
            return None
        return record

    async def persist(self, session_id: str) -> None:
        """Write the remembered record through to the store unless the store already holds it."""
        record = self._records.get(session_id)
        if record is None or self._store is None or self._stored.get(session_id) == record:
            return
        try:
            await self._store.save(session_id, record)
        except Exception:
            logger.warning("cli_session_save_failed name=%s session=%s", self._owner, session_id, exc_info=True)
            return
        self._stored[session_id] = record

    async def forget(self, session_id: str) -> None:
        """Drop the record from memory and the store (the CLI no longer knows the conversation).

        A store that cannot delete it is not read back from, so the next turn starts a fresh session whose
        record then overwrites the dead one.
        """
        self._records.pop(session_id, None)
        self._stored.pop(session_id, None)
        if self._store is None:
            return
        try:
            await self._store.delete(session_id)
        except Exception:
            logger.warning("cli_session_delete_failed name=%s session=%s", self._owner, session_id, exc_info=True)
            self._undeleted.add(session_id)

    def clear_memory(self) -> None:
        """Release in-memory state; the store keeps its records so a later backend can resume them."""
        self._records.clear()
        self._stored.clear()
        self._undeleted.clear()

    async def _load(self, session_id: str) -> CliSessionRecord | None:
        if self._store is None or session_id in self._undeleted:
            return None
        try:
            record = await self._store.load(session_id)
        except Exception:
            logger.warning("cli_session_load_failed name=%s session=%s", self._owner, session_id, exc_info=True)
            return None
        if record is not None:
            self.remember(session_id, record)
            self._stored[session_id] = record
        return record
