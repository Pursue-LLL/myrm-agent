"""Write-scope fence predicate shared by the memory writer and the consolidation cycle.

[INPUT]
- memory.types::MemoryScope (POS: memory scope model; imported for typing only)

[OUTPUT]
- write_grant: The namespaces a writer may target
- within_write_grant: Whether every namespace of a memory lies inside a grant

[POS]
Pure predicate over namespaces. It imports no memory config, so the write path and the compiled strategies can both
depend on it without an import cycle. Internal only — not part of the public API.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.types import MemoryScope


def write_grant(write_scope: MemoryScope, read_namespaces: Sequence[str]) -> frozenset[str]:
    """Namespaces a writer may target: its own write scope plus the shared-capable ones it reads.

    ``global`` and ``shared:*`` are broadcast namespaces, so whoever reads them may write into them; any other
    namespace the writer can read (another agent's private space) stays read-only.
    """
    return frozenset(write_scope.namespaces) | {
        namespace for namespace in read_namespaces if namespace == "global" or namespace.startswith("shared:")
    }


def within_write_grant(namespaces: Iterable[str], grant: frozenset[str]) -> bool:
    """Whether every namespace lies inside ``grant``; an empty grant fences nothing."""
    return not grant or set(namespaces) <= grant


__all__ = ["within_write_grant", "write_grant"]
