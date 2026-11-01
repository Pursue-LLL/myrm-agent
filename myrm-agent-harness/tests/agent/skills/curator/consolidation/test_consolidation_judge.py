"""The consolidation judge turns the LLM's judgment of a cluster into a plan action."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.skills.curator.consolidation.judge import ConsolidationJudge
from myrm_agent_harness.agent.skills.curator.consolidation.types import (
    ConsolidationActionType,
    SkillCluster,
)
from tests.support.skill_factory import make_skill


class TestConsolidationJudge:
    """Tests for ConsolidationJudge LLM interaction."""

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        llm = MagicMock()
        return llm

    @pytest.mark.asyncio
    async def test_judge_keep_decision(self, mock_llm: MagicMock) -> None:
        from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment

        mock_structured = AsyncMock(
            return_value=_ClusterJudgment(
                action="keep",
                target_skill_name="any",
                reasoning="Skills serve distinct purposes",
            )
        )
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))

        judge = ConsolidationJudge(mock_llm)
        cluster = SkillCluster(
            cluster_id="test-cluster",
            skill_names=("a_skill", "b_skill", "c_skill"),
            shared_domain="testing",
        )

        plan = await judge.judge_clusters([cluster], [])
        assert plan.is_empty

    @pytest.mark.asyncio
    async def test_judge_merge_decision(self, mock_llm: MagicMock) -> None:
        from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment

        mock_structured = AsyncMock(
            return_value=_ClusterJudgment(
                action="merge",
                target_skill_name="git_operations_skill",
                reasoning="git_operations_skill is already broad enough",
            )
        )
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))

        judge = ConsolidationJudge(mock_llm)
        skills = [
            make_skill("git_operations_skill", "Git operations"),
            make_skill("git_commit_skill", "Commit changes"),
            make_skill("git_push_skill", "Push changes"),
        ]
        cluster = SkillCluster(
            cluster_id="prefix-git",
            skill_names=("git_operations_skill", "git_commit_skill", "git_push_skill"),
            shared_domain="git",
        )

        plan = await judge.judge_clusters([cluster], skills)
        assert not plan.is_empty
        assert plan.actions[0].action_type == ConsolidationActionType.MERGE
        assert plan.actions[0].target_skill == "git_operations_skill"
        assert "git_commit_skill" in plan.actions[0].source_skills

    @pytest.mark.asyncio
    async def test_judge_leaves_standalone_members_out_of_the_action(self, mock_llm: MagicMock) -> None:
        from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment

        mock_structured = AsyncMock(
            return_value=_ClusterJudgment(
                action="merge",
                target_skill_name="task_flywheel_skill",
                keep_standalone=["task_planning_skill"],
                reasoning="task_planning_skill plans work; the other two distil transcripts",
            )
        )
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))
        names = ("task_planning_skill", "task_flywheel_skill", "task_transcript_skill")
        skills = [make_skill(name) for name in names]
        cluster = SkillCluster(cluster_id="prefix-task", skill_names=names, shared_domain="task")

        plan = await ConsolidationJudge(mock_llm).judge_clusters([cluster], skills)

        assert [action.source_skills for action in plan.actions] == [("task_transcript_skill",)]

    @pytest.mark.asyncio
    async def test_judge_drops_an_action_that_leaves_nothing_to_consolidate(self, mock_llm: MagicMock) -> None:
        from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment

        mock_structured = AsyncMock(
            return_value=_ClusterJudgment(
                action="merge",
                target_skill_name="task_flywheel_skill",
                keep_standalone=["task_planning_skill", "task_transcript_skill"],
                reasoning="only the target belongs to this family",
            )
        )
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))
        names = ("task_planning_skill", "task_flywheel_skill", "task_transcript_skill")
        skills = [make_skill(name) for name in names]
        cluster = SkillCluster(cluster_id="prefix-task", skill_names=names, shared_domain="task")

        plan = await ConsolidationJudge(mock_llm).judge_clusters([cluster], skills)

        assert plan.is_empty

    @pytest.mark.asyncio
    async def test_judge_prompt_spells_out_the_judgment_shape(self, mock_llm: MagicMock) -> None:
        """JSON mode only guarantees valid JSON; the model fills the shape the prompt describes."""
        from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment

        mock_structured = AsyncMock(
            return_value=_ClusterJudgment(action="keep", target_skill_name="any", reasoning="distinct purposes")
        )
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))
        cluster = SkillCluster(
            cluster_id="prefix-git",
            skill_names=("git_commit_skill", "git_push_skill", "git_pull_skill"),
            shared_domain="git",
        )

        await ConsolidationJudge(mock_llm).judge_clusters([cluster], [])

        prompt = mock_structured.await_args.args[0]
        assert [field for field in _ClusterJudgment.model_fields if field not in prompt] == []


class TestConsolidationJudgeEdgeCases:
    """Edge cases for the consolidation judge."""

    @pytest.mark.asyncio
    async def test_judge_llm_returns_none(self) -> None:
        """LLM returns None — should result in empty plan."""
        mock_structured = AsyncMock(return_value=None)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))

        judge = ConsolidationJudge(mock_llm)
        cluster = SkillCluster(
            cluster_id="test",
            skill_names=("a", "b", "c"),
            shared_domain="test",
        )

        plan = await judge.judge_clusters([cluster], [])
        assert plan.is_empty

    @pytest.mark.asyncio
    async def test_judge_llm_raises_exception(self) -> None:
        """LLM raises exception — should be caught, empty plan."""
        mock_structured = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))

        judge = ConsolidationJudge(mock_llm)
        cluster = SkillCluster(
            cluster_id="test",
            skill_names=("x", "y", "z"),
            shared_domain="test",
        )

        plan = await judge.judge_clusters([cluster], [])
        assert plan.is_empty

    @pytest.mark.asyncio
    async def test_judge_create_umbrella_decision(self) -> None:
        """LLM decides create_umbrella — should produce correct action."""
        from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment

        mock_structured = AsyncMock(
            return_value=_ClusterJudgment(
                action="create_umbrella",
                target_skill_name="deploy_operations_skill",
                reasoning="No single skill covers all deployment",
                umbrella_description="Unified deployment operations",
                umbrella_content_outline="Docker, K8s, and EC2 deployments",
            )
        )
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))

        judge = ConsolidationJudge(mock_llm)
        skills = [
            make_skill("deploy_docker_skill", "Deploy with Docker"),
            make_skill("deploy_k8s_skill", "Deploy to Kubernetes"),
            make_skill("deploy_ec2_skill", "Deploy to EC2"),
        ]
        cluster = SkillCluster(
            cluster_id="prefix-deploy",
            skill_names=("deploy_docker_skill", "deploy_k8s_skill", "deploy_ec2_skill"),
            shared_domain="deploy",
        )

        plan = await judge.judge_clusters([cluster], skills)
        assert not plan.is_empty
        assert plan.actions[0].action_type == ConsolidationActionType.CREATE_UMBRELLA
        assert plan.actions[0].umbrella_description == "Unified deployment operations"

    @pytest.mark.asyncio
    async def test_judge_demote_decision(self) -> None:
        """LLM decides demote — should produce correct action with target dir."""
        from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment

        mock_structured = AsyncMock(
            return_value=_ClusterJudgment(
                action="demote",
                target_skill_name="main_skill",
                reasoning="Helper skills are too narrow",
                demote_target_dir="scripts",
            )
        )
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=mock_structured))

        judge = ConsolidationJudge(mock_llm)
        skills = [
            make_skill("main_skill", "Main skill"),
            make_skill("helper_a", "Helper A"),
            make_skill("helper_b", "Helper B"),
        ]
        cluster = SkillCluster(
            cluster_id="test-demote",
            skill_names=("main_skill", "helper_a", "helper_b"),
            shared_domain="helpers",
        )

        plan = await judge.judge_clusters([cluster], skills)
        assert not plan.is_empty
        assert plan.actions[0].action_type == ConsolidationActionType.DEMOTE
        assert plan.actions[0].demote_target_dir == "scripts"
