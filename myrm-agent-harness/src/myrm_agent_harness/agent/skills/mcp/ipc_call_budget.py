"""Tool-call budget for MCP PTC scripts

[INPUT]
- (none)

[OUTPUT]
- DEFAULT_MAX_CALLS_PER_EXECUTION / DEFAULT_SESSION_CALL_CEILING / SESSION_CALL_WINDOW_SECONDS:
  Default limits and the session window length.
- CallBudget: Per-execution budget plus a per-session backstop; ``consume`` charges one
  call and returns an error message when a limit is hit.

[POS]
Admission control of the MCP IPC server, kept apart from the transport so the limits
can be reasoned about (and tested) without a socket.
"""

import time
from collections import OrderedDict
from dataclasses import dataclass

DEFAULT_MAX_CALLS_PER_EXECUTION = 50
"""Tool-call budget of one script execution (one client process, keyed by its trace id).

MCP PTC scripts loop over tools; without a ceiling a runaway script becomes an
unbounded external-API amplifier. 50 matches ``PtcConfig.max_tool_calls``, so both PTC
tracks share one number with one meaning: measured orchestration scripts on this
machine issue 0-3 callsites, so the ceiling only ever catches a runaway loop. The
budget is per execution because a chat runs many scripts over its lifetime; a
chat-wide counter would permanently lock the chat out of MCP after 50 calls in total.
"""

DEFAULT_SESSION_CALL_CEILING = 500
SESSION_CALL_WINDOW_SECONDS = 600.0
"""Backstop: calls one session may make across all its scripts within one window.

A script controls its own trace id, so the per-execution budget alone can be sidestepped
by re-keying (or by spawning child processes). This ceiling keeps that from becoming an
unbounded amplifier again. It is not a security boundary (read-only, path and scope
policies run on every call regardless of count) and the number is a deliberately loose
10x of the per-execution budget, not a measured workload limit.
"""

_MAX_TRACKED_BUCKETS = 1024
"""Bound on remembered executions / sessions; the oldest bucket is evicted first."""

_TRACE_KEY_CHARS = 64
"""Trace ids come from the script; clamp them so a bucket key cannot grow the table."""


@dataclass(slots=True)
class _CallWindow:
    """Calls one session made since ``started_at`` (monotonic seconds)."""

    started_at: float
    calls: int = 0


def _remember[T](buckets: OrderedDict[str, T], key: str, value: T) -> None:
    """Store ``value`` as the newest entry, evicting the oldest beyond the bucket bound."""
    buckets[key] = value
    buckets.move_to_end(key)
    while len(buckets) > _MAX_TRACKED_BUCKETS:
        buckets.popitem(last=False)


class CallBudget:
    """Accounts tool calls per script execution and per session window."""

    def __init__(
        self,
        max_calls_per_execution: int = DEFAULT_MAX_CALLS_PER_EXECUTION,
        session_call_ceiling: int = DEFAULT_SESSION_CALL_CEILING,
    ) -> None:
        self._max_calls_per_execution = max_calls_per_execution
        self._session_call_ceiling = session_call_ceiling
        self._execution_calls: OrderedDict[str, int] = OrderedDict()
        self._session_windows: OrderedDict[str, _CallWindow] = OrderedDict()

    def consume(self, session_id: str | None, trace_id: str) -> str | None:
        """Account one tool call against the execution budget and the session ceiling.

        The budget belongs to one script execution (``trace_id``), so a script that
        legitimately makes many calls never starves the scripts that follow it in the
        same chat. The session ceiling is the backstop for a script that re-keys its
        trace id. A request without ``trace_id`` / ``session_id`` has no such bucket and
        is not charged against it (the caller is already constrained by the
        authenticated socket and the per-call policies).

        Returns an error message when a limit is hit, else ``None``. Nothing is charged
        on rejection.
        """
        execution_key = trace_id[:_TRACE_KEY_CHARS]
        executed = self._execution_calls.get(execution_key, 0)
        if execution_key and executed >= self._max_calls_per_execution:
            return (
                f"Script tool-call budget exhausted: {executed}/{self._max_calls_per_execution} "
                "calls made in this execution. Summarise results and finish the script."
            )

        window = self._session_window(session_id) if session_id else None
        if window is not None and window.calls >= self._session_call_ceiling:
            return (
                f"Session tool-call ceiling reached: {window.calls} calls within "
                f"{SESSION_CALL_WINDOW_SECONDS:.0f}s across scripts. "
                "Stop calling MCP tools from scripts and report what you have."
            )

        if execution_key:
            _remember(self._execution_calls, execution_key, executed + 1)
        if window is not None:
            window.calls += 1
        return None

    def _session_window(self, session_id: str) -> _CallWindow:
        """Return the session's live call window, opening a new one once it expired."""
        now = time.monotonic()
        window = self._session_windows.get(session_id)
        if window is None or now - window.started_at >= SESSION_CALL_WINDOW_SECONDS:
            window = _CallWindow(started_at=now)
        _remember(self._session_windows, session_id, window)
        return window
