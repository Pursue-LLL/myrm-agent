"""Consolidation execute applies the plan the preview produced, through the real curator and the real write backend.

A model answers the same question differently from one call to the next, so an execute that judged again would
apply a plan the user never saw. Execute takes the previewed plan and asks the model nothing.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.skills.curator.consolidation.judge import _ClusterJudgment
from myrm_agent_harness.agent.skills.curator.consolidation.types import ConsolidationPlan
from myrm_agent_harness.backends.skills.curator_config import CuratorConfig
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
from myrm_agent_harness.backends.skills.types import SkillMetadata

from app.core.skills.creation.service import SkillCreationService
from app.core.skills.curator.consolidation import run_consolidation_execute, run_consolidation_preview
from app.core.skills.curator.local_skills import LocalSkillScan

_GIT_SKILLS = ("git_commit", "git_push", "git_merge", "deploy_ops")


async def _save(service: SkillCreationService, name: str) -> SkillMetadata:
    saved = await service.save_skill(name, f"---\nname: {name}\ndescription: {name} skill\n---\n# {name}\n")
    assert saved.success, saved.error
    return SkillMetadata(name=name, description=f"{name} skill", storage_path=saved.saved_path)


def _is_archived(skill: SkillMetadata) -> bool:
    ledger = Path(skill.storage_path or "") / ".stats.json"
    return ledger.exists() and json.loads(ledger.read_text(encoding="utf-8"))["lifecycle_status"] == "archived"


def _scan(skills: Sequence[SkillMetadata]) -> AsyncMock:
    return AsyncMock(return_value=LocalSkillScan(skills=list(skills), installed_names=frozenset()))


def _model_changing_its_mind() -> tuple[MagicMock, AsyncMock]:
    """A model whose first verdict merges into git_commit and whose every later verdict targets git_push."""
    verdicts = [
        _ClusterJudgment(action="merge", target_skill_name="git_commit", reasoning="same workflow"),
        *[_ClusterJudgment(action="merge", target_skill_name="git_push", reasoning="another opinion")] * 5,
    ]
    ainvoke = AsyncMock(side_effect=verdicts)
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=MagicMock(ainvoke=ainvoke))
    return llm, ainvoke


@contextmanager
def _consolidation_host(llm: MagicMock, service: SkillCreationService, scan: AsyncMock) -> Iterator[None]:
    config = CuratorConfig(enabled=True, consolidation_enabled=True, consolidation_min_skills=3, consolidation_min_cluster_size=3)
    with (
        patch("app.core.skills.curator.consolidation._get_consolidation_deps", AsyncMock(return_value=(llm, service))),
        patch("app.core.skills.curator.consolidation.scan_local_skills", scan),
        patch("app.core.skills.curator.consolidation.bound_skill_names", AsyncMock(return_value=frozenset())),
        patch("app.core.skills.curator.consolidation.get_curator_config", return_value=config),
        patch("app.core.skills.curator.consolidation.get_stats_collector", return_value=SkillStatsCollector()),
    ):
        yield


@pytest.mark.asyncio
async def test_execute_applies_the_previewed_plan_and_asks_the_model_nothing(tmp_path: Path) -> None:
    service = SkillCreationService(base_path=tmp_path)
    commit, push, merge, deploy = [await _save(service, name) for name in _GIT_SKILLS]
    llm, ainvoke = _model_changing_its_mind()

    with _consolidation_host(llm, service, _scan([commit, push, merge, deploy])):
        plan = await run_consolidation_preview()
        result = await run_consolidation_execute(plan)

    assert [action.target_skill for action in plan.actions] == ["git_commit"]
    assert ainvoke.await_count == 1
    assert (result["success_count"], result["failure_count"]) == (1, 0)
    assert (_is_archived(commit), _is_archived(push), _is_archived(merge), _is_archived(deploy)) == (
        False,
        True,
        True,
        False,
    )


@pytest.mark.asyncio
async def test_execute_leaves_alone_a_source_that_was_pinned_after_the_preview(tmp_path: Path) -> None:
    service = SkillCreationService(base_path=tmp_path)
    commit, push, merge, deploy = [await _save(service, name) for name in _GIT_SKILLS]
    llm, _ = _model_changing_its_mind()

    with _consolidation_host(llm, service, _scan([commit, push, merge, deploy])):
        plan = await run_consolidation_preview()

    push.usage_stats.pinned = True
    with _consolidation_host(llm, service, _scan([commit, push, merge, deploy])):
        result = await run_consolidation_execute(plan)

    assert (result["success_count"], result["total_archived"]) == (1, 1)
    assert (_is_archived(push), _is_archived(merge)) == (False, True)


@pytest.mark.asyncio
async def test_execute_with_no_skills_left_reports_that_nothing_was_available(tmp_path: Path) -> None:
    service = SkillCreationService(base_path=tmp_path)
    llm, ainvoke = _model_changing_its_mind()

    with _consolidation_host(llm, service, _scan([])):
        result = await run_consolidation_execute(ConsolidationPlan())

    assert result["summary"] == "No skills available for consolidation."
    ainvoke.assert_not_awaited()
