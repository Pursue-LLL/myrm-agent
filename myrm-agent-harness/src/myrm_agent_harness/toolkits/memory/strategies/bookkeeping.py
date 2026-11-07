"""Direct reads and writes of the maintenance bookkeeping rows (``_system.*`` profile keys).

[INPUT]
- memory._internal.scope::resolve_primary_namespace (POS: durable owner namespace of a namespace chain)
- memory.manager::MemoryManager (POS: unified memory manager facade)
- memory.types::MemoryScope (POS: memory data models)

[OUTPUT]
- read_bookkeeping: Read a bookkeeping value from the manager's owner namespace
- write_bookkeeping: Write a bookkeeping value to the manager's owner namespace

[POS]
Persistence of maintenance counters, hashes and timestamps. Deliberately bypasses the profile
governance path: bookkeeping is system state, so it must not enter the approval queue, the
injection scan or the ephemeral delta appended to the chat context. Rows are keyed by the
manager's owner namespace (project, client or agent scope, else global), so a conversation-scoped
write policy never fragments them and a project-bound manager never reads or overwrites the
global manager's rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.types import MemoryScope

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager


def _owner_namespace(manager: MemoryManager) -> str:
    """The broadest durable namespace the manager owns, never a write-policy target such as a conversation."""
    # Deferred: `_internal.scope` needs `memory.config`, and `memory.config` imports this package while loading.
    from myrm_agent_harness.toolkits.memory._internal.scope import resolve_primary_namespace

    return resolve_primary_namespace(manager.namespaces)


async def read_bookkeeping(manager: MemoryManager, key: str) -> str | None:
    """Return the value stored under ``key`` in the manager's owner namespace, if any."""
    return await manager._rel().get_profile(key, namespaces=[_owner_namespace(manager)])


async def write_bookkeeping(manager: MemoryManager, key: str, value: str) -> None:
    """Store ``value`` under ``key`` in the manager's owner namespace."""
    namespace = _owner_namespace(manager)
    await manager._rel().set_profile(key, value, scope=MemoryScope(primary_namespace=namespace, namespaces=[namespace]))


__all__ = ["read_bookkeeping", "write_bookkeeping"]
