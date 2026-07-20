"""Unit tests for chat_id traceability through the skill growth pipeline.

Verifies that chat_id written into ApprovalRecord is correctly propagated
through EvolutionReviewRecord, SkillGrowthCaseRead, and API response models.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.services.skills.evolution_reviews import (
    EvolutionApplyStatus,
    EvolutionGrowthStatus,
    EvolutionReviewRecord,
    approval_to_evolution_review_record,
)
from app.services.skills.growth_case_types import SkillGrowthCaseSource
from app.services.skills.growth_queries import (
    _approval_case,
    _evolution_case,
)


def _make_approval_record(
    *,
    chat_id: str | None = "test-chat-abc",
    action_type: str = "evolution",
) -> MagicMock:
    record = MagicMock()
    record.id = "approval-001"
    record.agent_id = "agent-001"
    record.chat_id = chat_id
    record.action_type = action_type
    record.status = "PENDING"
    record.reason = "Detected reusable pattern"
    record.severity = "warning"
    record.payload = {
        "schema_version": 1,
        "skill_id": "sk-001",
        "skill_name": "weekly-report",
        "skill_path": "/skills/weekly-report/SKILL.md",
        "evolution_type": "captured",
        "reason": "Detected reusable pattern",
        "original_content": "old content",
        "evolved_content": "new content",
        "confidence": 0.85,
        "test_passed": True,
        "task_context": "User asked to write a weekly report",
        "growth_status": "PENDING_REVIEW",
        "apply_status": "NOT_APPLIED",
    }
    record.created_at = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    record.resolved_at = None
    return record


def _make_evolution_review_record(
    *,
    chat_id: str | None = "test-chat-xyz",
) -> EvolutionReviewRecord:
    return EvolutionReviewRecord(
        id="evo-001",
        source="approval",
        skill_id="sk-002",
        skill_name="data-analysis",
        skill_path="/skills/data-analysis/SKILL.md",
        evolution_type="optimize",
        reason="Improved data processing logic",
        original_content="old",
        evolved_content="new",
        confidence=0.9,
        test_passed=True,
        status=EvolutionGrowthStatus.PENDING_REVIEW,
        approval_status="PENDING",
        apply_status=EvolutionApplyStatus.NOT_APPLIED,
        apply_error=None,
        reason_code="manual_review",
        remediation=None,
        runtime_failure=None,
        trajectory=None,
        chat_id=chat_id,
        task_context="User requested data analysis",
        created_at=datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC),
        resolved_at=None,
    )


class TestApprovalToEvolutionReviewRecord:
    """Tests for approval_to_evolution_review_record() chat_id mapping."""

    def test_chat_id_preserved_when_present(self) -> None:
        record = _make_approval_record(chat_id="session-123")
        result = approval_to_evolution_review_record(record)
        assert result is not None
        assert result.chat_id == "session-123"

    def test_chat_id_none_when_absent(self) -> None:
        record = _make_approval_record(chat_id=None)
        result = approval_to_evolution_review_record(record)
        assert result is not None
        assert result.chat_id is None

    def test_task_context_preserved(self) -> None:
        record = _make_approval_record()
        result = approval_to_evolution_review_record(record)
        assert result is not None
        assert result.task_context == "User asked to write a weekly report"

    def test_non_evolution_returns_none(self) -> None:
        record = _make_approval_record(action_type="shell_command")
        result = approval_to_evolution_review_record(record)
        assert result is None


class TestApprovalCase:
    """Tests for _approval_case() chat_id mapping (draft path)."""

    def test_chat_id_propagated_to_growth_case(self) -> None:
        record = _make_approval_record(
            chat_id="draft-chat-456",
            action_type="skill_draft",
        )
        case = _approval_case(record)
        assert case.chat_id == "draft-chat-456"
        assert case.source == SkillGrowthCaseSource.DRAFT

    def test_chat_id_none_propagated(self) -> None:
        record = _make_approval_record(
            chat_id=None,
            action_type="skill_draft",
        )
        case = _approval_case(record)
        assert case.chat_id is None


class TestEvolutionCase:
    """Tests for _evolution_case() chat_id mapping (evolution path)."""

    def test_chat_id_propagated_to_growth_case(self) -> None:
        review = _make_evolution_review_record(chat_id="evo-chat-789")
        case = _evolution_case(review)
        assert case.chat_id == "evo-chat-789"
        assert case.source == SkillGrowthCaseSource.EVOLUTION

    def test_chat_id_none_propagated(self) -> None:
        review = _make_evolution_review_record(chat_id=None)
        case = _evolution_case(review)
        assert case.chat_id is None


class TestApiResponseModels:
    """Tests for API response models including chat_id."""

    def test_growth_case_response_includes_chat_id(self) -> None:
        from app.api.skills.growth import SkillGrowthCaseSummaryResponse

        resp = SkillGrowthCaseSummaryResponse(
            id="test",
            source="evolution",
            status="PENDING_REVIEW",
            skill_name="test-skill",
            growth_type="captured",
            title="test",
            summary="test",
            chat_id="resp-chat-001",
            created_at="2025-06-01T12:00:00Z",
        )
        assert resp.chat_id == "resp-chat-001"
        data = resp.model_dump()
        assert data["chat_id"] == "resp-chat-001"

    def test_growth_case_response_chat_id_defaults_none(self) -> None:
        from app.api.skills.growth import SkillGrowthCaseSummaryResponse

        resp = SkillGrowthCaseSummaryResponse(
            id="test",
            source="evolution",
            status="PENDING_REVIEW",
            skill_name="test-skill",
            growth_type="captured",
            title="test",
            summary="test",
            created_at="2025-06-01T12:00:00Z",
        )
        assert resp.chat_id is None

    def test_pending_evolution_response_includes_chat_id(self) -> None:
        from app.api.skills.evolution.pending import PendingEvolutionResponse

        resp = PendingEvolutionResponse(
            id="test",
            skill_id="sk-001",
            skill_name="test-skill",
            evolution_type="captured",
            reason="test",
            original_content="old",
            evolved_content="new",
            confidence=0.9,
            test_passed=True,
            status="PENDING_REVIEW",
            approval_status="PENDING",
            apply_status="NOT_APPLIED",
            chat_id="pending-chat-002",
            created_at="2025-06-01T12:00:00Z",
        )
        assert resp.chat_id == "pending-chat-002"

    def test_pending_evolution_response_chat_id_defaults_none(self) -> None:
        from app.api.skills.evolution.pending import PendingEvolutionResponse

        resp = PendingEvolutionResponse(
            id="test",
            skill_id="sk-001",
            skill_name="test-skill",
            evolution_type="captured",
            reason="test",
            original_content="old",
            evolved_content="new",
            confidence=0.9,
            test_passed=True,
            status="PENDING_REVIEW",
            approval_status="PENDING",
            apply_status="NOT_APPLIED",
            created_at="2025-06-01T12:00:00Z",
        )
        assert resp.chat_id is None

    def test_growth_response_null_chat_id_serializes_to_none(self) -> None:
        from app.api.skills.growth import SkillGrowthCaseSummaryResponse

        resp = SkillGrowthCaseSummaryResponse(
            id="test",
            source="draft",
            status="PENDING_REVIEW",
            skill_name="test-skill",
            growth_type="skill_draft",
            title="test",
            summary="test",
            chat_id=None,
            created_at="2025-06-01T12:00:00Z",
        )
        data = resp.model_dump()
        assert data["chat_id"] is None
        json_data = resp.model_dump(mode="json")
        assert json_data["chat_id"] is None

    def test_growth_response_empty_string_chat_id(self) -> None:
        from app.api.skills.growth import SkillGrowthCaseSummaryResponse

        resp = SkillGrowthCaseSummaryResponse(
            id="test",
            source="draft",
            status="PENDING_REVIEW",
            skill_name="test-skill",
            growth_type="skill_draft",
            title="test",
            summary="test",
            chat_id="",
            created_at="2025-06-01T12:00:00Z",
        )
        assert resp.chat_id == ""

    def test_pending_response_model_dump_json_serialization(self) -> None:
        from app.api.skills.evolution.pending import PendingEvolutionResponse

        resp = PendingEvolutionResponse(
            id="test",
            skill_id="sk-001",
            skill_name="test-skill",
            evolution_type="captured",
            reason="test",
            original_content="old",
            evolved_content="new",
            confidence=0.9,
            test_passed=True,
            status="PENDING_REVIEW",
            approval_status="PENDING",
            apply_status="NOT_APPLIED",
            chat_id="json-chat-001",
            created_at="2025-06-01T12:00:00Z",
        )
        json_data = resp.model_dump(mode="json")
        assert json_data["chat_id"] == "json-chat-001"


class TestFullPipelineRoundtrip:
    """End-to-end data flow from mock approval → growth case read → API response."""

    def test_approval_to_growth_case_to_api_response(self) -> None:
        from app.api.skills.growth import SkillGrowthCaseSummaryResponse

        record = _make_approval_record(chat_id="e2e-chat-999")
        evo_review = approval_to_evolution_review_record(record)
        assert evo_review is not None
        assert evo_review.chat_id == "e2e-chat-999"

        growth_case = _evolution_case(evo_review)
        assert growth_case.chat_id == "e2e-chat-999"

        api_resp = SkillGrowthCaseSummaryResponse(
            id=growth_case.id,
            source=growth_case.source.value,
            status=growth_case.status.value,
            skill_name=growth_case.skill_name,
            growth_type=growth_case.growth_type,
            title=growth_case.title,
            summary=growth_case.summary,
            chat_id=growth_case.chat_id,
            created_at=str(growth_case.created_at),
        )
        assert api_resp.chat_id == "e2e-chat-999"
        assert api_resp.model_dump()["chat_id"] == "e2e-chat-999"

    def test_null_chat_id_roundtrip(self) -> None:
        from app.api.skills.growth import SkillGrowthCaseSummaryResponse

        record = _make_approval_record(chat_id=None)
        evo_review = approval_to_evolution_review_record(record)
        assert evo_review is not None
        assert evo_review.chat_id is None

        growth_case = _evolution_case(evo_review)
        assert growth_case.chat_id is None

        api_resp = SkillGrowthCaseSummaryResponse(
            id=growth_case.id,
            source=growth_case.source.value,
            status=growth_case.status.value,
            skill_name=growth_case.skill_name,
            growth_type=growth_case.growth_type,
            title=growth_case.title,
            summary=growth_case.summary,
            chat_id=growth_case.chat_id,
            created_at=str(growth_case.created_at),
        )
        assert api_resp.chat_id is None
        assert api_resp.model_dump()["chat_id"] is None
