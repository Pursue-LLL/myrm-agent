"""Shared mutable context of one sync slice.

[INPUT]
- .client / .ledger / .state (POS: ima reads, ledger, resumable state)
- .errors (POS: failure taxonomy the key check reads)
- app.database.connection::get_session (POS: DB sessions)

[OUTPUT]
- SyncContext: everything a slice needs, plus the time budget, throttled state persistence, the once-per-slice
  key check (``require_valid_key``) and the item-failure tally behind the slice's single log line

[POS]
Keeps inventory, import and engine decoupled: each takes the context instead of a long argument list.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.database.connection import get_session

from .client import ImaClient
from .errors import ImaAuthError, ImaError, ImaRateLimitError, ImaTransientError
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
    failures: Counter[str] = field(default_factory=Counter)
    failure_sample: str = ""
    _last_persist: float = field(default_factory=time.monotonic)
    _key_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _key_checked: bool = False
    _key_valid: bool | None = None

    def time_left(self) -> float:
        return self.deadline - time.monotonic()

    def note_failure(self, kind: str, cause: str) -> None:
        """Count one item failure toward the slice's log line; the first cause stays as its sample."""
        self.failures[kind] += 1
        self.failure_sample = self.failure_sample or cause

    async def require_valid_key(self, rejection: ImaAuthError) -> None:
        """Return when ima refused one request although the key itself works; raise ``rejection`` when the key is bad.

        ima refuses a resource the key may not read (a library shared without access, a teammate's note) exactly like a
        revoked key. One cheap authenticated call per slice, shared by every worker, tells the two apart. When even that
        call fails, the rejection is neither accepted nor dismissed: it surfaces as a transient failure to retry. A rate
        limit raised by the check propagates so the engine can pause.
        """
        valid = await self._key_is_valid()
        if valid is False:
            raise rejection
        if valid is None:
            raise ImaTransientError("ima refused a request and the key could not be checked") from rejection

    async def _key_is_valid(self) -> bool | None:
        async with self._key_lock:
            if not self._key_checked:
                try:
                    await self.client.verify()
                    self._key_valid = True
                except ImaAuthError:
                    self._key_valid = False
                except ImaRateLimitError:
                    raise
                except ImaError:
                    self._key_valid = None
                self._key_checked = True
            return self._key_valid

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
