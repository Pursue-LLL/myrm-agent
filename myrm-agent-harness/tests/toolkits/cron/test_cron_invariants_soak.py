"""Random-operation soak of the cron protocol on the in-memory store.

Eight seeds drive a real ``CronScheduler`` and ``CronManager`` through random operations: a slot comes due, a slot
arrives long after its grace, a second slot of one job arrives while its first run is still in flight, a post-run
write fails, and pause, resume, reschedule, delete and restart, also with a run in flight: a graceful stop cuts it
short, a crash ends the process without a stop. A manual run starts on an idle job, is asked for while a run is in
flight, and stays in flight while a slot comes due. Nothing waits for the clock: a slot comes due by rewriting the
stored ``next_run_at`` and the soak ticks the scheduler itself, whose timers are off. After every step the scheduler
is drained, and these invariants must hold at that quiet point:

- an enabled job has a next run time
- a slot that came due left a run record behind: a run, or a skip
- a job never has two runs in flight, a manual run included, and a manual request is refused while one is
- a schedule that can fire faster than once a minute is booked at least a minute ahead
- no run leaves its in-flight marker behind, and while runs are in flight the markers are exactly their jobs
- a stop counts no failure for the run it cut short, and a crash is reported exactly once
- a manual run writes its own run record and changes neither the schedule, the status nor the counters of its job

The operations and the checks live in ``tests/support/cron_soak.py``.

Runtime: about 11 s of CPU for the eight seeds.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from tests.support.cron_soak import Soak

_SEEDS = range(1, 9)
_STEPS = 100


@pytest.mark.parametrize("seed", _SEEDS)
async def test_invariants_hold_after_every_step(seed: int, monkeypatch: pytest.MonkeyPatch) -> None:
    await Soak(seed, InMemoryCronStore(), monkeypatch).run(_STEPS)
