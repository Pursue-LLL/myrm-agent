"""Tests for ConfidenceApprovalFlow multi-signal risk assessment.

Covers:
- diff change ratio signal (large rewrites trigger red flag)
- historical effective rate signal (low-quality skills need human oversight)
- the usage ledger fed by real tool-call outcomes drives that signal end to end
- CAPTURED type edge case (empty original_content)
- risk_signals field in ApprovalResult
- combined conditions (LLM signals + risk signals)
"""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from myrm_agent_harness.agent.middlewares.tooling._skill_failure_tracking import track_skill_execution
from myrm_agent_harness.agent.skill_agent.context import add_loaded_skill, reset_loaded_skills
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionProposal,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.backends.skills.usage_recorder import (
    begin_skill_run_usage,
    commit_skill_run_usage,
    flush_skill_usage_stats,
    set_stats_collector,
)

from app.services.agent.confidence_approval_flow import (
    ConfidenceApprovalFlow,
)


def _make_proposal(
    *,
    skill_id: str = "test_skill",
    original: str = "def func():\n    return 1",
    proposed: str = "def func():\n    return 2",
    score: float = 0.9,
    is_general: bool = True,
    evolution_type: EvolutionType = EvolutionType.FIX,
) -> EvolutionProposal:
    return EvolutionProposal(
        skill_id=skill_id,
        evolution_type=evolution_type,
        original_content=original,
        proposed_content=proposed,
        diff="dummy",
        score=score,
        reasoning="test",
        is_general=is_general,
        created_at=None,
    )


class _SkillLedger:
    """Runs recorded through the real run-usage pipeline into the Curator's ``.stats.json`` ledger."""

    def __init__(self, skills_root: Path) -> None:
        self._skills_root = skills_root

    def record_runs(self, skill_name: str, outcomes: list[bool]) -> SkillRecord:
        """One run per outcome: the only loaded skill executes one tool call that succeeds or fails."""
        skill_dir = self._skills_root / skill_name
        skill_dir.mkdir(exist_ok=True)
        for index, success in enumerate(outcomes):
            begin_skill_run_usage()
            reset_loaded_skills()
            add_loaded_skill(
                SkillMetadata(
                    name=skill_name,
                    description=skill_name,
                    storage_skill_id=f"{skill_name}-id",
                    storage_path=str(skill_dir),
                )
            )
            track_skill_execution(
                "browser_interact_tool",
                tool_call_id=f"call-{index}",
                tool_args={},
                success=success,
                error_message="" if success else "Timeout: selector #pay was not found",
            )
            commit_skill_run_usage()
        reset_loaded_skills()
        flush_skill_usage_stats()
        return SkillRecord(
            skill_id=f"{skill_name}-id",
            name=skill_name,
            description=skill_name,
            content="steps",
            path=str(skill_dir / "SKILL.md"),
            lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED),
        )


@pytest.fixture
def skill_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_SkillLedger]:
    """Isolated skills root with the Curator service singletons pointed at it."""
    import app.core.skills.curator.service as curator_service
    import app.core.skills.models as models_mod

    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    monkeypatch.setattr(models_mod, "DEFAULT_LOCAL_SKILL_PATHS", [str(skills_root)])
    monkeypatch.setattr(curator_service, "DEFAULT_LOCAL_SKILL_PATHS", [str(skills_root)])
    monkeypatch.setattr("myrm_agent_harness.runtime.events.get_event_bus", lambda: SimpleNamespace(publish=lambda _event: None))
    curator_service._stats_collector = None
    curator_service.get_stats_collector()
    yield _SkillLedger(skills_root)
    curator_service._stats_collector = None
    set_stats_collector(None)
    reset_loaded_skills()


class TestEvaluateRiskSignals:
    """Unit tests for _evaluate_risk_signals static method."""

    def test_small_diff_no_signal(self) -> None:
        proposal = _make_proposal(original="abc" * 100, proposed="abc" * 110)
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(proposal, None)
        assert len(signals) == 0

    def test_large_diff_triggers_signal(self) -> None:
        proposal = _make_proposal(original="short", proposed="very long content " * 50)
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(proposal, None)
        assert any("diff_range" in s for s in signals)

    def test_empty_original_skips_diff_signal(self) -> None:
        proposal = _make_proposal(original="", proposed="new skill content")
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(proposal, None)
        assert not any("diff_range" in s for s in signals)

    def test_exact_threshold_no_signal(self) -> None:
        original = "a" * 100
        proposed = "a" * 150  # exactly 50% change — threshold is > 50%, so no trigger
        proposal = _make_proposal(original=original, proposed=proposed)
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(proposal, None)
        assert not any("diff_range" in s for s in signals)

    def test_below_threshold_no_signal(self) -> None:
        original = "a" * 100
        proposed = "a" * 140
        proposal = _make_proposal(original=original, proposed=proposed)
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(proposal, None)
        assert not any("diff_range" in s for s in signals)

    def test_low_effective_rate_triggers_signal(self, skill_ledger: _SkillLedger) -> None:
        skill_record = skill_ledger.record_runs("weak_skill", [True] + [False] * 4)
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(_make_proposal(), skill_record)
        assert any("low_effective_rate" in s for s in signals)

    def test_high_effective_rate_no_signal(self, skill_ledger: _SkillLedger) -> None:
        skill_record = skill_ledger.record_runs("strong_skill", [True] * 4 + [False])
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(_make_proposal(), skill_record)
        assert not any("low_effective_rate" in s for s in signals)

    def test_insufficient_data_skips_rate_signal(self, skill_ledger: _SkillLedger) -> None:
        skill_record = skill_ledger.record_runs("new_skill", [False, False])
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(_make_proposal(), skill_record)
        assert not any("low_effective_rate" in s for s in signals)

    def test_skill_without_a_usage_ledger_skips_rate_signal(self, skill_ledger: _SkillLedger) -> None:
        skill_record = skill_ledger.record_runs("unused_skill", [])
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(_make_proposal(), skill_record)
        assert not any("low_effective_rate" in s for s in signals)

    def test_skill_missing_from_the_skill_roots_skips_rate_signal(self, skill_ledger: _SkillLedger) -> None:
        skill_record = skill_ledger.record_runs("moved_skill", [False] * 5)
        skill_record.name = "not_on_disk"
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(_make_proposal(), skill_record)
        assert not any("low_effective_rate" in s for s in signals)

    def test_none_skill_record_no_rate_signal(self) -> None:
        proposal = _make_proposal()
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(proposal, None)
        assert not any("low_effective_rate" in s for s in signals)

    def test_combined_signals(self, skill_ledger: _SkillLedger) -> None:
        proposal = _make_proposal(original="short", proposed="very long " * 100)
        skill_record = skill_ledger.record_runs("weak_skill", [True] + [False] * 4)
        signals = ConfidenceApprovalFlow._evaluate_risk_signals(proposal, skill_record)
        assert any("diff_range" in s for s in signals)
        assert any("low_effective_rate" in s for s in signals)
        assert len(signals) == 2


@pytest.mark.parametrize(
    ("outcomes", "expected_signals"),
    [
        pytest.param([True] * 4 + [False] * 6, ["low_effective_rate:40%(10runs)"], id="four_ok_six_failed"),
        pytest.param([True] * 9 + [False], [], id="mostly_succeeding"),
        pytest.param([False] * 2, [], id="too_few_runs"),
    ],
)
def test_run_outcomes_feed_the_low_effective_rate_signal(
    skill_ledger: _SkillLedger, outcomes: list[bool], expected_signals: list[str]
) -> None:
    """Real tool-call outcomes of the only loaded skill reach the approval flow's rate signal through the ledger."""
    skill_record = skill_ledger.record_runs("checkout_skill", outcomes)

    signals = ConfidenceApprovalFlow._evaluate_risk_signals(_make_proposal(skill_id="checkout_skill-id"), skill_record)

    assert signals == expected_signals


@pytest.mark.asyncio
async def test_risk_signal_blocks_auto_approve() -> None:
    """Large diff prevents auto-merge even with high score + is_general."""
    proposal = _make_proposal(
        original="short original",
        proposed="completely rewritten " * 100,
        score=0.95,
        is_general=True,
    )

    flow = ConfidenceApprovalFlow(auto_approve_threshold=0.8)
    result = await flow.process_evolution(proposal)

    assert not result.approved
    assert result.requires_manual_review
    assert len(result.risk_signals) > 0
    assert any("diff_range" in s for s in result.risk_signals)


@pytest.mark.asyncio
async def test_clean_proposal_allows_auto_approve_path() -> None:
    """Small diff + high score + is_general proceeds to auto-approve attempt."""
    proposal = _make_proposal(
        original="def func():\n    return 1",
        proposed="def func():\n    return 2",
        score=0.95,
        is_general=True,
    )

    flow = ConfidenceApprovalFlow(auto_approve_threshold=0.8)
    result = await flow.process_evolution(proposal)

    assert result.risk_signals == []
    # Note: auto-approve may still fail at apply step (disk/store),
    # but the risk_signals gate should not block it


@pytest.mark.asyncio
async def test_approval_result_has_risk_signals_field() -> None:
    """ApprovalResult always includes risk_signals field."""
    proposal = _make_proposal(score=0.3, is_general=False)

    flow = ConfidenceApprovalFlow()
    result = await flow.process_evolution(proposal)

    assert isinstance(result.risk_signals, list)
    assert result.requires_manual_review


@pytest.mark.asyncio
async def test_test_passed_reflects_score() -> None:
    """test_passed is True when score > 0, False when score == 0."""
    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models import ApprovalRecord
    from app.services.skills.evolution_reviews import approval_to_evolution_review_record

    async def _review_for_skill(skill_id: str) -> tuple[ApprovalRecord, object]:
        async with get_session() as db:
            result = await db.execute(
                select(ApprovalRecord).where(ApprovalRecord.action_type == "evolution").order_by(ApprovalRecord.created_at.desc())
            )
            for record in result.scalars().all():
                review = approval_to_evolution_review_record(record)
                if review is not None and review.skill_id == skill_id:
                    return record, review
        raise AssertionError(f"No evolution review for skill_id={skill_id}")

    zero_proposal = _make_proposal(skill_id="test_skill_zero_score", score=0.0, is_general=False)
    flow = ConfidenceApprovalFlow()
    await flow.process_evolution(zero_proposal)

    record, review = await _review_for_skill("test_skill_zero_score")
    assert review.test_passed is False
    async with get_session() as db:
        await db.delete(record)
        await db.commit()

    positive_proposal = _make_proposal(skill_id="test_skill_positive_score", score=0.5, is_general=False)
    await flow.process_evolution(positive_proposal)

    record, review = await _review_for_skill("test_skill_positive_score")
    assert review.test_passed is True
    async with get_session() as db:
        await db.delete(record)
        await db.commit()
