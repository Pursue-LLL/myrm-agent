"""The consolidation value types: clusters, plans and reports."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.skills.curator.consolidation.types import (
    ConsolidationAction,
    ConsolidationActionType,
    ConsolidationPlan,
    ConsolidationReport,
    ConsolidationResult,
    SkillCluster,
)


class TestSkillCluster:
    """Tests for SkillCluster data type."""

    def test_cluster_creation(self) -> None:
        cluster = SkillCluster(
            cluster_id="test-1",
            skill_names=("git_commit_skill", "git_push_skill", "git_merge_skill"),
            shared_domain="git",
        )
        assert cluster.cluster_id == "test-1"
        assert len(cluster.skill_names) == 3
        assert cluster.shared_domain == "git"

    def test_cluster_immutable(self) -> None:
        cluster = SkillCluster(
            cluster_id="test-1",
            skill_names=("a", "b", "c"),
            shared_domain="test",
        )
        with pytest.raises(AttributeError):
            cluster.cluster_id = "changed"  # type: ignore[misc]


class TestConsolidationAction:
    """Tests for the reduction a single action delivers."""

    @pytest.mark.parametrize(
        ("action_type", "sources", "expected"),
        [
            pytest.param(ConsolidationActionType.MERGE, ("a", "b", "c"), 3, id="merge-archives-every-source"),
            pytest.param(ConsolidationActionType.DEMOTE, ("a", "b"), 2, id="demote-archives-every-source"),
            pytest.param(ConsolidationActionType.CREATE_UMBRELLA, ("a", "b", "c", "d"), 3, id="umbrella-adds-one"),
            pytest.param(ConsolidationActionType.KEEP, ("a", "b"), 0, id="keep-removes-nothing"),
        ],
    )
    def test_net_reduction(self, action_type: ConsolidationActionType, sources: tuple[str, ...], expected: int) -> None:
        action = ConsolidationAction(
            action_type=action_type,
            target_skill="target",
            source_skills=sources,
            reasoning="test",
        )
        assert action.net_reduction == expected


class TestConsolidationPlan:
    """Tests for ConsolidationPlan data type."""

    def test_empty_plan(self) -> None:
        plan = ConsolidationPlan()
        assert plan.is_empty
        assert plan.merge_count == 0
        assert plan.create_count == 0
        assert plan.demote_count == 0

    def test_plan_with_actions(self) -> None:
        actions = [
            ConsolidationAction(
                action_type=ConsolidationActionType.MERGE,
                target_skill="git_operations_skill",
                source_skills=("git_commit_skill", "git_push_skill"),
                reasoning="Related git operations",
            ),
            ConsolidationAction(
                action_type=ConsolidationActionType.CREATE_UMBRELLA,
                target_skill="deploy_skill",
                source_skills=("deploy_docker_skill", "deploy_k8s_skill", "deploy_ec2_skill"),
                reasoning="All deployment related",
                umbrella_description="Unified deployment operations",
            ),
        ]
        plan = ConsolidationPlan(
            actions=actions,
            total_skills_affected=5,
            estimated_reduction=3,
        )
        assert not plan.is_empty
        assert plan.merge_count == 1
        assert plan.create_count == 1
        assert plan.demote_count == 0
        assert plan.estimated_reduction == 3


class TestConsolidationReport:
    """Tests for ConsolidationReport."""

    def test_empty_report(self) -> None:
        report = ConsolidationReport()
        assert report.net_reduction == 0
        assert report.success_count == 0
        assert report.failure_count == 0
        assert "No consolidation" in report.to_summary()

    def test_report_with_results(self) -> None:
        action = ConsolidationAction(
            action_type=ConsolidationActionType.MERGE,
            target_skill="umbrella",
            source_skills=("a", "b"),
            reasoning="test",
        )
        report = ConsolidationReport(
            results=[
                ConsolidationResult(action=action, success=True, archived_skills=("a", "b")),
            ],
            skills_before=10,
            skills_after=8,
            total_archived=2,
        )
        assert report.net_reduction == 2
        assert report.success_count == 1
        assert report.failure_count == 0


class TestConsolidationReportSummary:
    """Tests for ConsolidationReport.to_summary output."""

    def test_summary_with_failures(self) -> None:
        action_ok = ConsolidationAction(
            action_type=ConsolidationActionType.MERGE,
            target_skill="t",
            source_skills=("a",),
            reasoning="test",
        )
        action_fail = ConsolidationAction(
            action_type=ConsolidationActionType.CREATE_UMBRELLA,
            target_skill="u",
            source_skills=("b",),
            reasoning="test",
        )
        report = ConsolidationReport(
            results=[
                ConsolidationResult(action=action_ok, success=True, archived_skills=("a",)),
                ConsolidationResult(action=action_fail, success=False, error="disk full"),
            ],
            skills_before=10,
            skills_after=9,
            total_archived=1,
        )
        summary = report.to_summary()
        assert "failed" in summary.lower()
        assert "10" in summary
        assert "9" in summary
