"""Bounded access to the backup folder, so one that stops answering cannot use up the app's shared thread pool.

[INPUT]
- Python standard library only (threads, events and a queue)

[OUTPUT]
- FolderGuard: ``call`` runs one folder operation on a private thread and waits for it at most ``timeout`` seconds;
  ``call_progressing`` runs a long one and waits as long as it keeps reporting progress
- Pulse: handed to a progressing operation; ``progress()`` reports a sign of life and tells it when the caller gave up
- FolderUnresponsive: raised when the folder did not answer in time; an ``OSError``, so it reads as "cannot be read"
- FOLDER_TIMEOUT_SECONDS: how long a caller waits by default

[POS]
Bounded access to the user-chosen backup folder. Each call runs on one private daemon thread and the caller waits only
while the folder answers: a short call for at most a timeout, a long transfer for as long as it keeps reporting progress.
A share that stops answering therefore cannot pin the threads the rest of the app shares.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar, cast

FOLDER_TIMEOUT_SECONDS = 10.0
_POLL_SECONDS = 1.0  # how often a caller waiting on a progressing call looks for a sign of life

_T = TypeVar("_T")


class FolderUnresponsive(OSError):
    """The folder did not answer in time."""


@dataclass(eq=False, slots=True)
class _Job:
    operation: Callable[[Pulse], object]
    alive_at: float  # monotonic time of the operation's last sign of life; its start counts as one
    done: threading.Event = field(default_factory=threading.Event)
    result: object = None
    error: BaseException | None = None
    abandoned: bool = False  # the caller stopped waiting, so nobody needs the outcome


def _outcome(job: _Job) -> object:
    if job.error is not None:
        raise job.error
    return job.result


class Pulse:
    """Given to the operation of ``FolderGuard.call_progressing``: its way to show it is still moving."""

    __slots__ = ("_job",)

    def __init__(self, job: _Job) -> None:
        self._job = job

    def progress(self) -> None:
        """Report a sign of life. Raises ``FolderUnresponsive`` once the caller has given up, so the operation winds
        down instead of finishing work nobody waits for."""
        if self._job.abandoned:
            raise FolderUnresponsive("The caller stopped waiting")
        self._job.alive_at = time.monotonic()


class FolderGuard:
    """Runs folder operations one at a time on a private thread; callers wait for it at most ``timeout`` seconds.

    A hard-mounted share whose server is gone blocks every file call on it until the server returns, and a thread stuck
    in the kernel can neither be interrupted nor killed. Callers therefore give up instead of waiting it out, a call that
    gave up before its turn never runs, and while the running call has been stuck for longer than ``timeout`` the next
    callers fail at once. The thread is a daemon because the interpreter joins the workers of a ``ThreadPoolExecutor``
    at exit, and a stuck one would keep the app from closing; it leaves as soon as nothing is waiting.

    ``call`` is for short operations that are safe to abandon: listing the folder, creating and probing it, and
    removing the backups beyond the retained ones.
    ``call_progressing`` is for one that legitimately takes long, such as writing a large file: it is given up on only
    after ``timeout`` seconds without a sign of life, however long it has run in all. It must report through its
    ``Pulse`` at least that often and stop when told it was given up on, since the thread cannot be taken from it.
    A guard serves one kind of work, so a long transfer never queues the short calls behind it.
    """

    def __init__(self, timeout: float = FOLDER_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._lock = threading.Lock()
        self._queue: deque[_Job] = deque()
        self._worker: threading.Thread | None = None
        self._running: _Job | None = None  # the operation the worker is inside

    def call(self, operation: Callable[[], _T]) -> _T:
        """Run ``operation`` on the private thread. Raises ``FolderUnresponsive`` after ``timeout`` seconds, or at
        once while the operation already running has been stuck for longer than that; its own errors pass through."""
        job = self._submit(lambda _: operation())
        if not job.done.wait(self._timeout):
            job.abandoned = True
            raise FolderUnresponsive("The folder did not respond in time")
        return cast("_T", _outcome(job))

    def call_progressing(self, operation: Callable[[Pulse], _T]) -> _T:
        """Run ``operation`` on the private thread and wait for it while it reports progress. Raises
        ``FolderUnresponsive`` after ``timeout`` seconds without a sign of life, or at once while the operation
        already running has been silent for longer than that; its own errors pass through."""
        job = self._submit(operation)
        if not self._wait_while_alive(job):
            job.abandoned = True
            raise FolderUnresponsive("The folder stopped making progress")
        return cast("_T", _outcome(job))

    def _submit(self, operation: Callable[[Pulse], object]) -> _Job:
        job = _Job(operation, alive_at=time.monotonic())
        with self._lock:
            running = self._running
            if running is not None and time.monotonic() - running.alive_at > self._timeout:
                raise FolderUnresponsive("The folder is not responding")
            self._queue.append(job)
            if self._worker is None:
                worker = threading.Thread(target=self._drain, name="auto-backup-folder", daemon=True)
                try:
                    worker.start()
                except BaseException:
                    self._queue.pop()
                    raise
                self._worker = worker  # still under the lock, which the worker needs before it can look at ``_worker``
        return job

    def _wait_while_alive(self, job: _Job) -> bool:
        """True once ``job`` is done; False when it has shown no sign of life for ``timeout`` seconds."""
        step = min(self._timeout / 10, _POLL_SECONDS)
        woke = time.monotonic()
        while not job.done.wait(step):
            now = time.monotonic()
            if now - woke > self._timeout / 2:
                # This thread stood still, not just the folder: the machine slept, and where the clock counts that
                # time the operation would look silent for all of it. Nothing is known about the folder since.
                job.alive_at = now
            elif now - job.alive_at > self._timeout:
                return False
            woke = now
        return True

    def _drain(self) -> None:
        while True:
            with self._lock:
                while self._queue and self._queue[0].abandoned:
                    self._queue.popleft()
                if not self._queue:
                    self._worker = None
                    return
                job = self._queue.popleft()
                job.alive_at = time.monotonic()
                self._running = job
            try:
                job.result = job.operation(Pulse(job))
            except BaseException as exc:  # handed to the caller, which raises it there
                job.error = exc
            with self._lock:
                self._running = None
            job.done.set()
