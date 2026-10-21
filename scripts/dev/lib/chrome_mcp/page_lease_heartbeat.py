"""Keep MCP-owned browser leases alive while their pages are in use."""

from __future__ import annotations

import threading
from collections.abc import Callable


class PageLeaseHeartbeat:
    """Heartbeat tracked page leases and surface failures to foreground calls."""

    def __init__(
        self,
        heartbeat: Callable[[str], None],
        *,
        interval_sec: float,
    ) -> None:
        if interval_sec <= 0:
            raise ValueError("page lease heartbeat interval must be positive")
        self._heartbeat = heartbeat
        self._interval_sec = interval_sec
        self._lock = threading.Lock()
        self._lease_ids: set[str] = set()
        self._failure: RuntimeError | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop = threading.Event()
            self._failure = None
            self._thread = threading.Thread(
                target=self._run,
                name="mcp-page-lease-heartbeat",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop.set()
        if thread is not None:
            thread.join(timeout=11.0)

    def track(self, lease_id: str) -> None:
        with self._lock:
            self._lease_ids.add(lease_id)

    def untrack(self, lease_id: str) -> None:
        with self._lock:
            self._lease_ids.discard(lease_id)

    def raise_if_failed(self) -> None:
        with self._lock:
            failure = self._failure
        if failure is not None:
            raise failure

    def heartbeat_once(self) -> None:
        with self._lock:
            lease_ids = tuple(self._lease_ids)
        for lease_id in lease_ids:
            try:
                self._heartbeat(lease_id)
            except (RuntimeError, TimeoutError) as exc:
                with self._lock:
                    if lease_id not in self._lease_ids:
                        continue
                    self._failure = RuntimeError(
                        f"PAGE_LEASE_HEARTBEAT_FAILED: leaseId={lease_id}: {exc}"
                    )
                return

    def _run(self) -> None:
        while not self._stop.wait(self._interval_sec):
            self.heartbeat_once()
