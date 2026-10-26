"""Cron entry: single flight, wiring decisions and the mapping of a slice outcome to scheduler advice."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
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
from app.services.wiki.source_sync.ima.state import ImaSyncConfig, ImaSyncState, save_ima_config, save_ima_state
from app.services.wiki.source_sync.publish_helpers import RawConflictPolicy, publish_source_markdown

LLM = cast(BaseChatModel, object())
CREDENTIALS = ImaCredentials(client_id="cid", api_key="key")


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
    job_active: bool = True


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
def harness(tmp_path: Path, ima_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch) -> Harness:
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

    async def job_active(agent_id: str | None) -> bool:
        return h.job_active

    monkeypatch.setattr(job_runner, "is_job_active", job_active)
    monkeypatch.setattr(job_runner, "load_credentials", credentials)
    monkeypatch.setattr(job_runner, "run_slice", run_slice)
    monkeypatch.setattr(job_runner, "load_wiki_source_sync_config", source_config)
    monkeypatch.setattr(job_runner, "get_wiki_archiver", lambda llm, agent_id=None: archiver)
    monkeypatch.setattr("app.services.wiki.ingest_events.publish_wiki_ingest_snapshot", snapshot)
    monkeypatch.setattr(job_runner, "run_post_sync_dedup_scan", dedup)
    job_runner._slice_locks.clear()
    job_runner._running.clear()
    return h


async def _configure(
    ima_db: async_sessionmaker[AsyncSession],
    *,
    backfill_complete: bool = False,
    notes: bool = True,
    agent_id: str | None = None,
) -> None:
    async with ima_db() as db:
        await save_ima_config(db, ImaSyncConfig(knowledge_bases=[], include_notes=notes), agent_id=agent_id)
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


async def _run_two_agents_and(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession], stop: Callable[[], None]
) -> dict[str | None, bool]:
    """Run a slice for the default agent and for ``other``, call ``stop`` while both run, and report which one was still allowed to go on."""
    await _configure(ima_db)
    await _configure(ima_db, agent_id="other")
    harness.gate = asyncio.Event()
    runs = [asyncio.create_task(job_runner.run_ima_sync_job(llm=LLM, agent_id=agent)) for agent in (None, "other")]
    while len(harness.contexts) < 2:
        await asyncio.sleep(0)

    stop()
    may_go_on = {ctx.agent_id: ctx.time_left() > 0 for ctx in harness.contexts}
    harness.gate.set()
    await asyncio.gather(*runs)
    return may_go_on


async def test_stopping_one_agent_reaches_only_its_running_slice(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    may_go_on = await _run_two_agents_and(harness, ima_db, lambda: job_runner.stop_running_slice(None))

    assert may_go_on == {None: False, "other": True}


async def test_stopping_all_slices_reaches_every_agent(harness: Harness, ima_db: async_sessionmaker[AsyncSession]) -> None:
    may_go_on = await _run_two_agents_and(harness, ima_db, job_runner.stop_running_slices)

    assert may_go_on == {None: False, "other": False}


async def test_a_slice_leaves_no_stop_signal_behind_however_it_ends(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _configure(ima_db)
    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    assert job_runner._running == {}

    harness.slice_error = RuntimeError("transport died")
    with pytest.raises(RuntimeError, match="transport died"):
        await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    assert job_runner._running == {}


async def test_a_job_paused_or_removed_after_it_fired_starts_no_slice(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await _configure(ima_db)
    harness.job_active = False

    outcome = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert outcome.skipped and outcome.retry_at is None
    assert harness.contexts == [] and job_runner._running == {}


async def test_a_pause_that_lands_while_the_slice_is_admitted_is_not_lost(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The job is read after the slice registered, so a pause that comes in between that read and the slice's start reaches it."""
    await _configure(ima_db)

    async def pause_lands_during_the_read(agent_id: str | None) -> bool:
        job_runner.stop_running_slice(agent_id)
        return True  # the answer was already read: the job was still active then

    monkeypatch.setattr(job_runner, "is_job_active", pause_lands_during_the_read)

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.contexts[0].time_left() <= 0


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
