"""[POS]: app/services/memory/tombstone/__init__.py
[INPUT]: None.
[OUTPUT]: Public exports for MemoryTombstoneProvider and FastAPI dependency provider.
"""

from app.services.memory.tombstone.provider import (
    MemoryTombstoneProvider,
    get_tombstone_curation_service,
)

__all__ = [
    "MemoryTombstoneProvider",
    "get_tombstone_curation_service",
]
