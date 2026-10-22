"""The wiki maintain run of each vault scope: single flight plus the state the Settings page polls.

[INPUT]
- myrm_agent_harness.toolkits.wiki.maintenance.progress (POS: phase/progress DTOs reported by the LLM phases)
- app.services.wiki.ingest_events::normalize_agent_scope_key (POS: agent scope key SSOT)
- app.services.wiki.maintain.schemas (POS: maintain run result DTO)

[OUTPUT]
- MaintainRunState / MaintainErrorCode: lifecycle states and the only failure detail a client sees
- MaintainRun: live state of one run (phase, done/total, stop event, outcome)
- start_wiki_maintain_run: claim the scope, or None while a run is in flight
- get_wiki_maintain_run: the latest run of a scope
- cancel_wiki_maintain: ask the run in flight to stop between model calls

[POS]
A full maintain run makes up to 25 sequential LLM calls (minutes), so it runs in the background and a second
run on the same vault would only pay for the same pages twice. The registry lives in memory: it is transient
run progress of this single-process server, while the outcome of a run is persisted by `state_store` and the
vault health snapshot. The latest run of a scope stays after it ends, until the next run replaces it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from myrm_agent_harness.toolkits.wiki.maintenance.progress import MaintainPhase, MaintainProgress

from app.services.wiki.ingest_events import normalize_agent_scope_key
from app.services.wiki.maintain.schemas import WikiMaintainRunResult

type MaintainErrorCode = Literal["maintain_failed", "maintain_timeout", "compile_in_progress"]
type MaintainRunMode = Literal["structural", "full"]


class MaintainRunState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(slots=True)
class MaintainRun:
    mode: MaintainRunMode
    state: MaintainRunState = MaintainRunState.RUNNING
    phase: MaintainPhase | None = None
    done: int = 0
    total: int = 0
    result: WikiMaintainRunResult | None = None
    error_code: MaintainErrorCode | None = None
    # Set when the user cancels: the run ends between model calls and keeps what it has already written.
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    # Background runs only: the event loop keeps no strong reference to a task nobody awaits.
    task: asyncio.Task[None] | None = None

    @property
    def cancel_requested(self) -> bool:
        """Cancel was asked and the run has not finished winding down."""
        return self.state is MaintainRunState.RUNNING and self.stop.is_set()

    def on_progress(self, progress: MaintainProgress) -> None:
        self.phase = progress.phase
        self.done = progress.done
        self.total = progress.total

    def finish(self, result: WikiMaintainRunResult) -> None:
        self.result = result
        self.state = MaintainRunState.CANCELLED if result.cancelled else MaintainRunState.SUCCEEDED

    def fail(self, error_code: MaintainErrorCode) -> None:
        self.error_code = error_code
        self.state = MaintainRunState.FAILED


_runs: dict[str, MaintainRun] = {}


def start_wiki_maintain_run(agent_id: str | None, mode: MaintainRunMode) -> MaintainRun | None:
    """Claim the scope for a new run; None while a run is in flight.

    Nothing is awaited between the check and the claim, so two callers cannot both win.
    """
    scope_key = normalize_agent_scope_key(agent_id)
    current = _runs.get(scope_key)
    if current is not None and current.state is MaintainRunState.RUNNING:
        return None
    run = MaintainRun(mode=mode)
    _runs[scope_key] = run
    return run


def get_wiki_maintain_run(agent_id: str | None) -> MaintainRun | None:
    return _runs.get(normalize_agent_scope_key(agent_id))


def cancel_wiki_maintain(agent_id: str | None) -> MaintainRun | None:
    """Ask the run in flight to stop; the latest run of the scope either way, so the call is idempotent."""
    run = get_wiki_maintain_run(agent_id)
    if run is not None and run.state is MaintainRunState.RUNNING:
        run.stop.set()
    return run
