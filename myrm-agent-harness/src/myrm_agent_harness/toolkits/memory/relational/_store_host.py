"""Typed host contract of the SQLiteRelationalStore operation mixins.

[INPUT]
- aiosqlite::Connection (POS: the connection the mixins run their statements on)
- toolkits.memory.types::MemoryScope (POS: the scope a write is tagged with)

[OUTPUT]
- SQLiteStoreHost: base of the profile, rule and pending mixins; declares the connection, error and scope helpers
  that SQLiteRelationalStore provides to them. Type-checking only: at runtime it is `object`, so the MRO of
  SQLiteRelationalStore is unchanged.

[POS]
Single typed declaration of what an operation mixin may rely on from its host, so a mixin does not repeat helper
stubs and a signature drift in the store fails type checking instead of failing at runtime.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

    from myrm_agent_harness.toolkits.memory.types import MemoryScope

    class SQLiteStoreHost:
        async def _get_connection(self) -> aiosqlite.Connection: ...
        async def _handle_query_error(self, op: str, e: Exception) -> None: ...
        async def _ensure_integrity_before_write(self) -> None: ...
        def _scope_values(
            self, scope: MemoryScope | None
        ) -> tuple[str, str, str | None, str | None, str | None, str | None]: ...
        def _scope_filter_sql(self, namespaces: list[str] | None) -> tuple[str, list[str]]: ...
else:
    SQLiteStoreHost = object
