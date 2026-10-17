"""Tests for curator consolidation integration.

Tests the consolidation preview and execute services and which skills they hand to the curator.
"""

from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.skills.curator.consolidation.types import (
    ConsolidationAction,
    ConsolidationActionType,
    ConsolidationPlan,
    ConsolidationReport,
    ConsolidationResult,
)
from myrm_agent_harness.backends.skills.types import SkillMetadata

from app.core.skills.curator.local_skills import LocalSkillScan


def _scan(skills: Sequence[SkillMetadata], installed: frozenset[str] = frozenset()) -> AsyncMock:
    """A stand-in for ``scan_local_skills`` that returns the given skills."""
    return AsyncMock(return_value=LocalSkillScan(skills=list(skills), installed_names=installed))


class TestConsolidationPreview:
    """Tests for run_consolidation_preview service function."""

    @pytest.mark.asyncio
    async def test_preview_returns_empty_plan_when_no_skills(self) -> None:
        """Empty skill list should return empty plan."""
        mock_embed = MagicMock()
        mock_llm = MagicMock()
        mock_write = MagicMock()

        with (
            patch(
                "app.core.skills.curator.consolidation._get_consolidation_deps",
                AsyncMock(return_value=(mock_embed, mock_llm, mock_write)),
            ),
            patch("app.core.skills.curator.consolidation.scan_local_skills", _scan([])),
        ):
            from app.core.skills.curator.consolidation import run_consolidation_preview

            plan = await run_consolidation_preview()

        assert plan.is_empty

    @pytest.mark.asyncio
    async def test_preview_returns_plan_from_curator(self) -> None:
        """Should return the plan from curator's run_async."""
        mock_embed = MagicMock()
        mock_llm = MagicMock()
        mock_write = MagicMock()

        expected_plan = ConsolidationPlan(
            actions=[
                ConsolidationAction(
                    action_type=ConsolidationActionType.MERGE,
                    target_skill="target",
                    source_skills=("a", "b"),
                    reasoning="test",
                )
            ],
            total_skills_affected=2,
            estimated_reduction=1,
        )

        mock_run_result = MagicMock(skills_scanned=5)
        mock_curator_instance = MagicMock()
        mock_curator_instance.run_async = AsyncMock(return_value=(mock_run_result, expected_plan))

        with (
            patch(
                "app.core.skills.curator.consolidation._get_consolidation_deps",
                AsyncMock(return_value=(mock_embed, mock_llm, mock_write)),
            ),
            patch("app.core.skills.curator.consolidation.scan_local_skills", _scan([MagicMock() for _ in range(5)])),
            patch(
                "myrm_agent_harness.agent.skills.curator.SkillCurator",
                return_value=mock_curator_instance,
            ),
        ):
            from app.core.skills.curator.consolidation import run_consolidation_preview

            plan = await run_consolidation_preview()

        assert not plan.is_empty
        assert plan.actions[0].target_skill == "target"


class TestConsolidationSparesBoundAndInstalledSkills:
    """Preview and execute hand the bound skills (agents / cron jobs) and the installed ones to the curator."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("dry_run", [True, False])
    async def test_run_async_receives_protected_and_installed_names(self, dry_run: bool) -> None:
        mock_curator_instance = MagicMock()
        mock_curator_instance.run_async = AsyncMock(return_value=(MagicMock(), ConsolidationReport()))

        with (
            patch(
                "app.core.skills.curator.consolidation._get_consolidation_deps",
                AsyncMock(return_value=(MagicMock(), MagicMock(), MagicMock())),
            ),
            patch("app.core.skills.curator.consolidation.scan_local_skills", _scan([MagicMock()], frozenset({"from-store"}))),
            patch(
                "app.core.skills.curator.consolidation.bound_skill_names",
                AsyncMock(return_value=frozenset({"bound"})),
            ),
            patch("myrm_agent_harness.agent.skills.curator.SkillCurator", return_value=mock_curator_instance),
        ):
            from app.core.skills.curator.consolidation import run_consolidation_execute, run_consolidation_preview

            await (run_consolidation_preview() if dry_run else run_consolidation_execute())

        kwargs = mock_curator_instance.run_async.call_args.kwargs
        assert kwargs["protected_names"] == frozenset({"bound"})
        assert kwargs["installed_names"] == frozenset({"from-store"})


class TestConsolidationExecute:
    """Execute answers with what the curator did and nothing else: bound skills never take part, so no reference is rewritten."""

    @pytest.mark.asyncio
    async def test_execute_reports_exactly_what_the_curator_did(self) -> None:
        action = ConsolidationAction(
            action_type=ConsolidationActionType.MERGE,
            target_skill="umbrella",
            source_skills=("a", "b"),
            reasoning="test",
        )
        report = ConsolidationReport(
            results=[ConsolidationResult(action=action, success=True, archived_skills=("a", "b"))],
            skills_before=5,
            skills_after=4,
            total_archived=2,
        )
        mock_curator_instance = MagicMock()
        mock_curator_instance.run_async = AsyncMock(return_value=(MagicMock(), report))

        with (
            patch(
                "app.core.skills.curator.consolidation._get_consolidation_deps",
                AsyncMock(return_value=(MagicMock(), MagicMock(), MagicMock())),
            ),
            patch("app.core.skills.curator.consolidation.scan_local_skills", _scan([MagicMock()])),
            patch("app.core.skills.curator.consolidation.bound_skill_names", AsyncMock(return_value=frozenset())),
            patch("myrm_agent_harness.agent.skills.curator.SkillCurator", return_value=mock_curator_instance),
        ):
            from app.core.skills.curator.consolidation import run_consolidation_execute

            result = await run_consolidation_execute()

        assert result == {
            "success_count": 1,
            "failure_count": 0,
            "total_archived": 2,
            "total_created": 0,
            "net_reduction": 1,
            "summary": report.to_summary(),
        }
