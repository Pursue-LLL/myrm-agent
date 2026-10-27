"""Cron entry: single flight, wiring decisions, ending a slice whose sync was withdrawn, and the mapping of a slice outcome to scheduler advice."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupGovernor, CorpusDedupScanner
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.source_sync.ima import job_runner
from app.services.wiki.source_sync.ima.context import SyncContext
from app.services.wiki.source_sync.ima.engine import SliceOutcome
from app.services.wiki.source_sync.ima.models import ImaCredentials
from app.services.wiki.source_sync.ima.state import (
    ImaKbSelection,
    ImaSyncConfig,
    ImaSyncState,
    save_ima_config,
    save_ima_state,
)
from app.services.wiki.source_sync.publish_helpers import RawConflictPolicy, publish_source_markdown

LLM = cast(BaseChatModel, object())
CREDENTIALS = ImaCredentials(client_id="cid", api_key="key")
_POLL_S = 0.01
# A withdrawal must reach the slice within this long: about a hundred polls, so a slow machine does not flake it.
_PATIENCE_S = 1.0


def _job_id(agent_id: str | None) -> str:
    return f"job:{agent_id}"


@dataclass
class Harness:
    contexts: list[SyncContext] = field(default_factory=list)
    outcome: SliceOutcome = field(
        default_factory=lambda: SliceOutcome(finished=False, retry_after_s=5.0, published=0, generation_total=0)
    )
    snapshots: int = 0
    dedups: int = 0
    credentials: ImaCredentials | None = CREDENTIALS
    auto_compile: bool = True
    gate: asyncio.Event | None = None
    events: list[str] = field(default_factory=list)
    publish: dict[str, str] = field(default_factory=dict)
    slice_error: Exception | None = None
    scan_completes: bool = True
    # Jobs the user paused or removed.
    paused: set[str] = field(default_factory=set)
    # Raised when the running slice asks whether its sync is still wanted.
    mandate_read_error: Exception | None = None
    # The user pauses right after the cron job was read for admission.
    pause_after_admission: bool = False

    def pause(self, agent_id: str | None) -> None:
        self.paused.add(_job_id(agent_id))

    def release(self) -> None:
        """Let the slices held at the gate go on."""
        if self.gate is not None:
            self.gate.set()


class FakeCompiler:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def enqueue_file(self, file_path: Path) -> None:
        self._events.append(f"enqueue:{file_path.name}")


class FakeArchiver:
    def __init__(self, root: Path, events: list[str]) -> None:
        from myrm_agent_harness.toolkits.wiki import WikiStructure

        self._structure = WikiStructure(base_dir=root)
        self._compiler = FakeCompiler(events)


@pytest.fixture
def harness(tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    h = Harness()
    archiver = FakeArchiver(tmp_path, h.events)

    async def credentials() -> ImaCredentials | None:
        return h.credentials

    async def run_slice(ctx: SyncContext) -> SliceOutcome:
        h.contexts.append(ctx)
        if h.gate is not None:
            await h.gate.wait()
        for relative_path, body in h.publish.items():
            await publish_source_markdown(
                ctx.structure,
                relative_path=relative_path,
                content=body,
                auto_compile=ctx.compiler_enqueue is not None,
                compiler_enqueue=ctx.compiler_enqueue,
                conflict_policy=RawConflictPolicy.SUPERSEDE,
            )
        if h.slice_error is not None:
            raise h.slice_error
        return h.outcome

    async def source_config(db: AsyncSession, *, agent_id: str | None) -> SimpleNamespace:
        return SimpleNamespace(auto_compile=h.auto_compile)

    async def snapshot(archiver: object, *, agent_id: str | None) -> None:
        h.snapshots += 1
        h.events.append("snapshot")

    async def dedup(*, agent_id: str | None) -> bool:
        h.dedups += 1
        h.events.append("scan")
        if h.scan_completes and archiver._structure.raw_dir.exists():
            CorpusDedupScanner(archiver._structure).scan(incremental=True)
        return h.scan_completes

    async def find_active_job(agent_id: str | None) -> SimpleNamespace | None:
        if _job_id(agent_id) in h.paused:
            return None
        if h.pause_after_admission:
            h.pause(agent_id)
        return SimpleNamespace(id=_job_id(agent_id))

    async def is_job_active(job_id: str) -> bool:
        if h.mandate_read_error is not None:
            raise h.mandate_read_error
        return job_id not in h.paused

    monkeypatch.setattr(job_runner, "find_active_job", find_active_job)
    monkeypatch.setattr(job_runner, "is_job_active", is_job_active)
    monkeypatch.setattr(job_runner, "_MANDATE_POLL_S", _POLL_S)
    monkeypatch.setattr(job_runner, "load_credentials", credentials)
    monkeypatch.setattr(job_runner, "run_slice", run_slice)
    monkeypatch.setattr(job_runner, "load_wiki_source_sync_config", source_config)
    monkeypatch.setattr(job_runner, "get_wiki_archiver", lambda llm, agent_id=None: archiver)
    monkeypatch.setattr("app.services.wiki.ingest_events.publish_wiki_ingest_snapshot", snapshot)
    monkeypatch.setattr(job_runner, "run_post_sync_dedup_scan", dedup)
    job_runner._slice_locks.clear()
    yield h
    h.release()


async def _configure(
    ima_db: async_sessionmaker[AsyncSession],
    *,
    backfill_complete: bool = False,
    notes: bool = True,
    libraries: tuple[ImaKbSelection, ...] = (),
    agent_id: str | None = None,
) -> None:
    async with ima_db() as db:
        await save_ima_config(db, ImaSyncConfig(knowledge_bases=list(libraries), include_notes=notes), agent_id=agent_id)
        await save_ima_state(db, ImaSyncState(backfill_complete=backfill_complete), agent_id=agent_id)


async def test_not_connected_or_nothing_selected_is_a_quiet_skip(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    harness.credentials = None
    await _configure(ima_db)
    skipped = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    assert skipped.skipped and skipped.summary_text == "[SILENT]" and skipped.retry_at is None

    harness.credentials = CREDENTIALS
    await _configure(ima_db, notes=False)
    assert (await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)).skipped
    assert harness.contexts == []


async def test_a_second_overlapping_run_for_the_same_agent_is_skipped(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _configure(ima_db)
    harness.gate = asyncio.Event()
    first = asyncio.create_task(job_runner.run_ima_sync_job(llm=LLM, agent_id=None))
    while not harness.contexts:
        await asyncio.sleep(0)

    overlapping = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    harness.gate.set()
    await first

    assert overlapping.skipped and len(harness.contexts) == 1


async def _start_slices(
    harness: Harness,
    ima_db: async_sessionmaker[AsyncSession],
    *agents: str | None,
    libraries: tuple[ImaKbSelection, ...] = (),
) -> list[asyncio.Task[job_runner.ImaJobOutcome]]:
    """Start one slice per agent and wait until each has begun; they run until ``harness.gate`` is set."""
    harness.gate = asyncio.Event()
    for agent in agents:
        await _configure(ima_db, libraries=libraries, agent_id=agent)
    begun = len(harness.contexts)
    runs = [asyncio.create_task(job_runner.run_ima_sync_job(llm=LLM, agent_id=agent)) for agent in agents]
    while len(harness.contexts) - begun < len(agents):
        await asyncio.sleep(0)
    return runs


async def _is_told_to_end(ctx: SyncContext) -> bool:
    try:
        await asyncio.wait_for(ctx.stop.wait(), timeout=_PATIENCE_S)
    except TimeoutError:
        return False
    return True


async def _stays_running(ctx: SyncContext) -> bool:
    """Let the watcher ask many times, then report whether the slice may still go on."""
    await asyncio.sleep(20 * _POLL_S)
    return ctx.time_left() > 0


def _watchers() -> list[asyncio.Task[object]]:
    return [task for task in asyncio.all_tasks() if task.get_name() == "ima-sync-mandate"]


async def test_a_slice_ends_when_its_job_is_paused_or_removed_while_it_runs(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    (run,) = await _start_slices(harness, ima_db, None)
    (ctx,) = harness.contexts
    assert ctx.time_left() > 0

    harness.pause(None)

    assert await _is_told_to_end(ctx)
    assert ctx.time_left() <= 0
    harness.release()
    await run


async def test_a_slice_ends_when_the_selection_changes_while_it_runs(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    (run,) = await _start_slices(harness, ima_db, None)
    (ctx,) = harness.contexts

    async with ima_db() as db:
        await save_ima_config(
            db, ImaSyncConfig(knowledge_bases=[ImaKbSelection(id="kb1", name="One")], include_notes=True), agent_id=None
        )

    assert await _is_told_to_end(ctx)
    harness.release()
    await run


async def test_saving_the_same_selection_again_leaves_the_slice_alone(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    """The selection is which ids are imported: a renamed library or a save that changes nothing is no reason to restart."""
    (run,) = await _start_slices(harness, ima_db, None, libraries=(ImaKbSelection(id="kb1", name="One"),))
    (ctx,) = harness.contexts
    async with ima_db() as db:
        await save_ima_config(
            db, ImaSyncConfig(knowledge_bases=[ImaKbSelection(id="kb1", name="One, renamed")], include_notes=True), agent_id=None
        )

    assert await _stays_running(ctx)
    harness.release()
    await run


async def test_a_slice_asks_about_the_selection_of_its_own_agent(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    """Only the other agent has a selection; reading the default agent's instead would look like a change."""
    (run,) = await _start_slices(harness, ima_db, "other", libraries=(ImaKbSelection(id="kb1", name="One"),))
    (ctx,) = harness.contexts

    assert await _stays_running(ctx)
    harness.release()
    await run


async def test_a_slice_nobody_withdrew_runs_on(harness: Harness, ima_db: async_sessionmaker[AsyncSession]) -> None:
    (run,) = await _start_slices(harness, ima_db, None)
    (ctx,) = harness.contexts

    assert await _stays_running(ctx)
    harness.release()
    await run


async def test_a_withdrawal_reaches_only_the_slice_of_that_agent(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    runs = await _start_slices(harness, ima_db, None, "other")
    by_agent = {ctx.agent_id: ctx for ctx in harness.contexts}

    harness.pause("other")

    assert await _is_told_to_end(by_agent["other"])
    assert await _stays_running(by_agent[None])
    harness.release()
    await asyncio.gather(*runs)


async def test_a_pause_that_lands_right_after_the_job_was_read_is_still_noticed(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    """Nothing is registered anywhere, so no ordering against the slice's start can lose a pause: the job is asked as it is now."""
    harness.pause_after_admission = True
    (run,) = await _start_slices(harness, ima_db, None)
    (ctx,) = harness.contexts

    assert await _is_told_to_end(ctx)
    harness.release()
    await run


async def test_a_failed_check_does_not_end_the_slice_and_is_asked_again(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    harness.mandate_read_error = RuntimeError("database is locked")
    (run,) = await _start_slices(harness, ima_db, None)
    (ctx,) = harness.contexts

    assert await _stays_running(ctx)
    # However often it was asked, the failure is reported once.
    complaints = [record for record in caplog.records if "could not check" in record.getMessage()]
    assert [record.levelno for record in complaints] == [logging.WARNING]

    harness.mandate_read_error = None
    harness.pause(None)
    assert await _is_told_to_end(ctx)
    harness.release()
    await run


async def test_the_watcher_ends_with_the_slice_however_it_ends(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _configure(ima_db)
    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    assert _watchers() == []

    harness.slice_error = RuntimeError("transport died")
    with pytest.raises(RuntimeError, match="transport died"):
        await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    assert _watchers() == []

    harness.slice_error = None
    (run,) = await _start_slices(harness, ima_db, None)
    assert len(_watchers()) == 1
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert _watchers() == []


async def test_a_job_paused_or_removed_after_it_fired_starts_no_slice(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _configure(ima_db)
    harness.pause(None)

    outcome = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert outcome.skipped and outcome.retry_at is None
    assert harness.contexts == [] and _watchers() == []


@pytest.mark.parametrize(
    ("backfill_complete", "auto_compile", "expect_compile"),
    [(False, True, False), (True, True, True), (True, False, False)],
)
async def test_compile_enqueue_requires_a_settled_backfill_and_the_users_auto_compile(
    harness: Harness,
    ima_db: async_sessionmaker[AsyncSession],
    backfill_complete: bool,
    auto_compile: bool,
    expect_compile: bool,
) -> None:
    await _configure(ima_db, backfill_complete=backfill_complete)
    harness.auto_compile = auto_compile

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert (harness.contexts[0].compiler_enqueue is not None) is expect_compile


async def test_continuation_is_rearmed_through_retry_at(harness: Harness, ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _configure(ima_db)
    before = datetime.now(UTC)

    outcome = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert not outcome.skipped and outcome.summary_text == "[SILENT]"
    assert outcome.retry_at is not None and timedelta(seconds=4) <= outcome.retry_at - before <= timedelta(seconds=7)


async def test_finished_pass_reports_the_count_and_runs_the_post_publish_hooks(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _configure(ima_db)
    harness.outcome = SliceOutcome(finished=True, retry_after_s=None, published=3, generation_total=7)

    outcome = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert outcome.summary_text == "ima: 7 imported" and outcome.retry_at is None and not outcome.skipped
    assert harness.snapshots == 1 and harness.dedups == 1


async def test_a_pass_that_published_nothing_stays_silent_and_skips_dedup(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _configure(ima_db)
    harness.outcome = SliceOutcome(finished=True, retry_after_s=None, published=0, generation_total=0)

    outcome = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert outcome.summary_text == "[SILENT]"
    assert harness.snapshots == 0 and harness.dedups == 0


async def test_auth_stops_the_job_without_a_retry_and_rate_limit_waits(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _configure(ima_db)
    harness.outcome = SliceOutcome(finished=False, retry_after_s=None, published=0, generation_total=0, error_kind="auth")
    auth = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    assert auth.skipped and auth.retry_at is None

    harness.outcome = SliceOutcome(finished=False, retry_after_s=120.0, published=0, generation_total=0, error_kind="rate_limit")
    limited = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    assert not limited.skipped and limited.retry_at is not None


SAME_BODY = "# Report\n\nThe very same body, in two libraries."


async def test_files_are_scanned_before_they_are_queued_and_the_snapshot_comes_last(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _configure(ima_db, backfill_complete=True)
    harness.publish = {"ima/KB1/a.md": SAME_BODY, "ima/KB2/a-copy.md": SAME_BODY, "ima/KB1/unique.md": "# Unique\n\nAlone."}
    harness.outcome = SliceOutcome(finished=False, retry_after_s=5.0, published=3, generation_total=0)

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == ["scan", "enqueue:unique.md", "snapshot"]


async def test_a_slice_with_nothing_held_back_does_not_scan(harness: Harness, ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _configure(ima_db, backfill_complete=True)

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == []


async def test_the_first_backfill_is_never_queued_by_a_slice(harness: Harness, ima_db: async_sessionmaker[AsyncSession]) -> None:
    await _configure(ima_db, backfill_complete=False)
    harness.publish = {"ima/KB1/a.md": "# A\n\nfirst"}
    harness.outcome = SliceOutcome(finished=False, retry_after_s=5.0, published=1, generation_total=0)

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == ["snapshot"]


async def test_a_failing_slice_still_hands_over_what_it_already_published(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _configure(ima_db, backfill_complete=True)
    harness.publish = {"ima/KB1/a.md": "# A\n\nfirst"}
    harness.slice_error = RuntimeError("transport died")

    with pytest.raises(RuntimeError, match="transport died"):
        await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == ["enqueue:a.md"]


async def test_a_scan_that_did_not_complete_does_not_hold_back_files_whatever_stored_groups_say(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    await _configure(ima_db, backfill_complete=True)
    structure = FakeArchiver(tmp_path, harness.events)._structure
    for relative_path in ("ima/KB1/old-a.md", "ima/KB1/old-b.md"):
        earlier = structure.get_raw_file_path(relative_path)
        earlier.parent.mkdir(parents=True, exist_ok=True)
        earlier.write_text(SAME_BODY, encoding="utf-8")
    CorpusDedupScanner(structure).scan(incremental=False)
    harness.scan_completes = False
    harness.publish = {"ima/KB1/a.md": SAME_BODY, "ima/KB2/a-copy.md": SAME_BODY}
    harness.outcome = SliceOutcome(finished=False, retry_after_s=5.0, published=2, generation_total=0)

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == ["scan", "enqueue:a.md", "enqueue:a-copy.md", "snapshot"]


async def test_a_slice_that_published_nothing_still_scans_for_files_an_earlier_slice_left_held(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    await _configure(ima_db, backfill_complete=True)
    structure = FakeArchiver(tmp_path, harness.events)._structure
    leftover = structure.get_raw_file_path("ima/KB1/leftover.md")
    leftover.parent.mkdir(parents=True, exist_ok=True)
    leftover.write_text("# Leftover\n\nHeld by a slice that died.", encoding="utf-8")
    CorpusDedupGovernor(structure).hold_for_compile(["ima/KB1/leftover.md"])

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == ["scan", "enqueue:leftover.md"]


async def test_a_slice_that_published_nothing_releases_files_an_earlier_scan_already_covered(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    await _configure(ima_db, backfill_complete=True)
    structure = FakeArchiver(tmp_path, harness.events)._structure
    leftover = structure.get_raw_file_path("ima/KB1/leftover.md")
    leftover.parent.mkdir(parents=True, exist_ok=True)
    leftover.write_text("# Leftover\n\nScanned, then the slice died.", encoding="utf-8")
    CorpusDedupGovernor(structure).hold_for_compile(["ima/KB1/leftover.md"])
    CorpusDedupScanner(structure).scan(incremental=False)

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == ["enqueue:leftover.md"]
