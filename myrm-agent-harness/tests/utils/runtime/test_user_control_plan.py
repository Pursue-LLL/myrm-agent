"""Plans of a script: a plan is stale once control changed hands after it was made, and binds the tasks it started."""

from __future__ import annotations

import asyncio

import pytest

from myrm_agent_harness.utils.runtime.user_control import UserControl, in_plan, plan_is_stale, planned_against


def test_a_plan_is_stale_once_control_changed_hands_after_it_was_made() -> None:
    control = UserControl()

    with planned_against(control.generation):
        assert plan_is_stale(control) is False
        control.acquire()
        assert plan_is_stale(control) is False, "a person who still holds control has not changed anything yet"
        control.release()
        assert plan_is_stale(control) is True


def test_a_plan_made_after_the_hand_over_is_not_stale() -> None:
    control = UserControl()
    control.acquire()
    control.release()

    with planned_against(control.generation):
        assert plan_is_stale(control) is False


def test_nothing_is_stale_outside_a_plan() -> None:
    control = UserControl()
    control.acquire()
    control.release()

    assert plan_is_stale(control) is False
    with planned_against(0):
        pass
    assert plan_is_stale(control) is False, "leaving the plan must forget it"


@pytest.mark.asyncio
async def test_a_plan_binds_only_the_task_that_made_it() -> None:
    control = UserControl()
    entered, finished = asyncio.Event(), asyncio.Event()

    async def planner() -> None:
        with planned_against(control.generation):
            entered.set()
            await finished.wait()

    task = asyncio.create_task(planner())
    await entered.wait()
    control.acquire()
    control.release()

    assert plan_is_stale(control) is False
    finished.set()
    await task


def test_a_call_is_a_step_of_a_plan_only_inside_planned_against() -> None:
    assert in_plan() is False
    with planned_against(0):
        assert in_plan() is True
    assert in_plan() is False, "leaving the plan must forget it"


@pytest.mark.asyncio
async def test_a_task_started_inside_a_plan_is_part_of_it() -> None:
    """Monty runs a script's host steps in tasks of their own; they copy the context of the script that began them."""

    async def step() -> bool:
        return in_plan()

    with planned_against(0):
        inside = await asyncio.create_task(step())
    outside = await asyncio.create_task(step())

    assert inside is True
    assert outside is False
