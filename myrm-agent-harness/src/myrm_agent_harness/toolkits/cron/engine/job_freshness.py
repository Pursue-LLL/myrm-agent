"""The stored job is the truth: bring an in-hand snapshot up to date before acting on it.

[INPUT]
- toolkits.cron.protocols::CronStore (POS: job and run persistence)
- toolkits.cron.types::CronJob (POS: Cron job domain types.)

[OUTPUT]
- RUN_OWNED_FIELDS: the only job fields a run decides itself
- adopt_latest: copy the stored job onto the in-hand snapshot, minus the run-owned fields

[POS]
A job reaches the executor as a snapshot read when it came due, but its stagger wait, concurrency wait, run,
delivery and closing writes all happen later, and the user pauses, edits and deletes jobs in that time. Every
step that waits and every step that writes calls ``adopt_latest`` first and then applies only what the run
decided, so a closing write can neither undo the user's change nor bring back a deleted job.
"""

from __future__ import annotations

from dataclasses import fields
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.types import CronJob

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.protocols import CronStore

# The scheduler counts a fire when the run starts and delivery sets the output hash while it runs; neither is in
# the store before the closing write, so adopting them would drop the run's own bookkeeping.
RUN_OWNED_FIELDS = frozenset({"fire_count", "last_output_hash"})
_ADOPTED_FIELDS = tuple(f.name for f in fields(CronJob) if f.name not in RUN_OWNED_FIELDS)


async def adopt_latest(store: CronStore, job: CronJob) -> bool:
    """Overwrite ``job`` with the stored job except for the run-owned fields; ``False`` when it was deleted."""
    latest = await store.get_job(job.id)
    if latest is None:
        return False
    for name in _ADOPTED_FIELDS:
        setattr(job, name, getattr(latest, name))
    return True
