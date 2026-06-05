"""Tests for curator_service consolidation integration.

Tests the consolidation preview, execute, agent ref rewrite, and
lock-based mutual exclusion with sweeps.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.skills.curator.consolidation.types import (
    ConsolidationAction,
    ConsolidationActionType,
    ConsolidationPlan,
    ConsolidationReport,
    ConsolidationResult,
)


class TestRewriteAgentSkillRefs:
    """Tests for _rewrite_agent_skill_refs."""

    @pytest.mark.asyncio
    async def test_no_renames_returns_zero(self) -> None:
        """When report has no successful merges, no refs should be rewritten."""
        from app.core.skills.curator_service import _rewrite_agent_skill_refs

        report = ConsolidationReport()
        result = await _rewrite_agent_skill_refs(report)
        assert result == 0

    @pytest.mark.asyncio
    async def test_failed_results_are_skipped(self) -> None:
        """Failed consolidation results should not create rename mappings."""
        from app.core.skills.curator_service import _rewrite_agent_skill_refs

        action = ConsolidationAction(
            action_type=ConsolidationActionType.MERGE,
            target_skill="umbrella",
            source_skills=("src_a",),
            reasoning="test",
        )
        report = ConsolidationReport(
            results=[
                ConsolidationResult(action=action, success=False, error="some error"),
            ]
        )
        result = await _rewrite_agent_skill_refs(report)
        assert result == 0

    @pytest.mark.asyncio
    async def test_successful_merge_rewrites_refs(self) -> None:
        """Successful merge should rewrite agent skill_ids."""
        from app.core.skills.curator_service import _rewrite_agent_skill_refs

        action = ConsolidationAction(
            action_type=ConsolidationActionType.MERGE,
            target_skill="git_operations",
            source_skills=("git_commit", "git_push"),
            reasoning="merge",
        )
        report = ConsolidationReport(
            results=[
                ConsolidationResult(
                    action=action,
                    success=True,
                    archived_skills=("git_commit", "git_push"),
                ),
            ]
        )

        mock_profile = MagicMock()
        mock_profile.skills = ["git_commit", "other_skill", "git_push"]
        mock_profile.agent_id = "agent-1"
        mock_profile.name = "TestAgent"

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        with (
            patch("app.database.connection.get_session", mock_get_session),
            patch(
                "app.database.repositories.agent_repo.AgentRepository.list_profiles",
                AsyncMock(return_value=[mock_profile]),
            ),
            patch(
                "app.database.repositories.agent_repo.AgentRepository.update_profile",
                AsyncMock(),
            ) as mock_update,
        ):
            result = await _rewrite_agent_skill_refs(report)

        assert result == 1
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        new_skills = call_args[0][2]["skills"]
        assert "git_commit" not in new_skills
        assert "git_push" not in new_skills
        assert "git_operations" in new_skills
        assert "other_skill" in new_skills

    @pytest.mark.asyncio
    async def test_create_umbrella_also_rewrites(self) -> None:
        """CREATE_UMBRELLA action should also trigger ref rewrite."""
        from app.core.skills.curator_service import _rewrite_agent_skill_refs

        action = ConsolidationAction(
            action_type=ConsolidationActionType.CREATE_UMBRELLA,
            target_skill="deploy_ops",
            source_skills=("deploy_docker", "deploy_k8s"),
            reasoning="create umbrella",
            umbrella_description="test",
        )
        report = ConsolidationReport(
            results=[
                ConsolidationResult(
                    action=action,
                    success=True,
                    archived_skills=("deploy_docker", "deploy_k8s"),
                ),
            ]
        )

        mock_profile = MagicMock()
        mock_profile.skills = ["deploy_docker", "deploy_k8s", "unrelated"]
        mock_profile.agent_id = "agent-2"
        mock_profile.name = "Agent2"

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        with (
            patch("app.database.connection.get_session", mock_get_session),
            patch(
                "app.database.repositories.agent_repo.AgentRepository.list_profiles",
                AsyncMock(return_value=[mock_profile]),
            ),
            patch(
                "app.database.repositories.agent_repo.AgentRepository.update_profile",
                AsyncMock(),
            ) as mock_update,
        ):
            result = await _rewrite_agent_skill_refs(report)

        assert result == 1
        new_skills = mock_update.call_args[0][2]["skills"]
        assert "deploy_ops" in new_skills
        assert "deploy_docker" not in new_skills
        assert "deploy_k8s" not in new_skills
        assert "unrelated" in new_skills

    @pytest.mark.asyncio
    async def test_rewrite_handles_db_exception(self) -> None:
        """Database error should be caught, returning 0."""
        from app.core.skills.curator_service import _rewrite_agent_skill_refs

        action = ConsolidationAction(
            action_type=ConsolidationActionType.CREATE_UMBRELLA,
            target_skill="umbrella",
            source_skills=("a",),
            reasoning="test",
        )
        report = ConsolidationReport(
            results=[
                ConsolidationResult(action=action, success=True, archived_skills=("a",)),
            ]
        )

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_get_session():
            raise RuntimeError("DB connection failed")
            yield  # type: ignore[misc]

        with patch("app.database.connection.get_session", mock_get_session):
            result = await _rewrite_agent_skill_refs(report)
        assert result == 0

    @pytest.mark.asyncio
    async def test_no_change_needed_zero_updates(self) -> None:
        """When agent has no matching skills, 0 should be returned."""
        from app.core.skills.curator_service import _rewrite_agent_skill_refs

        action = ConsolidationAction(
            action_type=ConsolidationActionType.MERGE,
            target_skill="umbrella",
            source_skills=("old_skill",),
            reasoning="merge",
        )
        report = ConsolidationReport(
            results=[
                ConsolidationResult(action=action, success=True, archived_skills=("old_skill",)),
            ]
        )

        mock_profile = MagicMock()
        mock_profile.skills = ["unrelated_a", "unrelated_b"]
        mock_profile.agent_id = "agent-3"
        mock_profile.name = "Agent3"

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        with (
            patch("app.database.connection.get_session", mock_get_session),
            patch(
                "app.database.repositories.agent_repo.AgentRepository.list_profiles",
                AsyncMock(return_value=[mock_profile]),
            ),
            patch(
                "app.database.repositories.agent_repo.AgentRepository.update_profile",
                AsyncMock(),
            ) as mock_update,
        ):
            result = await _rewrite_agent_skill_refs(report)

        assert result == 0
        mock_update.assert_not_called()


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
                "app.core.skills.curator_service._get_consolidation_deps",
                AsyncMock(return_value=(mock_embed, mock_llm, mock_write)),
            ),
            patch(
                "app.core.skills.curator_service._load_all_skills",
                AsyncMock(return_value=[]),
            ),
        ):
            from app.core.skills.curator_service import run_consolidation_preview

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
                "app.core.skills.curator_service._get_consolidation_deps",
                AsyncMock(return_value=(mock_embed, mock_llm, mock_write)),
            ),
            patch(
                "app.core.skills.curator_service._load_all_skills",
                AsyncMock(return_value=[MagicMock() for _ in range(5)]),
            ),
            patch(
                "myrm_agent_harness.agent.skills.curator.SkillCurator",
                return_value=mock_curator_instance,
            ),
        ):
            from app.core.skills.curator_service import run_consolidation_preview

            plan = await run_consolidation_preview()

        assert not plan.is_empty
        assert plan.actions[0].target_skill == "target"
