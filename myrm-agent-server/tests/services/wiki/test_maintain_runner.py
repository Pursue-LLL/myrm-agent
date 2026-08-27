"""Tests for wiki maintain runner SSOT."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.wiki.core.types import LintResult
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode

from app.services.wiki.maintain import run_wiki_maintain_job
from app.services.wiki.maintain.runner import _build_summary_text
from app.services.wiki.maintain.schemas import WikiMaintainRunResult


@asynccontextmanager
async def _fake_session():
    yield MagicMock()


def test_build_summary_silent_when_only_unfixed_issues() -> None:
    result = WikiMaintainRunResult(
        mode="structural",
        issues_found=3,
        issues_fixed=0,
    )
    assert _build_summary_text(result=result) == "[SILENT]"


@pytest.mark.asyncio
async def test_skip_when_compile_processing() -> None:
    mock_archiver = MagicMock()
    mock_archiver._queue.get_stats.return_value = {"processing": 1}
    mock_archiver._linter = MagicMock()

    with patch("app.services.wiki.vault.get_wiki_archiver", return_value=mock_archiver):
        with patch("app.services.wiki.maintain.runner.get_session", _fake_session):
            with patch(
                "app.services.wiki.maintain.runner.save_wiki_maintain_state",
                new=AsyncMock(),
            ) as save_mock:
                result = await run_wiki_maintain_job(
                    llm=MagicMock(),
                    agent_id="agent-1",
                    mode=MaintainMode.STRUCTURAL,
                )

    assert result.skipped is True
    assert result.skipped_reason == "compile_in_progress"
    assert result.summary_text == "[SILENT]"
    mock_archiver._linter.lint_and_maintain.assert_not_called()
    save_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_structural_maintain_persists_state() -> None:
    mock_archiver = MagicMock()
    mock_archiver._queue.get_stats.return_value = {"processing": 0}
    mock_archiver._linter.lint_and_maintain = AsyncMock(
        return_value=LintResult(
            issues_found=2,
            issues_fixed=1,
            connections_discovered=0,
            duration_ms=10,
            issues=[],
        )
    )

    with patch("app.services.wiki.vault.get_wiki_archiver", return_value=mock_archiver):
        with patch(
            "app.services.wiki.asset_index_service.run_wiki_asset_index",
            new=AsyncMock(),
        ):
            with patch("app.services.wiki.vault.after_wiki_vault_mutation", new=AsyncMock()):
                with patch("app.services.wiki.maintain.runner.get_session", _fake_session):
                    with patch(
                        "app.services.wiki.dedup_runner.get_wiki_dedup_stats",
                        return_value=MagicMock(duplicate_groups_pending=0),
                    ):
                        with patch(
                            "app.services.wiki.maintain.runner.save_wiki_maintain_state",
                            new=AsyncMock(),
                        ) as save_mock:
                            result = await run_wiki_maintain_job(
                                llm=MagicMock(),
                                agent_id="agent-1",
                                mode=MaintainMode.STRUCTURAL,
                            )

    mock_archiver._linter.lint_and_maintain.assert_awaited_once()
    assert mock_archiver._linter.lint_and_maintain.await_args.kwargs["mode"] == MaintainMode.STRUCTURAL
    assert result.issues_found == 2
    assert result.issues_fixed == 1
    assert "fixed" in result.summary_text.lower()
    save_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_only_maintain_no_fix_and_generates_markdown_report() -> None:
    from myrm_agent_harness.toolkits.wiki.core.types import LintIssue

    mock_archiver = MagicMock()
    mock_archiver._queue.get_stats.return_value = {"processing": 0}
    mock_issue = LintIssue(
        issue_type="broken_link",
        severity="high",
        location="concepts/service.md",
        description="Broken link to missing-node",
        action_kind="repair",
        can_auto_fix=False,
    )
    mock_archiver._linter.scan = AsyncMock(return_value=([mock_issue], {}))
    mock_archiver._linter.lint_and_maintain = AsyncMock()

    with patch("app.services.wiki.vault.get_wiki_archiver", return_value=mock_archiver):
        with patch("app.services.wiki.maintain.runner.get_session", _fake_session):
            with patch(
                "app.services.wiki.dedup_runner.get_wiki_dedup_stats",
                return_value=MagicMock(duplicate_groups_pending=0),
            ):
                with patch(
                    "app.services.wiki.maintain.runner.save_wiki_maintain_state",
                    new=AsyncMock(),
                ) as save_mock:
                    result = await run_wiki_maintain_job(
                        llm=None,
                        agent_id="agent-1",
                        mode="list_only",
                    )

    mock_archiver._linter.scan.assert_awaited_once_with(
        mode=MaintainMode.STRUCTURAL,
        include_raw_security=False,
    )
    mock_archiver._linter.lint_and_maintain.assert_not_called()
    assert result.mode == "list_only"
    assert result.issues_found == 1
    assert result.issues_fixed == 0
    assert "Wiki 知识库健康周检报告" in result.summary_text
    assert "严重断链: 1 处" in result.summary_text
    assert "/settings/knowledge" in result.summary_text
    save_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_only_maintain_all_green_report() -> None:
    mock_archiver = MagicMock()
    mock_archiver._queue.get_stats.return_value = {"processing": 0}
    mock_archiver._linter.scan = AsyncMock(return_value=([], {}))

    with patch("app.services.wiki.vault.get_wiki_archiver", return_value=mock_archiver):
        with patch("app.services.wiki.maintain.runner.get_session", _fake_session):
            with patch(
                "app.services.wiki.dedup_runner.get_wiki_dedup_stats",
                return_value=MagicMock(duplicate_groups_pending=0),
            ):
                with patch(
                    "app.services.wiki.maintain.runner.save_wiki_maintain_state",
                    new=AsyncMock(),
                ):
                    result = await run_wiki_maintain_job(
                        llm=None,
                        agent_id="agent-1",
                        mode="list_only",
                    )

    assert result.mode == "list_only"
    assert result.issues_found == 0
    assert "全库状态极佳" in result.summary_text
    assert "/settings/knowledge" in result.summary_text


def test_state_from_run_result_maps_fields() -> None:
    from app.services.wiki.maintain.state_store import state_from_run_result

    result = WikiMaintainRunResult(
        skipped=True,
        skipped_reason="no_content",
        mode="structural",
        issues_found=3,
        issues_fixed=2,
        connections_discovered=1,
        duration_ms=42,
        summary_text="Fixed 2",
    )

    state = state_from_run_result(result)

    assert state.last_mode == "structural"
    assert state.last_issues_found == 3
    assert state.last_issues_fixed == 2
    assert state.last_connections_discovered == 1
    assert state.last_duration_ms == 42
    assert state.last_skipped_reason == "no_content"
    assert state.last_output == "Fixed 2"
    assert state.last_run_at is not None
