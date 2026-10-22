"""Earliest future moment this server process must be running again.

[INPUT]
- app.services.agent.goals.usage_limit_resume::get_usage_limit_wake_daemon (POS: armed parked-goal wake times)
- app.core.cron.adapters.setup::get_cron_store (POS: cron store, earliest ACTIVE ``next_run_at``)
- app.services.kanban::KanbanService (POS: kanban store, earliest ``scheduled_until`` of rescheduled tasks)

[OUTPUT]
- earliest_scheduled_wake: min of the timer-driven wake (parked goal / cron, moved earlier by the wake
  lead) and the kanban un-schedule time (not moved), future only

[POS]
Single answer to "what must run while nobody is talking to this sandbox". Only times still in the
future count: a past one is already being handled by this (running) process, and the control plane
has nothing to wake.

Goal and cron work is timer-driven: the control plane polls and a cron job skips a run that starts
past its misfire grace, so the time is reported ``_WAKE_LEAD_S`` early whenever there is room for
that. Kanban tasks are released by a periodic poll instead; a poll whose sleep ended while the
container was paused runs the moment it is resumed, so the sandbox must be resumed at or after the
due time for that first poll to find the task due.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.cron.adapters.setup import get_cron_store
from app.services.agent.goals.usage_limit_resume import get_usage_limit_wake_daemon
from app.services.kanban import KanbanService

_WAKE_LEAD_S = 60.0


async def earliest_scheduled_wake(now: float) -> float | None:
    """Epoch seconds at which to wake for the earliest parked-goal wake, cron run or kanban release after ``now``."""
    timer_dues: list[float] = []

    goal_due = get_usage_limit_wake_daemon().next_due_at(now)
    if goal_due is not None:
        timer_dues.append(goal_due)

    cron_due = await get_cron_store().earliest_next_run()
    if cron_due is not None:
        timer_dues.append(cron_due.astimezone(timezone.utc).timestamp())

    wake_times: list[float] = []
    timer_due = min((at for at in timer_dues if at > now), default=None)
    if timer_due is not None:
        lead_time = timer_due - _WAKE_LEAD_S
        wake_times.append(lead_time if lead_time > now else timer_due)

    kanban_due = await KanbanService.get_instance().store.earliest_scheduled_until(datetime.fromtimestamp(now, tz=timezone.utc))
    if kanban_due is not None:
        wake_times.append(kanban_due.astimezone(timezone.utc).timestamp())

    return min(wake_times, default=None)
