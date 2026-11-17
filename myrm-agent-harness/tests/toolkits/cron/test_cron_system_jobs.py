"""System jobs: the names the application keeps for itself, who may take them, and where they show.

A name starting with ``__`` belongs to a job the application creates itself (the heartbeat). The manager refuses it to
every other caller when a job is created or renamed and when one is duplicated; a job listing is the user's jobs unless
it asks for the system ones; and a generated name never starts with the prefix. These scenarios drive the real manager
over the in-memory store, the heartbeat functions and the ``cron_manage`` tool; nothing is mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.cron.cron_agent_tools import create_cron_tools
from myrm_agent_harness.toolkits.cron.engine.name_generator import generate_job_name
from myrm_agent_harness.toolkits.cron.heartbeat import HEARTBEAT_JOB_NAME, enable_heartbeat, get_heartbeat_status
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronJobPatch,
    JobType,
    Schedule,
    ScheduleKind,
    is_system_job_name,
)
from tests.support.cron_manager_stack import ManagerStack, make_manager_stack

EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000)
RESERVED = "reserved for the application's own jobs"


@pytest.fixture
def stack() -> ManagerStack:
    return make_manager_stack()


async def _system_job(stack: ManagerStack, name: str = HEARTBEAT_JOB_NAME) -> CronJob:
    return await stack.manager.create_job(name, JobType.AGENT, EVERY_HOUR, prompt="prompt", system=True)


async def _stored_names(stack: ManagerStack) -> set[str]:
    return {job.name for job in await stack.store.list_jobs()}


@pytest.mark.parametrize(
    ("name", "reserved"),
    [("__heartbeat__", True), ("__x", True), ("__", True), ("_x", False), ("ab", False), ("a__b", False), ("", False)],
)
def test_only_a_double_underscore_prefix_is_reserved(name: str, reserved: bool) -> None:
    assert is_system_job_name(name) is reserved


class TestWhoMayTakeAReservedName:
    @pytest.mark.parametrize("name", ["__heartbeat__", "__x", "__"])
    async def test_a_user_job_cannot_take_one(self, stack: ManagerStack, name: str) -> None:
        with pytest.raises(ValueError, match=RESERVED):
            await stack.create(name, EVERY_HOUR)

        assert await stack.store.list_jobs() == []

    async def test_a_single_underscore_is_an_ordinary_name(self, stack: ManagerStack) -> None:
        job = await stack.create("_x", EVERY_HOUR)

        assert job.name == "_x"

    async def test_a_system_job_takes_one(self, stack: ManagerStack) -> None:
        job = await _system_job(stack)

        assert job.name == HEARTBEAT_JOB_NAME
        assert await _stored_names(stack) == {HEARTBEAT_JOB_NAME}

    async def test_a_system_job_cannot_take_a_name_the_listings_show(self, stack: ManagerStack) -> None:
        """Otherwise the flag would let a visible job past the plan's job quota, which counts only the user's jobs."""
        with pytest.raises(ValueError, match="must start with"):
            await _system_job(stack, "visible")

        assert await stack.store.list_jobs() == []

    async def test_enabling_the_heartbeat_creates_a_system_job_once(self, stack: ManagerStack) -> None:
        first = await enable_heartbeat(stack.manager)
        again = await enable_heartbeat(stack.manager)

        assert first.name == HEARTBEAT_JOB_NAME
        assert again.id == first.id
        assert len(await stack.store.list_jobs()) == 1


class TestRenameAndDuplicate:
    async def test_a_rename_cannot_move_a_job_into_the_reserved_names(self, stack: ManagerStack) -> None:
        job = await stack.create("plain", EVERY_HOUR)

        with pytest.raises(ValueError, match=RESERVED):
            await stack.manager.update_job(job.id, CronJobPatch(name="__plain"))

        assert (await stack.stored(job.id)).name == "plain"

    async def test_a_rename_cannot_move_a_system_job_out_of_them(self, stack: ManagerStack) -> None:
        job = await _system_job(stack)

        with pytest.raises(ValueError, match=RESERVED):
            await stack.manager.update_job(job.id, CronJobPatch(name="visible"))

        assert (await stack.stored(job.id)).name == HEARTBEAT_JOB_NAME

    async def test_a_patch_that_repeats_a_system_jobs_name_is_not_a_rename(self, stack: ManagerStack) -> None:
        job = await _system_job(stack)

        updated = await stack.manager.update_job(job.id, CronJobPatch(name=HEARTBEAT_JOB_NAME, prompt="again"))

        assert updated is not None
        assert (updated.name, updated.prompt) == (HEARTBEAT_JOB_NAME, "again")

    async def test_an_ordinary_rename_still_works(self, stack: ManagerStack) -> None:
        job = await stack.create("plain", EVERY_HOUR)

        updated = await stack.manager.update_job(job.id, CronJobPatch(name="_renamed"))

        assert updated is not None and updated.name == "_renamed"

    async def test_a_system_job_cannot_be_duplicated(self, stack: ManagerStack) -> None:
        job = await _system_job(stack)

        with pytest.raises(ValueError, match="cannot be duplicated"):
            await stack.manager.duplicate_job(job.id)

        assert await _stored_names(stack) == {HEARTBEAT_JOB_NAME}

    async def test_an_ordinary_job_is_duplicated_under_a_visible_name(self, stack: ManagerStack) -> None:
        job = await stack.create("plain", EVERY_HOUR)

        copy = await stack.manager.duplicate_job(job.id)

        assert copy is not None and copy.name == "plain (Copy)"


class TestListings:
    async def _jobs(self, stack: ManagerStack) -> None:
        await enable_heartbeat(stack.manager)
        for name in ("_x", "ab", "a__b", "plain"):
            await stack.create(name, EVERY_HOUR)

    async def test_a_listing_is_the_users_jobs_unless_it_asks_for_the_system_ones(self, stack: ManagerStack) -> None:
        await self._jobs(stack)
        user_names = {"_x", "ab", "a__b", "plain"}

        assert {j.name for j in await stack.manager.list_jobs()} == user_names
        assert {j.name for j in await stack.manager.list_jobs(include_system=True)} == user_names | {HEARTBEAT_JOB_NAME}

    async def test_a_count_agrees_with_its_listing(self, stack: ManagerStack) -> None:
        await self._jobs(stack)

        assert await stack.manager.count_jobs() == 4
        assert await stack.manager.count_jobs(include_system=True) == 5

    async def test_a_name_filter_cannot_reach_a_system_job_unless_asked(self, stack: ManagerStack) -> None:
        await self._jobs(stack)

        assert await stack.manager.list_jobs(name_filter="heartbeat") == []
        assert await stack.manager.count_jobs(name_filter="heartbeat") == 0
        found = await stack.manager.list_jobs(name_filter="heartbeat", include_system=True)
        assert [j.name for j in found] == [HEARTBEAT_JOB_NAME]

    async def test_the_store_lists_every_job_by_default(self, stack: ManagerStack) -> None:
        """The scheduler, startup recovery and name-conflict resolution read the store and must see them all."""
        await self._jobs(stack)

        assert len(await stack.store.list_jobs()) == 5
        assert await stack.store.count_jobs() == 5
        assert len(await stack.store.list_jobs(include_system=False)) == 4

    async def test_the_heartbeat_is_found_however_many_jobs_there_are(self, stack: ManagerStack) -> None:
        """The oldest job sits past any page of the newest ones; the lookup asks for the heartbeat by name."""
        first = await enable_heartbeat(stack.manager)
        for index in range(205):
            await stack.create(f"job-{index}", EVERY_HOUR)

        status = await get_heartbeat_status(stack.manager)

        assert status.enabled
        assert status.job is not None and status.job.id == first.id

    async def test_a_lookalike_name_is_not_the_heartbeat(self, stack: ManagerStack) -> None:
        await stack.create("my __heartbeat__ notes", EVERY_HOUR)

        status = await get_heartbeat_status(stack.manager)

        assert status.job is None and not status.enabled


class TestGeneratedNames:
    @pytest.mark.parametrize(
        ("text", "name"),
        [
            ("__main__.py every day", "main__.py every day"),
            ("  ___ spaced", "spaced"),
            ("__ __x", "x"),
            ("_private note", "_private note"),
            ("plain", "plain"),
        ],
    )
    def test_a_generated_name_never_starts_with_the_reserved_prefix(self, text: str, name: str) -> None:
        assert generate_job_name(text) == name

    def test_a_text_of_underscores_only_gets_the_placeholder(self) -> None:
        assert generate_job_name("____") == "Unnamed Task"

    def test_a_long_text_is_cut_after_the_prefix_is_dropped(self) -> None:
        name = generate_job_name("__" + "word " * 20)

        assert not is_system_job_name(name)
        assert name.endswith("...")


class TestCronManageTool:
    @staticmethod
    async def _call(stack: ManagerStack, **args: object) -> str:
        tool = create_cron_tools(stack.manager, current_model="m", chat_id="c")[0]
        return str(await tool.ainvoke(args))

    @staticmethod
    def _tomorrow() -> str:
        return (datetime.now(UTC) + timedelta(days=1)).isoformat()

    async def test_add_under_a_reserved_name_returns_the_reason(self, stack: ManagerStack) -> None:
        reply = await self._call(stack, action="add", name="__sneaky", prompt="p", at=self._tomorrow())

        assert RESERVED in reply
        assert await stack.store.list_jobs() == []

    async def test_add_without_a_name_derives_one_that_is_not_reserved(self, stack: ManagerStack) -> None:
        await self._call(stack, action="add", prompt="__main__.py report", at=self._tomorrow())

        (job,) = await stack.store.list_jobs()
        assert job.name == "main__.py report"

    async def test_update_to_a_reserved_name_returns_the_reason(self, stack: ManagerStack) -> None:
        job = await stack.create("plain", EVERY_HOUR)

        reply = await self._call(stack, action="update", job_id=job.id, name="__plain")

        assert RESERVED in reply
        assert (await stack.stored(job.id)).name == "plain"

    async def test_list_leaves_the_heartbeat_out(self, stack: ManagerStack) -> None:
        await enable_heartbeat(stack.manager)

        assert await self._call(stack, action="list") == "No scheduled tasks."

        await stack.create("plain", EVERY_HOUR)
        reply = await self._call(stack, action="list")
        assert "plain" in reply and HEARTBEAT_JOB_NAME not in reply
