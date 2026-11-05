"""A plan is applied exactly as it was proposed, and only to what is still fair game when it is applied.

The host previews a plan, the user reads it, and some time later the host applies it. In between, a model asked the
same question may answer differently, and a skill the plan names may have been pinned, archived, protected or
removed. Applying must neither ask the model again nor reach a skill the sweep that proposed the plan could no
longer have proposed.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.skills.curator.consolidation.executor import ConsolidationExecutor
from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment
from myrm_agent_harness.agent.skills.curator.consolidation.orchestrator import SkillConsolidator
from myrm_agent_harness.agent.skills.curator.consolidation.types import (
    ConsolidationAction,
    ConsolidationActionType,
    ConsolidationPlan,
)
from myrm_agent_harness.agent.skills.curator.engine import SkillCurator
from myrm_agent_harness.backends.skills.curator_config import CuratorConfig
from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus, SkillMetadata
from tests.support.skill_factory import make_skill

_SOURCES = ("git_push_skill", "git_merge_skill")


def _git_skills() -> list[SkillMetadata]:
    names = ("git_commit_skill", *_SOURCES, "deploy_skill")
    return [make_skill(name, f"{name} helper") for name in names]


def _write_backend() -> MagicMock:
    write = MagicMock()
    write.write_resource = AsyncMock(return_value=MagicMock(success=True))
    write.save_skill = AsyncMock(return_value=MagicMock(success=True, saved_path="/tmp/skills/git_ops", error=""))
    return write


def _merge(sources: tuple[str, ...] = _SOURCES) -> ConsolidationAction:
    return ConsolidationAction(
        action_type=ConsolidationActionType.MERGE,
        target_skill="git_commit_skill",
        source_skills=sources,
        reasoning="same workflow",
    )


def _archived(stats: MagicMock) -> set[str]:
    return {call.args[0].name for call in stats.archive_merged.call_args_list}


def _written(write: MagicMock) -> list[str]:
    return [call.kwargs["resource_path"] for call in write.write_resource.await_args_list]


def _pin(skill: SkillMetadata) -> None:
    skill.usage_stats.pinned = True


def _archive(skill: SkillMetadata) -> None:
    skill.usage_stats.lifecycle_status = SkillLifecycleStatus.ARCHIVED


def _lock(skill: SkillMetadata) -> None:
    skill.evolution_locked = True


class TestApplyDoesNotAskTheModelAgain:
    async def test_the_plan_that_was_proposed_is_the_plan_that_runs(self) -> None:
        """A model answers the same question differently from one call to the next; apply never asks it again."""
        verdicts = [
            _ClusterJudgment(action="merge", target_skill_name="git_commit_skill", reasoning="same workflow"),
            _ClusterJudgment(action="merge", target_skill_name="git_push_skill", reasoning="another opinion"),
        ]
        ainvoke = AsyncMock(side_effect=verdicts)
        llm = MagicMock()
        llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=ainvoke))
        stats = MagicMock()
        consolidator = SkillConsolidator(
            llm, _write_backend(), stats, min_skills_for_consolidation=3, min_cluster_size=3
        )
        skills = _git_skills()

        plan = await consolidator.propose(skills)
        report = await consolidator.apply(plan, skills)

        assert ainvoke.await_count == 1
        assert [result.action.target_skill for result in report.results] == ["git_commit_skill"]
        assert _archived(stats) == set(_SOURCES)


class TestASourceThatChangedSinceThePlan:
    """A source that is gone or no longer eligible counts as absent: it is neither absorbed nor archived."""

    @pytest.mark.parametrize("change", [_pin, _archive, _lock], ids=["pinned", "archived", "evolution-locked"])
    async def test_it_is_left_alone_while_the_rest_of_the_action_runs(
        self, change: Callable[[SkillMetadata], None]
    ) -> None:
        skills = _git_skills()
        change(next(skill for skill in skills if skill.name == "git_push_skill"))
        stats, write = MagicMock(), _write_backend()

        report = await ConsolidationExecutor(write, stats, skills).execute([_merge()])

        assert (report.success_count, report.failure_count) == (1, 0)
        assert _archived(stats) == {"git_merge_skill"}
        assert _written(write) == ["references/git_merge_skill.md"]

    async def test_a_removed_source_is_skipped_the_same_way(self) -> None:
        skills = [skill for skill in _git_skills() if skill.name != "git_push_skill"]
        stats, write = MagicMock(), _write_backend()

        report = await ConsolidationExecutor(write, stats, skills).execute([_merge()])

        assert report.success_count == 1
        assert _archived(stats) == {"git_merge_skill"}

    async def test_an_action_whose_sources_are_all_ineligible_changes_nothing(self) -> None:
        skills = _git_skills()
        for skill in skills:
            if skill.name in _SOURCES:
                _pin(skill)
        stats, write = MagicMock(), _write_backend()

        report = await ConsolidationExecutor(write, stats, skills).execute([_merge()])

        assert (report.success_count, report.failure_count) == (0, 1)
        assert "No source skills found" in report.results[0].error
        assert _archived(stats) == set()
        write.write_resource.assert_not_awaited()

    async def test_an_umbrella_is_built_from_the_sources_that_remain(self) -> None:
        skills = _git_skills()
        _pin(next(skill for skill in skills if skill.name == "git_push_skill"))
        stats, write = MagicMock(), _write_backend()
        umbrella = ConsolidationAction(
            action_type=ConsolidationActionType.CREATE_UMBRELLA,
            target_skill="git_ops",
            source_skills=("git_commit_skill", *_SOURCES),
            reasoning="same workflow",
            umbrella_description="Git operations",
        )

        report = await ConsolidationExecutor(write, stats, skills).execute([umbrella])

        content = write.save_skill.await_args.kwargs["content"]
        assert report.success_count == 1
        assert "git_push_skill" not in content
        assert "git_merge_skill" in content
        assert _archived(stats) == {"git_commit_skill", "git_merge_skill"}


class TestCuratorApplyingAPlan:
    @staticmethod
    def _curator(stats: MagicMock, write: MagicMock, llm: MagicMock, **config: bool) -> SkillCurator:
        settings = CuratorConfig(enabled=True, consolidation_enabled=True, **config)
        return SkillCurator(stats, settings, llm=llm, write_backend=write)

    @staticmethod
    def _plan() -> ConsolidationPlan:
        return ConsolidationPlan(actions=[_merge()], total_skills_affected=2, estimated_reduction=2)

    @pytest.mark.parametrize(
        "exempt",
        [
            pytest.param({"protected_names": frozenset({"git_push_skill"})}, id="bound-since-the-plan"),
            pytest.param({"installed_names": frozenset({"git_push_skill"})}, id="installed-while-protection-is-on"),
        ],
    )
    async def test_an_exempt_skill_is_left_alone_and_the_model_is_not_asked(
        self, exempt: dict[str, frozenset[str]]
    ) -> None:
        stats, write, llm = MagicMock(), _write_backend(), MagicMock()

        report = await self._curator(stats, write, llm).apply_consolidation_plan(_git_skills(), self._plan(), **exempt)

        assert report is not None
        assert _archived(stats) == {"git_merge_skill"}
        llm.with_structured_output.assert_not_called()

    async def test_an_installed_skill_is_applied_once_the_protection_is_off(self) -> None:
        stats, write, llm = MagicMock(), _write_backend(), MagicMock()
        curator = self._curator(stats, write, llm, protect_installed_skills=False)

        await curator.apply_consolidation_plan(
            _git_skills(), self._plan(), installed_names=frozenset({"git_push_skill"})
        )

        assert _archived(stats) == set(_SOURCES)

    async def test_nothing_is_applied_while_consolidation_is_switched_off(self) -> None:
        stats, write = MagicMock(), _write_backend()
        curator = SkillCurator(
            stats, CuratorConfig(enabled=True, consolidation_enabled=False), llm=MagicMock(), write_backend=write
        )

        report = await curator.apply_consolidation_plan(_git_skills(), self._plan())

        assert report is None
        write.write_resource.assert_not_awaited()
        assert _archived(stats) == set()
