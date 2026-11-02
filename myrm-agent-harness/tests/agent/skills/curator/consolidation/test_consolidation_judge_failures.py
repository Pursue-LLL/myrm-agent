"""A cluster the judge could not judge is counted, so an empty plan is never mistaken for 'well-organized'."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.skills.curator.consolidation.judge import ConsolidationJudge, _ClusterJudgment
from myrm_agent_harness.agent.skills.curator.consolidation.types import ConsolidationPlan, SkillCluster
from myrm_agent_harness.agent.skills.curator.engine import SkillCurator
from myrm_agent_harness.backends.skills.curator_config import CuratorConfig
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
from tests.support.skill_factory import make_skill

_TASK = ("task_a_skill", "task_b_skill", "task_c_skill")
_DEPLOY = ("deploy_a_skill", "deploy_b_skill", "deploy_c_skill")
_KEEP = _ClusterJudgment(action="keep", target_skill_name="any", reasoning="distinct purposes")


def _cluster(prefix: str, names: tuple[str, ...]) -> SkillCluster:
    return SkillCluster(cluster_id=f"prefix-{prefix}", skill_names=names, shared_domain=prefix)


def _merge_into(target: str, *, keep_standalone: list[str] | None = None) -> _ClusterJudgment:
    return _ClusterJudgment(
        action="merge", target_skill_name=target, keep_standalone=keep_standalone or [], reasoning="same family"
    )


def _llm_answering(*answers: _ClusterJudgment | Exception | None) -> MagicMock:
    """A model that gives the clusters, in order, the next answer: a judgment, nothing, or an exception to raise."""
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=AsyncMock(side_effect=list(answers))))
    return llm


class TestAClusterTheJudgeCouldNotJudge:
    """Only a cluster that was judged may be reported as needing nothing."""

    @pytest.mark.asyncio
    async def test_a_kept_cluster_was_judged_so_the_library_is_well_organized(self) -> None:
        plan = await ConsolidationJudge(_llm_answering(_KEEP)).judge_clusters(
            [_cluster("task", _TASK)], [make_skill(name) for name in _TASK]
        )

        assert (plan.failed_clusters, plan.is_empty) == (0, True)
        assert "well-organized" in plan.preview_summary

    @pytest.mark.asyncio
    async def test_an_action_with_nothing_left_to_consolidate_was_still_judged(self) -> None:
        answer = _merge_into("task_a_skill", keep_standalone=["task_b_skill", "task_c_skill"])

        plan = await ConsolidationJudge(_llm_answering(answer)).judge_clusters(
            [_cluster("task", _TASK)], [make_skill(name) for name in _TASK]
        )

        assert (plan.failed_clusters, plan.is_empty) == (0, True)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "answer",
        [
            RuntimeError("429 rate limited"),
            None,
            _merge_into("ghost_skill"),
            _ClusterJudgment(
                action="create_umbrella",
                target_skill_name="task_a_skill",
                reasoning="umbrella named after a skill that already exists",
                umbrella_description="Tasks",
            ),
        ],
        ids=["model-call-raises", "no-usable-judgment", "unknown-merge-target", "umbrella-name-taken"],
    )
    async def test_an_answer_that_cannot_be_acted_on_is_counted_and_never_called_well_organized(
        self, answer: _ClusterJudgment | Exception | None
    ) -> None:
        plan = await ConsolidationJudge(_llm_answering(answer)).judge_clusters(
            [_cluster("task", _TASK)], [make_skill(name) for name in _TASK]
        )

        assert plan.failed_clusters == 1
        assert plan.is_empty
        assert "well-organized" not in plan.preview_summary
        assert "could not be evaluated: 1" in plan.preview_summary

    @pytest.mark.asyncio
    async def test_the_judged_actions_stay_in_the_plan_beside_a_cluster_that_failed(self) -> None:
        judge = ConsolidationJudge(_llm_answering(RuntimeError("timeout"), _merge_into("deploy_a_skill")))

        plan = await judge.judge_clusters(
            [_cluster("task", _TASK), _cluster("deploy", _DEPLOY)], [make_skill(name) for name in (*_TASK, *_DEPLOY)]
        )

        assert [action.target_skill for action in plan.actions] == ["deploy_a_skill"]
        assert plan.failed_clusters == 1
        assert "deploy_a_skill" in plan.preview_summary
        assert "could not be evaluated: 1" in plan.preview_summary


class TestAFailingJudgeThroughTheCurator:
    """The curator swallows a failed consolidation pass, so the count has to travel inside the plan it returns."""

    @pytest.mark.asyncio
    async def test_every_failed_cluster_reaches_the_caller_of_a_dry_run(self) -> None:
        names = [f"{family}-{i}" for family in ("report", "invoice", "meeting") for i in range(4)]
        outage = _llm_answering(*[RuntimeError("429 rate limited")] * 3)
        curator = SkillCurator(
            SkillStatsCollector(),
            CuratorConfig(enabled=True, consolidation_enabled=True),
            llm=outage,
            write_backend=MagicMock(),
        )

        _, plan = await curator.run_async([make_skill(name) for name in names], force=True, consolidation_dry_run=True)

        assert isinstance(plan, ConsolidationPlan)
        assert (plan.failed_clusters, plan.is_empty) == (3, True)
        assert "well-organized" not in plan.preview_summary
