"""Protocol adapter for SQLAlchemyStorage.

Bridges the harness SnapshotStoreProtocol with SQLAlchemyStorage's concrete method signatures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.backends.skills.protocols import SnapshotStoreProtocol

if TYPE_CHECKING:
    from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage


class SnapshotStoreAdapter(SnapshotStoreProtocol):
    """Adapts SQLAlchemyStorage to SnapshotStoreProtocol."""

    def __init__(self, storage: SQLAlchemyStorage):
        self._storage = storage

    async def get_active_version(self, skill_id: str) -> object | None:
        return await self._storage.get_active_version(skill_id)
