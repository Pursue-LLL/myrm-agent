"""Heartbeat of a delegated run: tells the chat the task is still working while the run itself says nothing.

[INPUT]
- channels.routing.router_reassurance::run_reassurance_loop (POS: edit-in-place heartbeat loop)
- channels.delegation.delegation_models::DelegationTask (POS: the delegated task and its time limit)
- channels.core.bus::MessageBus (POS: sends the heartbeat and edits it in place)

[OUTPUT]
- HEARTBEAT_INTERVAL_SECONDS: minutes of quiet before a heartbeat, in seconds
- delegated_run_heartbeat: async context manager that runs the heartbeat for the duration of the block

[POS]
A delegated run's progress is not shown in the chat, so the run counts as quiet from its first second and the
heartbeat is time-triggered, not silence-gated. It says only that the task is alive (elapsed minutes and step count):
what the run is doing stays out of the chat. It edits one message in place (a channel that cannot edit gets the
first one only) and never outlives the block: it ends when the run finishes, is stopped, or stops at an approval.
At most one heartbeat per interval fits in the task's time limit.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from app.channels.routing.router_reassurance import run_reassurance_loop
from app.channels.types import InboundMessage, ProgressUpdate

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus

    from .delegation_models import DelegationTask

HEARTBEAT_INTERVAL_SECONDS = 300.0


@asynccontextmanager
async def delegated_run_heartbeat(
    task: DelegationTask, bus: MessageBus, msg: InboundMessage
) -> AsyncIterator[Callable[[ProgressUpdate], None]]:
    """Run the task's heartbeat while the block runs; the yielded callback feeds it the run's progress events."""
    interval = HEARTBEAT_INTERVAL_SECONDS
    # Quiet since one interval before the start, so the first check at the end of the first interval always fires.
    state: dict[str, float | int | str] = {"last_activity": time.monotonic() - interval, "step_count": 0, "current_stage": ""}

    def note_progress(_update: ProgressUpdate) -> None:
        state["step_count"] = int(state["step_count"]) + 1

    beat = asyncio.create_task(
        run_reassurance_loop(
            bus,
            msg,
            task.origin_chat_id,
            state,
            interval=interval,
            max_count=int(task.timeout_seconds // interval),
            text_key="delegation_still_running",
            text_params={"task_id": task.task_id},
        )
    )
    try:
        yield note_progress
    finally:
        beat.cancel()
        await asyncio.gather(beat, return_exceptions=True)
