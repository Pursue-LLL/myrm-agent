"""Protocol adapters for SQLAlchemyStorage.

Bridges the harness SnapshotStoreProtocol/ABTestStoreProtocol with
SQLAlchemyStorage's concrete method signatures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.backends.skills.protocols import ABTestStoreProtocol, SnapshotStoreProtocol

if TYPE_CHECKING:
    from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage


class SnapshotStoreAdapter(SnapshotStoreProtocol):
    """Adapts SQLAlchemyStorage to SnapshotStoreProtocol."""

    def __init__(self, storage: SQLAlchemyStorage):
        self._storage = storage

    async def get_version(self, skill_id: str, version: int) -> object | None:
        return await self._storage.get_skill_version(skill_id, version)

    async def get_active_version(self, skill_id: str) -> object | None:
        return await self._storage.get_active_version(skill_id)


class ABTestStoreAdapter(ABTestStoreProtocol):
    """Adapts SQLAlchemyStorage to ABTestStoreProtocol."""

    def __init__(self, storage: SQLAlchemyStorage):
        self._storage = storage

    async def get_running_tests(self) -> list[object]:
        return await self._storage.get_running_ab_tests()
