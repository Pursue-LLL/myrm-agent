"""ConflictGate: shared holders run together, an exclusive holder runs alone, admission follows arrival order."""

from __future__ import annotations

import asyncio
import random

import pytest

from myrm_agent_harness.agent.middlewares.concurrency.conflict_gate import ConflictGate


async def _settle() -> None:
    """Let every task that can make progress do so."""
    for _ in range(8):
        await asyncio.sleep(0)


class Holder:
    """A task that holds the gate until told to let go, and logs when it got in and out."""

    def __init__(self, gate: ConflictGate, name: str, *, exclusive: bool, log: list[str]) -> None:
        self.name = name
        self.release = asyncio.Event()
        self._gate = gate
        self._exclusive = exclusive
        self._log = log
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        async with self._gate.hold(exclusive=self._exclusive):
            self._log.append(f"{self.name}+")
            await self.release.wait()
            self._log.append(f"{self.name}-")

    async def let_go(self) -> None:
        self.release.set()
        await _settle()


async def _start(gate: ConflictGate, log: list[str], name: str, *, exclusive: bool) -> Holder:
    holder = Holder(gate, name, exclusive=exclusive, log=log)
    await _settle()
    return holder


async def test_shared_holders_are_admitted_together() -> None:
    gate = ConflictGate()
    log: list[str] = []

    first = await _start(gate, log, "a", exclusive=False)
    second = await _start(gate, log, "b", exclusive=False)

    assert log == ["a+", "b+"]
    await first.let_go()
    await second.let_go()


async def test_an_exclusive_holder_waits_for_the_shared_holders_in_front_of_it() -> None:
    gate = ConflictGate()
    log: list[str] = []
    reader = await _start(gate, log, "r", exclusive=False)

    writer = await _start(gate, log, "w", exclusive=True)
    assert log == ["r+"]

    await reader.let_go()
    assert log == ["r+", "r-", "w+"]
    await writer.let_go()


async def test_a_shared_holder_waits_for_the_exclusive_holder_in_front_of_it() -> None:
    gate = ConflictGate()
    log: list[str] = []
    writer = await _start(gate, log, "w", exclusive=True)

    reader = await _start(gate, log, "r", exclusive=False)
    assert log == ["w+"]

    await writer.let_go()
    assert log == ["w+", "w-", "r+"]
    await reader.let_go()


async def test_exclusive_holders_never_hold_together() -> None:
    gate = ConflictGate()
    log: list[str] = []
    first = await _start(gate, log, "a", exclusive=True)
    second = await _start(gate, log, "b", exclusive=True)
    assert log == ["a+"]

    await first.let_go()
    assert log == ["a+", "a-", "b+"]
    await second.let_go()


async def test_shared_holders_arriving_behind_a_waiting_exclusive_holder_do_not_overtake_it() -> None:
    gate = ConflictGate()
    log: list[str] = []
    early_reader = await _start(gate, log, "r1", exclusive=False)
    writer = await _start(gate, log, "w", exclusive=True)

    late_reader = await _start(gate, log, "r2", exclusive=False)
    assert log == ["r1+"]

    await early_reader.let_go()
    assert log == ["r1+", "r1-", "w+"]

    await writer.let_go()
    assert log == ["r1+", "r1-", "w+", "w-", "r2+"]
    await late_reader.let_go()


async def test_waiting_exclusive_holders_are_admitted_in_arrival_order() -> None:
    gate = ConflictGate()
    log: list[str] = []
    blocker = await _start(gate, log, "x", exclusive=True)
    waiting = [await _start(gate, log, name, exclusive=True) for name in ("w1", "w2", "w3")]

    await blocker.let_go()
    for holder in waiting:
        await holder.let_go()

    assert log == ["x+", "x-", "w1+", "w1-", "w2+", "w2-", "w3+", "w3-"]


async def test_shared_holders_that_wait_together_are_admitted_together() -> None:
    gate = ConflictGate()
    log: list[str] = []
    writer = await _start(gate, log, "w", exclusive=True)
    first = await _start(gate, log, "r1", exclusive=False)
    second = await _start(gate, log, "r2", exclusive=False)

    await writer.let_go()

    assert log == ["w+", "w-", "r1+", "r2+"]
    await first.let_go()
    await second.let_go()


async def test_a_waiter_that_is_cancelled_lets_the_ones_behind_it_in() -> None:
    gate = ConflictGate()
    log: list[str] = []
    reader = await _start(gate, log, "r1", exclusive=False)
    writer = await _start(gate, log, "w", exclusive=True)
    late_reader = await _start(gate, log, "r2", exclusive=False)
    assert log == ["r1+"]

    writer.task.cancel()
    await _settle()

    assert log == ["r1+", "r2+"]
    assert writer.task.cancelled()
    await reader.let_go()
    await late_reader.let_go()


async def test_a_waiter_cancelled_the_moment_it_is_admitted_gives_the_hold_back() -> None:
    gate = ConflictGate()
    log: list[str] = []
    holder = await _start(gate, log, "x", exclusive=True)
    waiter = await _start(gate, log, "w", exclusive=True)

    holder.release.set()
    while "x-" not in log:
        await asyncio.sleep(0)
    # ``x`` has left, which admitted ``w``; the cancellation reaches ``w`` before it runs on.
    waiter.task.cancel()
    await _settle()

    assert waiter.task.cancelled()
    async with asyncio.timeout(1):
        async with gate.hold(exclusive=True):
            pass


async def test_a_holder_that_leaves_before_a_cancelled_waiter_has_noticed_is_not_disturbed() -> None:
    gate = ConflictGate()
    log: list[str] = []
    holder = await _start(gate, log, "x", exclusive=True)
    waiter = await _start(gate, log, "w", exclusive=True)

    holder.release.set()
    waiter.task.cancel()
    await _settle()

    assert holder.task.result() is None
    assert waiter.task.cancelled()
    assert log == ["x+", "x-"]
    async with asyncio.timeout(1):
        async with gate.hold(exclusive=True):
            pass


async def test_the_hold_ends_when_the_body_raises() -> None:
    gate = ConflictGate()

    with pytest.raises(ValueError, match="body failed"):
        async with gate.hold(exclusive=True):
            raise ValueError("body failed")

    async with asyncio.timeout(1):
        async with gate.hold(exclusive=True):
            pass


async def test_the_hold_ends_when_the_holder_is_cancelled() -> None:
    gate = ConflictGate()
    log: list[str] = []
    holder = await _start(gate, log, "x", exclusive=True)

    holder.task.cancel()
    await _settle()

    async with asyncio.timeout(1):
        async with gate.hold(exclusive=True):
            pass


@pytest.mark.parametrize("seed", range(5))
async def test_holders_never_overlap_wrongly_whatever_the_arrival_order_and_cancellations(seed: int) -> None:
    """Many holders of both kinds, some cancelled while waiting or holding: the invariants hold and all of them end."""
    rng = random.Random(seed)
    gate = ConflictGate()
    inside = {"shared": 0, "exclusive": 0}
    violations: list[str] = []
    completed = 0

    async def holder(exclusive: bool) -> None:
        nonlocal completed
        await asyncio.sleep(rng.random() * 0.01)
        async with gate.hold(exclusive=exclusive):
            kind = "exclusive" if exclusive else "shared"
            inside[kind] += 1
            if inside["exclusive"] > 1 or (inside["exclusive"] and inside["shared"]):
                violations.append(f"{dict(inside)} while {kind} entered")
            try:
                await asyncio.sleep(rng.random() * 0.005)
                completed += 1
            finally:
                inside[kind] -= 1

    tasks = [asyncio.create_task(holder(rng.random() < 0.4)) for _ in range(150)]
    for task in rng.sample(tasks, 30):
        asyncio.get_running_loop().call_later(rng.random() * 0.02, task.cancel)

    async with asyncio.timeout(10):
        await asyncio.gather(*tasks, return_exceptions=True)

    assert violations == []
    assert inside == {"shared": 0, "exclusive": 0}
    assert completed >= 120
    async with asyncio.timeout(1):
        async with gate.hold(exclusive=True):
            pass
