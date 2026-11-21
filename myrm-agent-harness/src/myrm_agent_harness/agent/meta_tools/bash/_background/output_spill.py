"""Log of one background job's output: every line as printed, from the first, once a read could cut the output.

[INPUT]
- agent.context_management.infra.evicted::MAX_STORED_CHARS, resolve_evicted_target, format_storage_cap_marker (POS: where an evicted file lives, how large it may grow, the line a capped file ends with)
- agent.meta_tools.bash._background.output_window::WINDOW_MAX_CHARS (POS: the size of the window a read shows)

[OUTPUT]
- BackgroundOutputSpillWriter: buffered log writer of one job; ``vault_log_ref`` names the file once it exists, ``close`` writes the tail

[POS]
Full-output half of the output chain. The rings keep the newest lines for reads; the log keeps all of them (up to the cap) at the place the foreground evicted files use, so the activity panel and the file read tool open it the same way.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from typing import TextIO

from myrm_agent_harness.agent.context_management.infra.evicted import (
    MAX_STORED_CHARS,
    format_storage_cap_marker,
    resolve_evicted_target,
)
from myrm_agent_harness.agent.meta_tools.bash._background.output_window import WINDOW_MAX_CHARS

logger = logging.getLogger(__name__)

# The file is created at this many lines, or sooner when the lines are long enough that a read would cut them.
_SPILL_LINE_THRESHOLD = 80
# What waits for a write never exceeds a ring (200 lines per stream) or a read's window (``WINDOW_MAX_CHARS``), so a
# line that is not yet in the file is still in what a read shows: a read that reports dropped lines finds the rest in
# one of the two.
_FLUSH_LINES = 128
_FLUSH_INTERVAL_SECONDS = 0.5


class BackgroundOutputSpillWriter:
    """Writes a job's lines, as printed, to a log file; the head is held in memory until the output is long enough.

    A failure to create or write the file closes the log and nothing else: the job and its reader go on.
    """

    def __init__(self, *, job_id: str, path: Path) -> None:
        self._job_id = job_id
        self._path = path
        self._file: TextIO | None = None
        self._created = False
        self._closed = False
        self._capped = False
        self._pending: list[str] = []
        self._pending_chars = 0
        self._lines = 0
        self._seen_chars = 0
        self._written_chars = 0
        self._timer: asyncio.TimerHandle | None = None

    @classmethod
    def for_session(cls, *, session_id: str | None, job_id: str) -> BackgroundOutputSpillWriter | None:
        """The writer for a job of ``session_id``, or ``None`` when there is no session or no workspace to write into."""
        if not session_id:
            return None
        target = resolve_evicted_target("output", "txt", chat_id=session_id)
        if target is None:
            return None
        return cls(job_id=job_id, path=target[2])

    @property
    def vault_log_ref(self) -> str | None:
        """Basename the evicted-file API serves; ``None`` until the file exists."""
        return self._path.name if self._created else None

    def append_line(self, stream: str, text: str) -> None:
        if self._closed:
            return
        line = f"[stderr] {text}\n" if stream == "stderr" else f"{text}\n"
        self._lines += 1
        self._seen_chars += len(line)
        if self._capped:
            return
        self._pending.append(line)
        self._pending_chars += len(line)
        if (
            self._pending_chars >= WINDOW_MAX_CHARS
            or len(self._pending) >= _FLUSH_LINES
            or (not self._created and self._lines >= _SPILL_LINE_THRESHOLD)
        ):
            self._flush()
        elif self._created:
            self._arm_timer()

    def close(self) -> None:
        """The job is over: write what is waiting, the cap marker when the file was cut, and release the file.

        A job that never reached the point of a log leaves no file.
        """
        if self._closed:
            return
        if self._created:
            self._flush()
        self._disarm_timer()
        file, self._file = self._file, None
        self._closed = True
        self._pending.clear()
        if file is None:
            return
        try:
            if self._capped:
                file.write(format_storage_cap_marker(cap=MAX_STORED_CHARS, original=self._seen_chars))
            file.close()
        except (OSError, UnicodeError) as exc:
            logger.warning("Background job log close failed job=%s: %s", self._job_id, exc)

    def _flush(self) -> None:
        """Write the waiting lines; the first write creates the file."""
        self._disarm_timer()
        if self._closed or not self._pending:
            return
        text = "".join(self._pending)
        self._pending.clear()
        self._pending_chars = 0
        room = MAX_STORED_CHARS - self._written_chars
        if len(text) > room:
            text = text[:room]
            self._capped = True
        try:
            if self._file is None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._file = self._path.open("x", encoding="utf-8", errors="replace")
                self._created = True
            self._file.write(text)
            self._file.flush()
        except (OSError, UnicodeError) as exc:
            self._fail(exc)
            return
        self._written_chars += len(text)

    def _fail(self, exc: Exception) -> None:
        logger.warning("Background job log write failed job=%s: %s", self._job_id, exc)
        self._pending.clear()
        self._pending_chars = 0
        self._closed = True
        file, self._file = self._file, None
        if file is not None:
            with suppress(OSError):
                file.close()

    def _arm_timer(self) -> None:
        if self._timer is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._timer = loop.call_later(_FLUSH_INTERVAL_SECONDS, self._flush)

    def _disarm_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


__all__ = ["BackgroundOutputSpillWriter"]
