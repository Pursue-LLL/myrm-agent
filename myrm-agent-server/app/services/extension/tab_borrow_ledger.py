"""Tab borrowing ledger for browser extension mode.

[INPUT]
- asyncio, collections.abc, dataclasses, logging, time

[OUTPUT]
- BorrowedTabRecord: Immutable dataclass recording original tab position
- TabBorrowLedger: Ledger service managing borrowed tab life cycle and auto-return

[POS]
app.services.extension.tab_borrow_ledger: Extension tab lease coordinator.
Maintains original tab window and index positions when the Agent borrows
a user's everyday browser tab, ensuring seamless auto-return upon completion
or disconnection, preserving the user's workspace order.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import logging
import time

logger = logging.getLogger(__name__)

_DEFAULT_BORROW_TTL = 7200.0  # 2 hours default TTL for orphan cleanups


@dataclass(frozen=True)
class BorrowedTabRecord:
    """Record of a tab borrowed by the Agent.

    Attributes:
        tab_id: Chrome internal tab ID.
        original_window_id: Initial window ID when borrowed.
        original_index: Initial tab index within the window.
        borrowed_at: Monotonic timestamp of the first borrow.
    """

    tab_id: int
    original_window_id: int
    original_index: int
    borrowed_at: float = field(default_factory=time.monotonic)


class TabBorrowLedger:
    """State machine tracking borrowed tabs and orchestrating idempotent auto-return."""

    def __init__(self, ttl: float = _DEFAULT_BORROW_TTL) -> None:
        self._ttl = ttl
        self._records: dict[int, BorrowedTabRecord] = {}
        self._lock = asyncio.Lock()

    def record_borrow(self, tab_id: int, window_id: int, index: int) -> bool:
        """Record tab borrow with First-Borrow Freeze semantics.

        If the tab is already borrowed, maintains the original coordinates
        and only updates freshness.

        Returns:
            True if this was a new borrow; False if already recorded.
        """
        self._prune_expired()
        if tab_id in self._records:
            return False

        self._records[tab_id] = BorrowedTabRecord(
            tab_id=tab_id,
            original_window_id=window_id,
            original_index=index,
        )
        logger.info(
            "Recorded tab borrow: tab_id=%d -> (window_id=%d, index=%d)",
            tab_id,
            window_id,
            index,
        )
        return True

    def get_borrowed_record(self, tab_id: int) -> BorrowedTabRecord | None:
        """Get borrow record for a specific tab if active."""
        self._prune_expired()
        return self._records.get(tab_id)

    def list_active_borrows(self) -> list[BorrowedTabRecord]:
        """List all currently active tab borrow records."""
        self._prune_expired()
        return list(self._records.values())

    async def restore_tab(
        self,
        tab_id: int,
        send_move_fn: Callable[[int, int, int], Awaitable[bool]],
        timeout: float = 1.5,
    ) -> bool:
        """Restore a borrowed tab to its original window and index.

        Args:
            tab_id: Target Chrome tab ID.
            send_move_fn: Async callable(tab_id, window_id, index) -> bool.
            timeout: Non-blocking timeout guard for dispatch.

        Returns:
            True if restored or peacefully forgotten; False on failure.
        """
        async with self._lock:
            record = self._records.pop(tab_id, None)
            if record is None:
                return False

            try:
                coro = send_move_fn(record.tab_id, record.original_window_id, record.original_index)
                res = await asyncio.wait_for(coro, timeout=timeout)
                logger.info(
                    "Restored tab %d to window %d index %d (result=%s)",
                    record.tab_id,
                    record.original_window_id,
                    record.original_index,
                    res,
                )
                return bool(res)
            except TimeoutError:
                logger.warning(
                    "Timeout (%.1fs) restoring tab %d to original position; dropped from ledger",
                    timeout,
                    record.tab_id,
                )
                return False
            except Exception as exc:
                logger.debug("Suppressed error restoring tab %d: %s", record.tab_id, exc)
                return False

    async def restore_all(
        self,
        send_move_fn: Callable[[int, int, int], Awaitable[bool]],
        timeout_per_tab: float = 1.0,
    ) -> int:
        """Restore all borrowed tabs sequentially with timeout guards.

        Returns:
            Count of tabs attempted to restore.
        """
        async with self._lock:
            to_restore = list(self._records.values())
            self._records.clear()

        restored_count = 0
        for rec in to_restore:
            try:
                coro = send_move_fn(rec.tab_id, rec.original_window_id, rec.original_index)
                await asyncio.wait_for(coro, timeout=timeout_per_tab)
                restored_count += 1
            except Exception as exc:
                logger.debug("Failed restoring tab %d during restore_all: %s", rec.tab_id, exc)

        if restored_count > 0:
            logger.info("Restored %d borrowed tab(s) to original coordinates", restored_count)
        return restored_count

    def clear(self) -> None:
        """Clear all records without dispatching move requests."""
        self._records.clear()

    def _prune_expired(self) -> None:
        """Purge expired records exceeding TTL."""
        now = time.monotonic()
        expired_keys = [
            tid for tid, rec in self._records.items() if (now - rec.borrowed_at) > self._ttl
        ]
        for tid in expired_keys:
            del self._records[tid]


_ledger_singleton: TabBorrowLedger | None = None


def get_tab_borrow_ledger() -> TabBorrowLedger:
    """Get the process-wide TabBorrowLedger singleton."""
    global _ledger_singleton
    if _ledger_singleton is None:
        _ledger_singleton = TabBorrowLedger()
    return _ledger_singleton
