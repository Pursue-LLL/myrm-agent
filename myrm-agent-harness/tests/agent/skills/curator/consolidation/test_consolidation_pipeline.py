"""The consolidation pipeline end to end: eligibility, detect, judge, execute, and the curator that runs it."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.skills.curator.consolidation.orchestrator import SkillConsolidator
from myrm_agent_harness.agent.skills.curator.consolidation.types import (
    ConsolidationActionType,
    ConsolidationPlan,
    ConsolidationReport,
)
from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus
from tests.support.skill_factory import make_skill


class TestSkillConsolidatorOrchestrator:
    """Tests for the top-level SkillConsolidator."""

    @pytest.fixture
    def mock_deps(self) -> tuple[MagicMock, MagicMock, MagicMock]:
        return MagicMock(), MagicMock(), MagicMock()

    @pytest.mark.asyncio
    async def test_run_too_few_skills(self, mock_deps: tuple[MagicMock, MagicMock, MagicMock]) -> None:
        llm, write, stats = mock_deps
        consolidator = SkillConsolidator(llm, write, stats, min_skills_for_consolidation=10)
        skills = [make_skill(f"skill_{i}") for i in range(5)]
        result = await consolidator.run(skills, dry_run=True)
        assert isinstance(result, ConsolidationPlan)
        assert result.is_empty

    def test_filter_eligible_excludes_pinned(self) -> None:
        skills = [
            make_skill("normal_skill"),
            make_skill("pinned_skill", pinned=True),
            make_skill("archived_skill", status=SkillLifecycleStatus.ARCHIVED),
        ]
        eligible = SkillConsolidator._filter_eligible(skills)
        assert len(eligible) == 1
        assert eligible[0].name == "normal_skill"

    def test_filter_eligible_excludes_mcp(self) -> None:
        mcp_skill = make_skill("mcp_skill", storage_path=None)
        mcp_skill.storage_path = None
        skills = [make_skill("normal"), mcp_skill]
        eligible = SkillConsolidator._filter_eligible(skills)
        names = [s.name for s in eligible]
        assert "mcp_skill" not in names


class TestSkillConsolidatorFullPipeline:
    """Tests for orchestrator full execution path (non-dry-run)."""

    @pytest.mark.asyncio
    async def test_run_dry_run_with_detected_clusters(self) -> None:
        """Full pipeline: enough skills, clusters detected, plan returned."""
        from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment

        mock_structured = AsyncMock(
            return_value=_ClusterJudgment(
                action="create_umbrella",
                target_skill_name="git_operations_skill",
                reasoning="Create umbrella for git domain",
                umbrella_description="Git operations umbrella",
                umbrella_content_outline="Covers all git operations.",
            )
        )
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))

        mock_write = MagicMock()
        mock_stats = MagicMock()

        consolidator = SkillConsolidator(
            mock_llm,
            mock_write,
            mock_stats,
            min_skills_for_consolidation=3,
            min_cluster_size=3,
        )

        skills = [
            make_skill("git_commit_skill", "Commit changes"),
            make_skill("git_push_skill", "Push to remote"),
            make_skill("git_merge_skill", "Merge branches"),
            make_skill("deploy_skill", "Deploy app"),
        ]

        result = await consolidator.run(skills, dry_run=True)
        assert isinstance(result, ConsolidationPlan)
        assert not result.is_empty
        assert result.actions[0].action_type == ConsolidationActionType.CREATE_UMBRELLA

    @pytest.mark.asyncio
    async def test_run_execute_mode(self) -> None:
        """Full pipeline execute mode: creates umbrella, archives sources."""
        from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment

        mock_structured = AsyncMock(
            return_value=_ClusterJudgment(
                action="merge",
                target_skill_name="git_commit_skill",
                reasoning="Merge into existing broader skill",
            )
        )
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))

        mock_write = MagicMock()
        mock_write.write_resource = AsyncMock(return_value=MagicMock(success=True))
        mock_stats = MagicMock()

        consolidator = SkillConsolidator(
            mock_llm,
            mock_write,
            mock_stats,
            min_skills_for_consolidation=3,
            min_cluster_size=3,
        )

        skills = [
            make_skill("git_commit_skill", "Commit changes"),
            make_skill("git_push_skill", "Push to remote"),
            make_skill("git_merge_skill", "Merge branches"),
            make_skill("deploy_skill", "Deploy app"),
        ]

        result = await consolidator.run(skills, dry_run=False)
        assert isinstance(result, ConsolidationReport)
        assert result.success_count >= 1

    @pytest.mark.asyncio
    async def test_run_no_clusters_detected(self) -> None:
        """Pipeline with enough skills but no shared name prefix: the judge is never asked."""
        mock_llm = MagicMock()
        mock_write = MagicMock()
        mock_stats = MagicMock()

        consolidator = SkillConsolidator(
            mock_llm,
            mock_write,
            mock_stats,
            min_skills_for_consolidation=3,
            min_cluster_size=3,
        )

        skills = [
            make_skill(f"{prefix}_helper", "Format a date for display")
            for prefix in ("alpha", "beta", "gamma", "delta")
        ]

        result = await consolidator.run(skills, dry_run=True)
        assert isinstance(result, ConsolidationPlan)
        assert result.is_empty
        mock_llm.with_structured_output.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_judge_returns_keep_for_all(self) -> None:
        """Pipeline where judge decides KEEP for all clusters."""
        from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment

        mock_structured = AsyncMock(
            return_value=_ClusterJudgment(
                action="keep",
                target_skill_name="any",
                reasoning="Skills serve distinct purposes",
            )
        )
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))

        mock_write = MagicMock()
        mock_stats = MagicMock()

        consolidator = SkillConsolidator(
            mock_llm,
            mock_write,
            mock_stats,
            min_skills_for_consolidation=3,
            min_cluster_size=3,
        )

        skills = [
            make_skill("git_commit_skill", "Commit"),
            make_skill("git_push_skill", "Push"),
            make_skill("git_merge_skill", "Merge"),
            make_skill("deploy_skill", "Deploy"),
        ]

        result = await consolidator.run(skills, dry_run=True)
        assert isinstance(result, ConsolidationPlan)
        assert result.is_empty


class TestPreviewMatchesExecution:
    """The reduction the preview promises is the reduction the execution delivers."""

    @staticmethod
    def _consolidator(action: str, target: str) -> SkillConsolidator:
        from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment

        judgment = _ClusterJudgment(
            action=action,
            target_skill_name=target,
            reasoning="The members implement the same workflow",
            umbrella_description="Git operations umbrella",
            umbrella_content_outline="Covers all git operations.",
        )
        llm = MagicMock()
        llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=AsyncMock(return_value=judgment)))
        write = MagicMock()
        write.write_resource = AsyncMock(return_value=MagicMock(success=True))
        write.save_skill = AsyncMock(return_value=MagicMock(success=True, saved_path="/tmp/skills/umbrella", error=""))
        return SkillConsolidator(llm, write, MagicMock(), min_skills_for_consolidation=3, min_cluster_size=3)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action", "target", "expected_reduction"),
        [
            pytest.param("merge", "git_commit_skill", 2, id="merge-archives-every-source"),
            pytest.param("demote", "git_commit_skill", 2, id="demote-archives-every-source"),
            pytest.param("create_umbrella", "git_operations_skill", 2, id="umbrella-adds-one-skill"),
        ],
    )
    async def test_estimated_reduction_equals_executed_net_reduction(
        self, action: str, target: str, expected_reduction: int
    ) -> None:
        skills = [
            make_skill("git_commit_skill", "Commit changes"),
            make_skill("git_push_skill", "Push to remote"),
            make_skill("git_merge_skill", "Merge branches"),
            make_skill("deploy_skill", "Deploy app"),
        ]

        plan = await self._consolidator(action, target).run(skills, dry_run=True)
        report = await self._consolidator(action, target).run(skills, dry_run=False)

        assert isinstance(plan, ConsolidationPlan)
        assert isinstance(report, ConsolidationReport)
        assert report.failure_count == 0
        assert report.net_reduction == expected_reduction
        assert plan.estimated_reduction == report.net_reduction


class TestCuratorEngineConsolidationIntegration:
    """Tests for SkillCurator async consolidation integration."""

    @pytest.mark.asyncio
    async def test_run_async_without_consolidation(self, tmp_path: Path) -> None:
        from myrm_agent_harness.agent.skills.curator.engine import SkillCurator
        from myrm_agent_harness.backends.skills.curator_config import CuratorConfig
        from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        config = CuratorConfig(enabled=True, consolidation_enabled=False)
        collector = SkillStatsCollector()
        curator = SkillCurator(collector, config)

        assert not curator.consolidation_available
        _result, consolidation = await curator.run_async([])
        assert consolidation is None

    @pytest.mark.asyncio
    async def test_run_async_with_consolidation_deps(self, tmp_path: Path) -> None:
        from myrm_agent_harness.agent.skills.curator.engine import SkillCurator
        from myrm_agent_harness.backends.skills.curator_config import CuratorConfig
        from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        config = CuratorConfig(enabled=True, consolidation_enabled=True)
        collector = SkillStatsCollector()

        mock_llm = MagicMock()
        mock_write = MagicMock()

        curator = SkillCurator(collector, config, llm=mock_llm, write_backend=mock_write)
        assert curator.consolidation_available

        skills = [make_skill(f"skill_{i}") for i in range(3)]
        result, _consolidation = await curator.run_async(skills)
        assert result.skills_scanned == 3
