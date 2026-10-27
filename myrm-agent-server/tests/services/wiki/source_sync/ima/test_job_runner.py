"""Cron entry: single flight, wiring decisions, and the mapping of a slice outcome to scheduler advice."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupGovernor, CorpusDedupScanner
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.source_sync.ima import job_runner
from app.services.wiki.source_sync.ima.engine import SliceOutcome

from .job_runner_support import CREDENTIALS, LLM, FakeArchiver, Harness, configure


async def test_not_connected_or_nothing_selected_is_a_quiet_skip(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    harness.credentials = None
    await configure(ima_db)
    skipped = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    assert skipped.skipped and skipped.summary_text == "[SILENT]" and skipped.retry_at is None

    harness.credentials = CREDENTIALS
    await configure(ima_db, notes=False)
    assert (await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)).skipped
    assert harness.contexts == []


async def test_a_second_overlapping_run_for_the_same_agent_is_skipped(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await configure(ima_db)
    harness.gate = asyncio.Event()
    first = asyncio.create_task(job_runner.run_ima_sync_job(llm=LLM, agent_id=None))
    while not harness.contexts:
        await asyncio.sleep(0)

    overlapping = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    harness.gate.set()
    await first

    assert overlapping.skipped and len(harness.contexts) == 1


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
    await configure(ima_db, backfill_complete=backfill_complete)
    harness.auto_compile = auto_compile

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert (harness.contexts[0].compiler_enqueue is not None) is expect_compile


async def test_continuation_is_rearmed_through_retry_at(harness: Harness, ima_db: async_sessionmaker[AsyncSession]) -> None:
    await configure(ima_db)
    before = datetime.now(UTC)

    outcome = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert not outcome.skipped and outcome.summary_text == "[SILENT]"
    assert outcome.retry_at is not None and timedelta(seconds=4) <= outcome.retry_at - before <= timedelta(seconds=7)


async def test_finished_pass_reports_the_count_and_runs_the_post_publish_hooks(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await configure(ima_db)
    harness.outcome = SliceOutcome(finished=True, retry_after_s=None, published=3, generation_total=7)

    outcome = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert outcome.summary_text == "ima: 7 imported" and outcome.retry_at is None and not outcome.skipped
    assert harness.snapshots == 1 and harness.dedups == 1


async def test_a_pass_that_published_nothing_stays_silent_and_skips_dedup(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await configure(ima_db)
    harness.outcome = SliceOutcome(finished=True, retry_after_s=None, published=0, generation_total=0)

    outcome = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert outcome.summary_text == "[SILENT]"
    assert harness.snapshots == 0 and harness.dedups == 0


async def test_auth_stops_the_job_without_a_retry_and_rate_limit_waits(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await configure(ima_db)
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
    await configure(ima_db, backfill_complete=True)
    harness.publish = {"ima/KB1/a.md": SAME_BODY, "ima/KB2/a-copy.md": SAME_BODY, "ima/KB1/unique.md": "# Unique\n\nAlone."}
    harness.outcome = SliceOutcome(finished=False, retry_after_s=5.0, published=3, generation_total=0)

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == ["scan", "enqueue:unique.md", "snapshot"]


async def test_a_slice_with_nothing_held_back_does_not_scan(harness: Harness, ima_db: async_sessionmaker[AsyncSession]) -> None:
    await configure(ima_db, backfill_complete=True)

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == []


async def test_the_first_backfill_is_never_queued_by_a_slice(harness: Harness, ima_db: async_sessionmaker[AsyncSession]) -> None:
    await configure(ima_db, backfill_complete=False)
    harness.publish = {"ima/KB1/a.md": "# A\n\nfirst"}
    harness.outcome = SliceOutcome(finished=False, retry_after_s=5.0, published=1, generation_total=0)

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == ["snapshot"]


async def test_a_failing_slice_still_hands_over_what_it_already_published(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await configure(ima_db, backfill_complete=True)
    harness.publish = {"ima/KB1/a.md": "# A\n\nfirst"}
    harness.slice_error = RuntimeError("transport died")

    with pytest.raises(RuntimeError, match="transport died"):
        await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == ["enqueue:a.md"]


async def test_a_scan_that_did_not_complete_does_not_hold_back_files_whatever_stored_groups_say(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    await configure(ima_db, backfill_complete=True)
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
    await configure(ima_db, backfill_complete=True)
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
    await configure(ima_db, backfill_complete=True)
    structure = FakeArchiver(tmp_path, harness.events)._structure
    leftover = structure.get_raw_file_path("ima/KB1/leftover.md")
    leftover.parent.mkdir(parents=True, exist_ok=True)
    leftover.write_text("# Leftover\n\nScanned, then the slice died.", encoding="utf-8")
    CorpusDedupGovernor(structure).hold_for_compile(["ima/KB1/leftover.md"])
    CorpusDedupScanner(structure).scan(incremental=False)

    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert harness.events == ["enqueue:leftover.md"]
