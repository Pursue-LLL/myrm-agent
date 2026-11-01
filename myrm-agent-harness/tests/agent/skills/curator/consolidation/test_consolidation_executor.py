"""The consolidation executor applies plan actions through the skill write backend."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.skills.curator.consolidation.executor import ConsolidationExecutor
from myrm_agent_harness.agent.skills.curator.consolidation.types import (
    ConsolidationAction,
    ConsolidationActionType,
)
from tests.support.skill_factory import make_skill


class TestConsolidationExecutor:
    """Tests for ConsolidationExecutor."""

    @pytest.fixture
    def mock_write_backend(self) -> MagicMock:
        backend = MagicMock()
        backend.save_skill = AsyncMock(
            return_value=MagicMock(
                success=True,
                saved_path="/tmp/skills/umbrella_skill",
                error="",
            )
        )
        backend.write_resource = AsyncMock(return_value=MagicMock(success=True))
        return backend

    @pytest.fixture
    def stats_collector(self) -> MagicMock:
        return MagicMock()

    @pytest.mark.asyncio
    async def test_execute_create_umbrella(self, mock_write_backend: MagicMock, stats_collector: MagicMock) -> None:
        skills = [
            make_skill("git_commit_skill", "Commit changes"),
            make_skill("git_push_skill", "Push changes"),
            make_skill("git_merge_skill", "Merge branches"),
        ]
        action = ConsolidationAction(
            action_type=ConsolidationActionType.CREATE_UMBRELLA,
            target_skill="git_operations_skill",
            source_skills=("git_commit_skill", "git_push_skill", "git_merge_skill"),
            reasoning="Create umbrella for git ops",
            umbrella_description="Unified git operations",
            umbrella_content_outline="Covers commit, push, merge operations.",
        )

        executor = ConsolidationExecutor(mock_write_backend, stats_collector, skills)
        report = await executor.execute([action])

        assert report.success_count == 1
        assert report.failure_count == 0
        assert report.total_created == 1
        mock_write_backend.save_skill.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_merge(self, mock_write_backend: MagicMock, stats_collector: MagicMock) -> None:
        skills = [
            make_skill("git_operations_skill", "Git operations"),
            make_skill("git_commit_skill", "Commit changes"),
        ]
        action = ConsolidationAction(
            action_type=ConsolidationActionType.MERGE,
            target_skill="git_operations_skill",
            source_skills=("git_commit_skill",),
            reasoning="Merge into existing",
        )

        executor = ConsolidationExecutor(mock_write_backend, stats_collector, skills)
        report = await executor.execute([action])

        assert report.success_count == 1
        mock_write_backend.write_resource.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_missing_target(self, mock_write_backend: MagicMock, stats_collector: MagicMock) -> None:
        skills = [make_skill("only_skill", "Only skill")]
        action = ConsolidationAction(
            action_type=ConsolidationActionType.MERGE,
            target_skill="nonexistent_skill",
            source_skills=("only_skill",),
            reasoning="test",
        )

        executor = ConsolidationExecutor(mock_write_backend, stats_collector, skills)
        report = await executor.execute([action])

        assert report.failure_count == 1
        assert "not found" in report.results[0].error


class TestConsolidationExecutorDemote:
    """Tests for ConsolidationExecutor DEMOTE action."""

    @pytest.fixture
    def mock_write_backend(self) -> MagicMock:
        backend = MagicMock()
        backend.write_resource = AsyncMock(return_value=MagicMock(success=True))
        return backend

    @pytest.fixture
    def stats_collector(self) -> MagicMock:
        return MagicMock()

    @pytest.mark.asyncio
    async def test_execute_demote_success(self, mock_write_backend: MagicMock, stats_collector: MagicMock) -> None:
        skills = [
            make_skill("main_skill", "Main skill"),
            make_skill("narrow_a", "Narrow helper A"),
            make_skill("narrow_b", "Narrow helper B"),
        ]
        action = ConsolidationAction(
            action_type=ConsolidationActionType.DEMOTE,
            target_skill="main_skill",
            source_skills=("narrow_a", "narrow_b"),
            reasoning="Narrow skills should be support files",
            demote_target_dir="references",
        )

        executor = ConsolidationExecutor(mock_write_backend, stats_collector, skills)
        report = await executor.execute([action])

        assert report.success_count == 1
        assert report.failure_count == 0
        assert mock_write_backend.write_resource.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_demote_no_sources(self, mock_write_backend: MagicMock, stats_collector: MagicMock) -> None:
        skills = [make_skill("main_skill")]
        action = ConsolidationAction(
            action_type=ConsolidationActionType.DEMOTE,
            target_skill="main_skill",
            source_skills=("nonexistent_a", "nonexistent_b"),
            reasoning="test",
        )

        executor = ConsolidationExecutor(mock_write_backend, stats_collector, skills)
        report = await executor.execute([action])

        assert report.failure_count == 1
        assert "No source" in report.results[0].error


class TestConsolidationExecutorKeep:
    """Tests for ConsolidationExecutor KEEP action."""

    @pytest.mark.asyncio
    async def test_execute_keep(self) -> None:
        action = ConsolidationAction(
            action_type=ConsolidationActionType.KEEP,
            target_skill="any_skill",
            source_skills=("a", "b"),
            reasoning="No action needed",
        )
        backend = MagicMock()
        stats = MagicMock()
        executor = ConsolidationExecutor(backend, stats, [])
        report = await executor.execute([action])

        assert report.success_count == 1
        assert report.failure_count == 0


class TestConsolidationExecutorExceptionHandling:
    """Tests for executor error handling paths."""

    @pytest.mark.asyncio
    async def test_execute_action_raises_exception(self) -> None:
        backend = MagicMock()
        backend.save_skill = AsyncMock(side_effect=RuntimeError("Write failed"))
        stats = MagicMock()

        skills = [make_skill("src_skill")]
        action = ConsolidationAction(
            action_type=ConsolidationActionType.CREATE_UMBRELLA,
            target_skill="new_umbrella",
            source_skills=("src_skill",),
            reasoning="test exception",
            umbrella_description="test",
        )

        executor = ConsolidationExecutor(backend, stats, skills)
        report = await executor.execute([action])

        assert report.failure_count == 1
        assert "Write failed" in report.results[0].error
