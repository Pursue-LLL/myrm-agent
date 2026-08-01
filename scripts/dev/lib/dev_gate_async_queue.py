"""Async command queue with single durable writer for Dev Gate coordinator (P0-D)."""

from __future__ import annotations

import concurrent.futures
import os
import queue
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dev_gate_coordinator import CoordinatorService

DEFAULT_MAX_QUEUE = 1000
_WRITE_OPERATIONS = frozenset(
    {
        "submit",
        "transition",
        "heartbeat",
        "ownership",
        "cleanup",
        "finish",
        "private_admit",
        "private_release",
        "desktop_admit",
        "desktop_release",
        "reap",
    }
)


@dataclass(frozen=True, slots=True)
class _QueueItem:
    request: dict[str, object]
    future: concurrent.futures.Future[dict[str, object]]


class DevGateAsyncWriter:
    """Bounded queue + single writer thread serializing coordinator mutations."""

    def __init__(
        self,
        service: CoordinatorService,
        *,
        max_queue: int = DEFAULT_MAX_QUEUE,
    ) -> None:
        self._service = service
        self._queue: queue.Queue[_QueueItem | None] = queue.Queue(maxsize=max_queue)
        self._thread = threading.Thread(
            target=self._run,
            name="dev-gate-async-writer",
            daemon=True,
        )
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def stop(self, *, timeout_sec: float = 2.0) -> None:
        if not self._started:
            return
        try:
            self._queue.put(None, timeout=timeout_sec)
        except queue.Full:
            pass
        self._thread.join(timeout=timeout_sec)

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    def dispatch(
        self,
        request: dict[str, object],
        *,
        timeout_sec: float = 10.0,
    ) -> dict[str, object]:
        operation = request.get("operation")
        if not isinstance(operation, str) or operation not in _WRITE_OPERATIONS:
            return self._service.handle(request)
        future: concurrent.futures.Future[dict[str, object]] = (
            concurrent.futures.Future()
        )
        item = _QueueItem(request=request, future=future)
        try:
            self._queue.put(item, timeout=timeout_sec)
        except queue.Full as exc:
            raise RuntimeError("DEV_GATE_ASYNC_QUEUE_FULL") from exc
        return future.result(timeout=timeout_sec)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                result = self._service.handle(item.request)
                item.future.set_result(result)
            except Exception as exc:  # noqa: BLE001 — propagate to waiter
                if item is not None:
                    item.future.set_exception(exc)
            finally:
                self._queue.task_done()


def async_queue_enabled() -> bool:
    raw = os.environ.get("MYRM_DEV_GATE_ASYNC_QUEUE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def max_async_queue_depth() -> int:
    raw = os.environ.get("MYRM_DEV_GATE_ASYNC_QUEUE_MAX", "").strip()
    if not raw:
        return DEFAULT_MAX_QUEUE
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_QUEUE
