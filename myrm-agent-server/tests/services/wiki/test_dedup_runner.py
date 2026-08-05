"""Tests for wiki dedup runner SSOT."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import (
    CorpusDedupScanner,
    DispositionAction,
    GroupStatus,
)

from app.services.wiki import dedup_runner
from app.services.wiki.vault_service import (
    get_wiki_archiver,
    reset_wiki_archiver_cache_for_tests,
)


@pytest.fixture
def wiki_archiver(tmp_path):
    reset_wiki_archiver_cache_for_tests()
    dedup_runner._running_scans.clear()
    harness = tmp_path / "harness"
    llm = MagicMock()
    with patch("app.config.settings.settings") as mock_settings:
        mock_settings.database.harness_dir = str(harness)
        mock_settings.database.state_dir = str(tmp_path)
        archiver = get_wiki_archiver(llm)
    with patch(
        "app.services.wiki.vault_service.get_wiki_archiver", return_value=archiver
    ):
        yield archiver
    dedup_runner._running_scans.clear()
    reset_wiki_archiver_cache_for_tests()


def _write_duplicate_pair(
    archiver, *, content: str = "# Dup\n\nShared runner test body."
) -> None:
    for relative_path in ("runner/a.md", "runner/b.md"):
        path = archiver._structure.get_raw_file_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.mark.asyncio
async def test_run_wiki_dedup_scan_job_reports_open_groups(wiki_archiver) -> None:
    _write_duplicate_pair(wiki_archiver)
    result = await dedup_runner.run_wiki_dedup_scan_job()
    assert result.skipped is False
    assert result.scan_result is not None
    assert result.scan_result.open_groups >= 1
    assert "duplicate group" in result.summary_text


@pytest.mark.asyncio
async def test_run_wiki_dedup_scan_job_silent_when_no_open_groups(
    wiki_archiver,
) -> None:
    path = wiki_archiver._structure.get_raw_file_path("solo.md")
    path.write_text("# Solo\n\nUnique body.", encoding="utf-8")
    result = await dedup_runner.run_wiki_dedup_scan_job()
    assert result.summary_text == "[SILENT]"


@pytest.mark.asyncio
async def test_run_wiki_dedup_scan_job_skips_when_compile_busy(wiki_archiver) -> None:
    wiki_archiver._queue.get_stats = MagicMock(return_value={"processing": 1})
    result = await dedup_runner.run_wiki_dedup_scan_job()
    assert result.skipped is True
    assert result.skipped_reason == "compile_in_progress"


@pytest.mark.asyncio
async def test_schedule_wiki_dedup_scan_accepts_background_task(wiki_archiver) -> None:
    _write_duplicate_pair(wiki_archiver)
    result = await dedup_runner.schedule_wiki_dedup_scan()
    assert result.accepted is True
    assert result.skipped is False


@pytest.mark.asyncio
async def test_schedule_wiki_dedup_scan_skips_when_scan_already_running(
    wiki_archiver,
) -> None:
    dedup_runner._running_scans.add("__default__")
    result = await dedup_runner.schedule_wiki_dedup_scan()
    assert result.accepted is False
    assert result.skipped_reason == "scan_in_progress"


def test_wiki_dedup_blocks_compile_when_exact_group_open(wiki_archiver) -> None:
    _write_duplicate_pair(wiki_archiver)
    CorpusDedupScanner(wiki_archiver._structure).scan(incremental=False)
    assert dedup_runner.wiki_dedup_blocks_compile() is True


def test_wiki_dedup_checklist_ready_requires_scan_before_compile(wiki_archiver) -> None:
    _write_duplicate_pair(wiki_archiver)
    assert dedup_runner.wiki_dedup_checklist_ready() is False
    CorpusDedupScanner(wiki_archiver._structure).scan(incremental=False)
    assert dedup_runner.wiki_dedup_checklist_ready() is False


def test_wiki_dedup_checklist_ready_when_vault_empty(wiki_archiver) -> None:
    assert wiki_archiver._structure.list_raw_files() == []
    assert dedup_runner.wiki_dedup_checklist_ready() is True


def test_get_wiki_dedup_stats_progress_and_groups(wiki_archiver) -> None:
    _write_duplicate_pair(wiki_archiver)
    CorpusDedupScanner(wiki_archiver._structure).scan(incremental=False)
    stats = dedup_runner.get_wiki_dedup_stats()
    progress = dedup_runner.get_wiki_dedup_progress()
    groups = dedup_runner.list_wiki_dedup_groups()
    assert stats.duplicate_groups_pending >= 1
    assert progress.phase == "done"
    assert len(groups) >= 1


def test_get_wiki_dedup_group_snippets(wiki_archiver) -> None:
    _write_duplicate_pair(wiki_archiver)
    scanner = CorpusDedupScanner(wiki_archiver._structure)
    scanner.scan(incremental=False)
    group_id = scanner.store.list_groups(status=GroupStatus.OPEN)[0].group_id
    snippets = dedup_runner.get_wiki_dedup_group_snippets(
        agent_id=None, group_id=group_id
    )
    assert len(snippets) == 2
    assert snippets[0].snippet


def test_get_wiki_dedup_group_snippets_missing_group_raises(wiki_archiver) -> None:
    with pytest.raises(ValueError, match="Duplicate group not found"):
        dedup_runner.get_wiki_dedup_group_snippets(agent_id=None, group_id=999_999)


@pytest.mark.asyncio
async def test_apply_wiki_dedup_disposition_dismiss(wiki_archiver) -> None:
    _write_duplicate_pair(wiki_archiver)
    scanner = CorpusDedupScanner(wiki_archiver._structure)
    scanner.scan(incremental=False)
    group_id = scanner.store.list_groups(status=GroupStatus.OPEN)[0].group_id
    result = await dedup_runner.apply_wiki_dedup_disposition(
        agent_id=None,
        group_id=group_id,
        action=DispositionAction.DISMISS,
        reason="",
    )
    assert result.action == DispositionAction.DISMISS


def test_get_wiki_dedup_vault_hygiene(wiki_archiver) -> None:
    snapshot = dedup_runner.get_wiki_dedup_vault_hygiene()
    assert snapshot.trashed == ()
    assert snapshot.excluded == ()


@pytest.mark.asyncio
async def test_schedule_wiki_dedup_scan_skips_when_compile_busy(wiki_archiver) -> None:
    wiki_archiver._queue.get_stats = MagicMock(return_value={"processing": 1})
    result = await dedup_runner.schedule_wiki_dedup_scan()
    assert result.accepted is False
    assert result.skipped_reason == "compile_in_progress"


@pytest.mark.asyncio
async def test_restore_wiki_dedup_trashed_requeues_scan(wiki_archiver) -> None:
    _write_duplicate_pair(wiki_archiver)
    scanner = CorpusDedupScanner(wiki_archiver._structure)
    scanner.scan(incremental=False)
    group_id = scanner.store.list_groups(status=GroupStatus.OPEN)[0].group_id
    await dedup_runner.apply_wiki_dedup_disposition(
        agent_id=None,
        group_id=group_id,
        action=DispositionAction.TRASH,
        reason="restore runner test",
    )
    trashed = dedup_runner.get_wiki_dedup_vault_hygiene().trashed[0].relative_path
    restored = await dedup_runner.restore_wiki_dedup_trashed(
        agent_id=None, relative_path=trashed
    )
    assert restored.relative_path == trashed
    assert wiki_archiver._structure.get_raw_file_path(trashed).exists()


@pytest.mark.asyncio
async def test_undo_wiki_dedup_excluded_requeues_scan(wiki_archiver) -> None:
    _write_duplicate_pair(wiki_archiver)
    scanner = CorpusDedupScanner(wiki_archiver._structure)
    scanner.scan(incremental=False)
    group_id = scanner.store.list_groups(status=GroupStatus.OPEN)[0].group_id
    await dedup_runner.apply_wiki_dedup_disposition(
        agent_id=None,
        group_id=group_id,
        action=DispositionAction.EXCLUDE,
        reason="undo runner test",
    )
    excluded = dedup_runner.get_wiki_dedup_vault_hygiene().excluded[0].relative_path
    restored = await dedup_runner.undo_wiki_dedup_excluded(
        agent_id=None, relative_path=excluded
    )
    assert restored.relative_path == excluded


@pytest.mark.asyncio
async def test_execute_background_scan_records_failure_progress(wiki_archiver) -> None:
    with patch(
        "app.services.wiki.dedup_runner._run_scan_sync",
        side_effect=RuntimeError("scan boom"),
    ):
        await dedup_runner._execute_background_scan(agent_id=None, incremental=True)
    progress = dedup_runner.get_wiki_dedup_progress()
    assert progress.phase == "failed"
    assert dedup_runner.is_wiki_dedup_scan_running() is False


def test_is_wiki_dedup_scan_running(wiki_archiver) -> None:
    assert dedup_runner.is_wiki_dedup_scan_running() is False
    dedup_runner._running_scans.add("__default__")
    assert dedup_runner.is_wiki_dedup_scan_running() is True
