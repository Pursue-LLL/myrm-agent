"""Tests for curator consolidation integration.

Tests the consolidation preview and execute services and which skills they hand to the curator.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.skills.curator.consolidation.executor import ConsolidationExecutor
from myrm_agent_harness.agent.skills.curator.consolidation.types import (
    ConsolidationAction,
    ConsolidationActionType,
    ConsolidationPlan,
    ConsolidationReport,
    ConsolidationResult,
)
from myrm_agent_harness.backends.skills.curator_config import CuratorConfig
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
from myrm_agent_harness.backends.skills.types import SkillMetadata

from app.core.skills.creation.service import SkillCreationService
from app.core.skills.curator.local_skills import LocalSkillScan


def _scan(skills: Sequence[SkillMetadata], installed: frozenset[str] = frozenset()) -> AsyncMock:
    """A stand-in for ``scan_local_skills`` that returns the given skills."""
    return AsyncMock(return_value=LocalSkillScan(skills=list(skills), installed_names=installed))


class TestConsolidationPreview:
    """Tests for run_consolidation_preview service function."""

    @pytest.mark.asyncio
    async def test_preview_returns_empty_plan_when_no_skills(self) -> None:
        """Empty skill list should return empty plan."""
        mock_llm = MagicMock()
        mock_write = MagicMock()

        with (
            patch(
                "app.core.skills.curator.consolidation._get_consolidation_deps",
                AsyncMock(return_value=(mock_llm, mock_write)),
            ),
            patch("app.core.skills.curator.consolidation.scan_local_skills", _scan([])),
        ):
            from app.core.skills.curator.consolidation import run_consolidation_preview

            plan = await run_consolidation_preview()

        assert plan.is_empty

    @pytest.mark.asyncio
    async def test_preview_returns_plan_from_curator(self) -> None:
        """Should return the plan from curator's run_async."""
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
                AsyncMock(return_value=(mock_llm, mock_write)),
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


@contextmanager
def _curator_returning(plan: ConsolidationPlan) -> Iterator[None]:
    """``run_consolidation_preview`` over five skills, with a curator that answers every run with ``plan``."""
    curator = MagicMock()
    curator.run_async = AsyncMock(return_value=(MagicMock(skills_scanned=5), plan))
    with (
        patch(
            "app.core.skills.curator.consolidation._get_consolidation_deps",
            AsyncMock(return_value=(MagicMock(), MagicMock())),
        ),
        patch("app.core.skills.curator.consolidation.scan_local_skills", _scan([MagicMock() for _ in range(5)])),
        patch("app.core.skills.curator.consolidation.bound_skill_names", AsyncMock(return_value=frozenset())),
        patch("myrm_agent_harness.agent.skills.curator.SkillCurator", return_value=curator),
    ):
        yield


class TestConsolidationPreviewNeverHidesUnjudgedClusters:
    """An empty plan reads as 'well-organized', so a plan that is empty because the judge failed is an error."""

    @pytest.mark.asyncio
    async def test_an_empty_plan_with_unjudged_clusters_is_a_bad_gateway(self) -> None:
        from fastapi import HTTPException

        from app.core.skills.curator.consolidation import run_consolidation_preview

        with _curator_returning(ConsolidationPlan(failed_clusters=2)), pytest.raises(HTTPException) as caught:
            await run_consolidation_preview()

        assert caught.value.status_code == 502
        assert "2 skill group" in caught.value.detail

    @pytest.mark.asyncio
    async def test_an_empty_plan_without_failures_is_still_returned(self) -> None:
        from app.core.skills.curator.consolidation import run_consolidation_preview

        with _curator_returning(ConsolidationPlan()):
            plan = await run_consolidation_preview()

        assert plan.is_empty

    @pytest.mark.asyncio
    async def test_judged_actions_are_returned_beside_a_cluster_that_failed(self) -> None:
        from app.core.skills.curator.consolidation import run_consolidation_preview

        merge = ConsolidationAction(
            action_type=ConsolidationActionType.MERGE, target_skill="target", source_skills=("a", "b"), reasoning="test"
        )
        partial = ConsolidationPlan(actions=[merge], total_skills_affected=2, estimated_reduction=1, failed_clusters=1)

        with _curator_returning(partial):
            plan = await run_consolidation_preview()

        assert plan is partial

    @pytest.mark.asyncio
    async def test_a_model_outage_in_the_real_curator_is_a_bad_gateway_not_an_empty_plan(self) -> None:
        """The curator swallows a failed consolidation pass, so only the plan it returns can carry the failure."""
        from fastapi import HTTPException

        from app.core.skills.curator.consolidation import run_consolidation_preview

        outage = MagicMock()
        outage.with_structured_output = MagicMock(
            return_value=MagicMock(ainvoke=AsyncMock(side_effect=RuntimeError("429 rate limited")))
        )
        skills = [
            SkillMetadata(name=f"{family}-{i}", description=f"{family} {i}", storage_path=f"/tmp/skills/{family}-{i}")
            for family in ("report", "invoice", "meeting")
            for i in range(4)
        ]

        with (
            patch(
                "app.core.skills.curator.consolidation._get_consolidation_deps",
                AsyncMock(return_value=(outage, MagicMock())),
            ),
            patch("app.core.skills.curator.consolidation.scan_local_skills", _scan(skills)),
            patch("app.core.skills.curator.consolidation.bound_skill_names", AsyncMock(return_value=frozenset())),
            patch(
                "app.core.skills.curator.consolidation.get_curator_config",
                return_value=CuratorConfig(enabled=True, consolidation_enabled=True),
            ),
            patch("app.core.skills.curator.consolidation.get_stats_collector", return_value=SkillStatsCollector()),
            pytest.raises(HTTPException) as caught,
        ):
            await run_consolidation_preview()

        assert caught.value.status_code == 502
        assert "3 skill group" in caught.value.detail


class TestConsolidationDependencies:
    """Consolidation needs the LLM and the skill write backend; it asks for no embedding configuration."""

    @pytest.mark.asyncio
    async def test_resolves_without_an_embedding_configuration(self) -> None:
        from myrm_agent_harness.toolkits.llms import llm_manager

        from app.core.skills.creation.service import skill_creation_service
        from app.core.skills.curator.consolidation import _get_consolidation_deps

        llm = MagicMock()
        no_embedding = AsyncMock(side_effect=RuntimeError("embedding not configured"))
        with (
            patch("app.services.agent.platform_config.load_platform_model_config", AsyncMock(return_value=MagicMock())),
            patch("app.services.agent.platform_config.require_platform_embedding_config", no_embedding),
            patch.object(llm_manager, "get_llm_from_config", AsyncMock(return_value=llm)),
        ):
            resolved = await _get_consolidation_deps()

        assert resolved == (llm, skill_creation_service)
        no_embedding.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unconfigured_llm_is_service_unavailable(self) -> None:
        from fastapi import HTTPException

        from app.core.skills.curator.consolidation import _get_consolidation_deps

        with (
            patch(
                "app.services.agent.platform_config.load_platform_model_config",
                AsyncMock(side_effect=RuntimeError("no model")),
            ),
            pytest.raises(HTTPException) as caught,
        ):
            await _get_consolidation_deps()

        assert (caught.value.status_code, caught.value.detail) == (503, "LLM not configured")


class TestConsolidationSparesBoundAndInstalledSkills:
    """Preview and execute hand the bound skills (agents / cron jobs) and the installed ones to the curator."""

    @staticmethod
    @contextmanager
    def _curator_seeing(curator: MagicMock) -> Iterator[None]:
        with (
            patch(
                "app.core.skills.curator.consolidation._get_consolidation_deps",
                AsyncMock(return_value=(MagicMock(), MagicMock())),
            ),
            patch("app.core.skills.curator.consolidation.scan_local_skills", _scan([MagicMock()], frozenset({"from-store"}))),
            patch(
                "app.core.skills.curator.consolidation.bound_skill_names",
                AsyncMock(return_value=frozenset({"bound"})),
            ),
            patch("myrm_agent_harness.agent.skills.curator.SkillCurator", return_value=curator),
        ):
            yield

    @pytest.mark.asyncio
    async def test_preview_hands_them_to_the_proposal(self) -> None:
        curator = MagicMock()
        curator.run_async = AsyncMock(return_value=(MagicMock(), ConsolidationPlan()))

        with self._curator_seeing(curator):
            from app.core.skills.curator.consolidation import run_consolidation_preview

            await run_consolidation_preview()

        kwargs = curator.run_async.call_args.kwargs
        assert kwargs["protected_names"] == frozenset({"bound"})
        assert kwargs["installed_names"] == frozenset({"from-store"})

    @pytest.mark.asyncio
    async def test_execute_hands_them_to_the_application_of_the_plan(self) -> None:
        curator = MagicMock()
        curator.apply_consolidation_plan = AsyncMock(return_value=ConsolidationReport())
        plan = ConsolidationPlan()

        with self._curator_seeing(curator):
            from app.core.skills.curator.consolidation import run_consolidation_execute

            await run_consolidation_execute(plan)

        assert curator.apply_consolidation_plan.call_args.args[1] is plan
        kwargs = curator.apply_consolidation_plan.call_args.kwargs
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
        mock_curator_instance.apply_consolidation_plan = AsyncMock(return_value=report)

        with (
            patch(
                "app.core.skills.curator.consolidation._get_consolidation_deps",
                AsyncMock(return_value=(MagicMock(), MagicMock())),
            ),
            patch("app.core.skills.curator.consolidation.scan_local_skills", _scan([MagicMock()])),
            patch("app.core.skills.curator.consolidation.bound_skill_names", AsyncMock(return_value=frozenset())),
            patch("myrm_agent_harness.agent.skills.curator.SkillCurator", return_value=mock_curator_instance),
        ):
            from app.core.skills.curator.consolidation import run_consolidation_execute

            result = await run_consolidation_execute(ConsolidationPlan())

        assert result == {
            "success_count": 1,
            "failure_count": 0,
            "total_archived": 2,
            "total_created": 0,
            "net_reduction": 1,
            "summary": report.to_summary(),
        }


_USER_BODY = "# git_operations\n\nRule 1: never force push.\nRule 2: rebase before merge.\n"


async def _save(service: SkillCreationService, name: str, body: str) -> SkillMetadata:
    saved = await service.save_skill(name, f"---\nname: {name}\ndescription: {name} skill\n---\n{body}")
    assert saved.success, saved.error
    return SkillMetadata(name=name, description=f"{name} skill", storage_path=saved.saved_path)


def _is_archived(skill: SkillMetadata) -> bool:
    ledger = Path(skill.storage_path or "") / ".stats.json"
    return ledger.exists() and json.loads(ledger.read_text(encoding="utf-8"))["lifecycle_status"] == "archived"


def _umbrella(target: str) -> ConsolidationAction:
    return ConsolidationAction(
        action_type=ConsolidationActionType.CREATE_UMBRELLA,
        target_skill=target,
        source_skills=("git_commit", "git_push"),
        reasoning="same domain",
        umbrella_description="Git operations",
    )


class TestConsolidationThroughTheProductionWriteBackend:
    """The executor against the real skill write backend, which replaces an existing skill on save."""

    @pytest.mark.asyncio
    async def test_umbrella_named_like_an_existing_skill_is_refused(self, tmp_path: Path) -> None:
        service = SkillCreationService(base_path=tmp_path)
        occupant = await _save(service, "git_operations", _USER_BODY)
        commit = await _save(service, "git_commit", "# commit\n")
        push = await _save(service, "git_push", "# push\n")
        before = (tmp_path / "git_operations" / "SKILL.md").read_bytes()
        executor = ConsolidationExecutor(service, SkillStatsCollector(), [occupant, commit, push])

        report = await executor.execute([_umbrella("git_operations")])

        assert (report.success_count, report.failure_count) == (0, 1)
        assert (tmp_path / "git_operations" / "SKILL.md").read_bytes() == before
        assert not _is_archived(commit)
        assert not _is_archived(push)

    @pytest.mark.asyncio
    async def test_umbrella_with_a_free_name_is_created_and_the_sources_archived(self, tmp_path: Path) -> None:
        service = SkillCreationService(base_path=tmp_path)
        commit = await _save(service, "git_commit", "# commit\n")
        push = await _save(service, "git_push", "# push\n")
        executor = ConsolidationExecutor(service, SkillStatsCollector(), [commit, push])

        report = await executor.execute([_umbrella("git_ops")])

        assert (report.success_count, report.failure_count) == (1, 0)
        umbrella = (tmp_path / "git_ops" / "SKILL.md").read_text(encoding="utf-8")
        assert "name: git_ops" in umbrella
        assert "- git_commit: git_commit skill" in umbrella
        assert _is_archived(commit)
        assert _is_archived(push)
