"""Shared data types for the background bash-process registry.

These dataclasses / exception / typing aliases live in a dedicated module
so that:

1. The registry implementation file stays small enough to fit one screen
   of mental working set (logic + I/O without a 400-line type block).
2. Downstream consumers (bash tool, surface tools) can import the
   snapshot type without pulling in the registry singleton and its
   ``atexit`` hook — useful for type-only imports in callsites that
   never spawn jobs.

[INPUT]
- none (imports no other project module)

[OUTPUT]
- BackgroundProcessInfo: Snapshot dataclass exposed to UI/LLM.
- BackgroundQuotaError: Per-session concurrency cap breach.
- OutputTail: What a job's output read returns: the newest lines of each stream and whether older ones fell off.
- FinishListener / ProgressListener: Async callback type aliases used by
  the bash tool to bridge registry lifecycle events into ``ptc_notify`` UI
  updates.
- OUTPUT_RING_LINES / INPUT_WAIT_IDLE_SECONDS: the limits ``bash_process_tool`` reports to the model
  (how many lines of a stream a job keeps, how long a silent job with open stdin waits before it is flagged).

[POS]
PTC-adjacent runtime helper. Pure data types and the limits shared by the registry and the tool's schema and
descriptions — no I/O, no logging.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import NotRequired, TypedDict

# Lines of each stream a job keeps for ``output`` (the newest ones); older lines fall off the ring.
OUTPUT_RING_LINES = 200

# Idle time after last stdout/stderr before a running job is flagged as likely waiting for stdin.
INPUT_WAIT_IDLE_SECONDS = 15.0


def compute_waiting_for_input(
    *,
    status: str,
    last_output_at: float,
    started_at: float,
    stdin_closed: bool,
    stdin_available: bool,
    now: float | None = None,
) -> bool:
    """True when a running job has an open stdin and has been idle long enough."""
    if status != "running" or stdin_closed or not stdin_available:
        return False
    ts = now if now is not None else time.time()
    anchor = last_output_at if last_output_at > 0 else started_at
    return (ts - anchor) >= INPUT_WAIT_IDLE_SECONDS


def build_input_wait_hint(info: BackgroundProcessInfo) -> str:
    """Human-readable nudge when a running job may be blocked on stdin (output poll)."""
    if not info.waiting_for_input:
        return ""
    anchor = info.last_output_at if info.last_output_at > 0 else info.started_at
    idle_sec = max(0, int(time.time() - anchor))
    return (
        f"No new output for {idle_sec}s; this job may be waiting for stdin. "
        "Use write_stdin, submit_stdin, close_stdin, or the Activity panel Send input."
    )


class BackgroundQuotaError(RuntimeError):
    """Raised when a session would exceed its allowed concurrent background jobs."""

    def __init__(self, session_id: str | None, limit: int) -> None:
        super().__init__(f"Session {session_id!r} already has {limit} active background jobs.")
        self.session_id = session_id
        self.limit = limit


class OutputTail(TypedDict):
    """The newest lines of a job's two streams, as ``get_output`` reads them from the ring tails."""

    stdout: list[str]
    stderr: list[str]
    # True once a stream produced more lines than its ring holds: the oldest lines are missing from this view.
    dropped: bool
    # Where the full output was written; present only when ``dropped`` and the job has a log.
    spill_log_ref: NotRequired[str]


@dataclass
class BackgroundProcessInfo:
    """Snapshot of a tracked background process (LLM/UI consumable).

    ``last_progress`` is the most recent ptc_notify payload distilled out of
    stdout/stderr (explicit ``MYRM_PROGRESS`` marker or heuristic ``42%`` /
    ``3/10 tests`` parse). It lets ``bash_process_tool`` list action answer the
    "how far along is each background job?" question in a single token-cheap
    call instead of forcing the LLM to follow up with one
    ``bash_process_tool(action='output')`` per pid. The ``updated_at`` epoch second is
    embedded by the registry so a multi-minute-old snapshot is recognisable
    without extra bookkeeping.

    ``leftover_processes`` counts the processes found still running in the job's
    process group: after a finished job (detached daemons) or after a kill that
    did not reach them. Zero means none was found; a process that started its
    own session is not looked for.
    """

    job_id: str
    pid: int
    command: str
    session_id: str | None
    started_at: float
    status: str  # "running" | "exited" | "killed"
    vault_log_ref: str | None = None
    exit_code: int | None = None
    error_category: str | None = None
    last_stdout_tail: list[str] = field(default_factory=list)
    last_stderr_tail: list[str] = field(default_factory=list)
    last_progress: dict[str, object] | None = None
    last_output_at: float = 0.0
    waiting_for_input: bool = False
    stdin_closed: bool = False
    leftover_processes: int = 0

    @property
    def uptime_seconds(self) -> float:
        return max(0.0, time.time() - self.started_at)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "job_id": self.job_id,
            "pid": self.pid,
            "command": self.command,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "status": self.status,
            "exit_code": self.exit_code,
            "uptime_seconds": round(self.uptime_seconds, 2),
        }
        if self.error_category is not None:
            payload["error_category"] = self.error_category
        if self.last_progress is not None:
            payload["last_progress"] = self.last_progress
        if self.vault_log_ref is not None:
            payload["vault_log_ref"] = self.vault_log_ref
        if self.leftover_processes:
            payload["leftover_processes"] = self.leftover_processes
        if self.status == "running":
            payload["waiting_for_input"] = self.waiting_for_input
            payload["last_output_at"] = self.last_output_at
            payload["stdin_closed"] = self.stdin_closed
        return payload


FinishListener = Callable[[BackgroundProcessInfo], Awaitable[None]]
ProgressListener = Callable[[BackgroundProcessInfo, dict[str, object]], Awaitable[None]]


__all__ = [
    "INPUT_WAIT_IDLE_SECONDS",
    "OUTPUT_RING_LINES",
    "BackgroundProcessInfo",
    "BackgroundQuotaError",
    "FinishListener",
    "OutputTail",
    "ProgressListener",
    "build_input_wait_hint",
    "compute_waiting_for_input",
]
