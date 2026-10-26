"""Shared mutable context of one sync slice.

[INPUT]
- .client / .ledger / .state (POS: ima reads, ledger, resumable state)
- app.database.connection::get_session (POS: DB sessions)

[OUTPUT]
- SyncContext: everything a slice needs, plus the time budget and throttled state persistence

[POS]
Keeps inventory, import and engine decoupled: each takes the context instead of a long argument list.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.database.connection import get_session

from .client import ImaClient
from .identity import NOTES_LANE
from .ledger import ImaLedger
from .state import ImaSyncConfig, ImaSyncState, save_ima_state

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki import WikiStructure

_PERSIST_INTERVAL_S = 15.0


@dataclass(slots=True)
class SyncContext:
    agent_id: str | None
    client: ImaClient
    structure: WikiStructure
    config: ImaSyncConfig
    state: ImaSyncState
    ledger: ImaLedger
    deadline: float
    compiler_enqueue: object | None = None
    _last_persist: float = field(default_factory=time.monotonic)

    def time_left(self) -> float:
        return self.deadline - time.monotonic()

    @property
    def containers(self) -> list[str]:
        """Containers this agent currently imports; rows of deselected libraries are left untouched."""
        containers = [kb.id for kb in self.config.knowledge_bases]
        if self.config.include_notes:
            containers.append(NOTES_LANE)
        return containers

    def raw_exists(self, relative_path: str) -> bool:
        try:
            return self.structure.get_raw_file_path(relative_path).exists()
        except ValueError:
            return False

    async def persist_state(self, *, force: bool = False) -> None:
        """Inventory pages arrive faster than the state needs saving; throttling bounds the rewrite cost of a large queue."""
        now = time.monotonic()
        if not force and now - self._last_persist < _PERSIST_INTERVAL_S:
            return
        async with get_session() as db:
            await save_ima_state(db, self.state, agent_id=self.agent_id)
        self._last_persist = now
