"""In-flight agent runs that ``AgentGateway`` does not count.

[INPUT]
- myrm_agent_harness.agent.sub_agents.manager::ACTIVE_SUBAGENTS (POS: sub-agent tasks spawned and not yet finished)

[OUTPUT]
- track_background_agent_run: context manager marking one gateway-less agent run as in flight
- active_background_agent_runs: gateway-less runs executing now plus running sub-agent tasks

[POS]
Cron, kanban, IM channel and eval runs call the agent pipeline directly, so the gateway's active
count never sees them, and a detached sub-agent keeps running after the turn that spawned it
ended. The liveness endpoint reports the sandbox as busy while any of them runs, which is what the
hosted idle recycler reads before pausing the container (a pause freezes the run mid-way); the manual
environment reset refuses on it too, since the container swap kills whatever is still running.

Callers wrap the scope that consumes ``process_stream`` in ``track_background_agent_run``. The count
is released as soon as that block ends; when the block sits inside an async generator whose consumer
stops early, it is released at generator finalization, a few event-loop iterations later. Every
``process_stream`` call site is accounted for by ``tests/architecture/test_agent_run_tracking.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from myrm_agent_harness.agent.sub_agents.manager import ACTIVE_SUBAGENTS

_active_runs = 0


@contextmanager
def track_background_agent_run() -> Iterator[None]:
    """Mark one gateway-less agent run as in flight for the duration of the block."""
    global _active_runs
    _active_runs += 1
    try:
        yield
    finally:
        _active_runs -= 1


def active_background_agent_runs() -> int:
    """Gateway-less agent runs executing in this process plus running sub-agent tasks."""
    return _active_runs + len(ACTIVE_SUBAGENTS)
