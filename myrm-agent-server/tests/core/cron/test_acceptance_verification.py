"""Unit tests for acceptance criteria verification in cron direct-execution mode."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.goals.verification.base import (
    AggregatedVerificationResult,
    VerificationResult,
)
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult, JobType, Schedule, ScheduleKind

from app.core.cron.adapters.acceptance_verification import (
    _with_verification_metadata,
    apply_acceptance_criteria_verification,
)


def _minimal_job(**overrides: object) -> CronJob:
    payload: dict[str, object] = {
        "id": "job-ac-1",
        "user_id": "user-1",
        "name": "test-acceptance",
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.INTERVAL, interval_ms=60_000),
    }
    payload.update(overrides)
    return CronJob(**payload)  # type: ignore[arg-type]


def _ok_result() -> JobResult:
    return JobResult(success=True, output="done")


class TestApplyAcceptanceCriteriaVerification:
    """Core logic tests for apply_acceptance_criteria_verification."""

    @pytest.mark.asyncio
    async def test_no_criteria_returns_unchanged(self) -> None:
        job = _minimal_job(acceptance_criteria=())
        result = _ok_result()
        out = await apply_acceptance_criteria_verification(job, result)
        assert out is result

    @pytest.mark.asyncio
    async def test_semantic_only_criteria_skipped_in_direct_mode(self) -> None:
        job = _minimal_job(
            acceptance_criteria=({"type": "semantic", "description": "check something"},),
        )
        result = _ok_result()
        out = await apply_acceptance_criteria_verification(job, result)
        assert out is result

    @pytest.mark.asyncio
    async def test_shell_criteria_pass(self) -> None:
        job = _minimal_job(
            acceptance_criteria=({"type": "shell", "command": "echo ok"},),
        )
        result = _ok_result()

        mock_agg = AggregatedVerificationResult(
            passed=True,
            per_criterion=[
                VerificationResult(passed=True, criterion_label="shell: echo ok"),
            ],
        )

        with patch(
            "app.core.cron.adapters.acceptance_verification.VerificationGatekeeper"
        ) as MockGK:
            instance = MockGK.return_value
            instance.criteria = [object()]
            instance.verify_all = AsyncMock(return_value=mock_agg)

            out = await apply_acceptance_criteria_verification(job, result)

        assert out.success is True
        assert out.metadata["verification"]["status"] == "pass"
        assert out.metadata["verification"]["passed"] is True

    @pytest.mark.asyncio
    async def test_shell_criteria_fail(self) -> None:
        job = _minimal_job(
            acceptance_criteria=(
                {"type": "shell", "command": "test -f /tmp/missing"},
                {"type": "shell", "command": "echo works"},
            ),
        )
        result = _ok_result()

        mock_agg = AggregatedVerificationResult(
            passed=False,
            per_criterion=[
                VerificationResult(
                    passed=False,
                    criterion_label="shell: test -f /tmp/missing",
                    reason="exit code 1",
                ),
                VerificationResult(passed=True, criterion_label="shell: echo works"),
            ],
        )

        with patch(
            "app.core.cron.adapters.acceptance_verification.VerificationGatekeeper"
        ) as MockGK:
            instance = MockGK.return_value
            instance.criteria = [object(), object()]
            instance.verify_all = AsyncMock(return_value=mock_agg)

            out = await apply_acceptance_criteria_verification(job, result)

        assert out.success is False
        assert out.metadata["verification"]["status"] == "fail"
        assert out.metadata["verification"]["passed"] is False
        assert "1 criterion(s) failed" in out.metadata["verification"]["summary"]
        assert out.exit_code == 2

    @pytest.mark.asyncio
    async def test_timeout_marks_error(self) -> None:
        job = _minimal_job(
            acceptance_criteria=({"type": "shell", "command": "sleep 999"},),
        )
        result = _ok_result()

        with patch(
            "app.core.cron.adapters.acceptance_verification.VerificationGatekeeper"
        ) as MockGK:
            instance = MockGK.return_value
            instance.criteria = [object()]
            instance.verify_all = AsyncMock(side_effect=asyncio.TimeoutError())

            out = await apply_acceptance_criteria_verification(
                job, result, timeout_seconds=0.01,
            )

        assert out.success is False
        assert out.metadata["verification"]["status"] == "error"
        assert "timed out" in out.metadata["verification"]["summary"]

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_original(self) -> None:
        job = _minimal_job(
            acceptance_criteria=({"type": "shell", "command": "echo x"},),
        )
        result = _ok_result()

        with patch(
            "app.core.cron.adapters.acceptance_verification.VerificationGatekeeper"
        ) as MockGK:
            instance = MockGK.return_value
            instance.criteria = [object()]
            instance.verify_all = AsyncMock(side_effect=RuntimeError("unexpected"))

            out = await apply_acceptance_criteria_verification(job, result)

        assert out is result

    @pytest.mark.asyncio
    async def test_mixed_criteria_filters_shell_only(self) -> None:
        job = _minimal_job(
            acceptance_criteria=(
                {"type": "shell", "command": "echo ok"},
                {"type": "semantic", "description": "check output quality"},
            ),
        )
        result = _ok_result()

        mock_agg = AggregatedVerificationResult(
            passed=True,
            per_criterion=[
                VerificationResult(passed=True, criterion_label="shell: echo ok"),
            ],
        )

        with patch(
            "app.core.cron.adapters.acceptance_verification.VerificationGatekeeper"
        ) as MockGK:
            instance = MockGK.return_value
            instance.criteria = [object()]
            instance.verify_all = AsyncMock(return_value=mock_agg)

            out = await apply_acceptance_criteria_verification(job, result)

            MockGK.assert_called_once_with([{"type": "shell", "command": "echo ok"}])

        assert out.metadata["verification"]["passed"] is True


class TestWithVerificationMetadata:
    """Tests for the metadata attachment helper."""

    def test_pass_metadata(self) -> None:
        result = _ok_result()
        out = _with_verification_metadata(result, status="pass", passed=True, summary="All good")
        assert out.success is True
        assert out.metadata["verification"] == {"status": "pass", "passed": True, "summary": "All good"}

    def test_fail_overrides_success(self) -> None:
        result = _ok_result()
        out = _with_verification_metadata(
            result, status="fail", passed=False,
            summary="failed", success_override=False,
        )
        assert out.success is False
        assert out.exit_code == 2
        assert "acceptance criteria" in out.error

    def test_truncates_long_summary(self) -> None:
        result = _ok_result()
        long_summary = "x" * 1000
        out = _with_verification_metadata(result, status="fail", passed=False, summary=long_summary)
        assert len(out.metadata["verification"]["summary"]) <= 500
