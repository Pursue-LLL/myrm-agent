"""Tests for wiki maintain runner SSOT."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.wiki.core.types import LintResult
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode

from app.services.wiki.maintain_runner import _build_summary_text, run_wiki_maintain_job
from app.services.wiki.maintain_schemas import WikiMaintainRunResult


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

    with patch("app.services.wiki.vault_service.get_wiki_archiver", return_value=mock_archiver):
        with patch("app.services.wiki.maintain_runner.get_session", _fake_session):
            with patch(
                "app.services.wiki.maintain_runner.save_wiki_maintain_state",
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

    with patch("app.services.wiki.vault_service.get_wiki_archiver", return_value=mock_archiver):
        with patch("app.services.wiki.asset_index_service.run_wiki_asset_index", new=AsyncMock()):
            with patch("app.services.wiki.vault_git_snapshot.after_wiki_vault_mutation", new=AsyncMock()):
                with patch("app.services.wiki.maintain_runner.get_session", _fake_session):
                    with patch(
                        "app.services.wiki.dedup_runner.get_wiki_dedup_stats",
                        return_value=MagicMock(duplicate_groups_pending=0),
                    ):
                        with patch(
                            "app.services.wiki.maintain_runner.save_wiki_maintain_state",
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
