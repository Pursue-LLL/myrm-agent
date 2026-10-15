from typing import ClassVar

from myrm_agent_harness.agent.sub_agents.orthogonal_reviewer import (
    ArbitrationStatus,
    ArbitrationVerdict,
    FindingCategory,
    FindingSeverity,
    OrthogonalReviewArbiter,
    ReviewFinding,
    ReviewerPerspective,
    ReviewerReport,
)

from app.schemas.orthogonal_reviewer import (
    ArbitrationVerdictDTO,
    AutoFixResponse,
    FullReviewResponse,
    ReviewFindingDTO,
    ReviewerReportDTO,
)


class OrthogonalReviewerService:
    """Service orchestrating dual orthogonal reviewers and arbitration auto-fix loop."""

    _instance: ClassVar["OrthogonalReviewerService | None"] = None

    def __init__(self) -> None:
        self._arbiter = OrthogonalReviewArbiter()
        self._sessions: dict[str, ArbitrationVerdict] = {}
        self._reports_a: dict[str, ReviewerReport] = {}
        self._reports_b: dict[str, ReviewerReport] = {}

    @classmethod
    def get_instance(cls) -> "OrthogonalReviewerService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def _convert_finding_to_dto(self, f: ReviewFinding) -> ReviewFindingDTO:
        return ReviewFindingDTO(
            finding_id=f.finding_id,
            reviewer=f.reviewer.value,
            severity=f.severity.value,
            category=f.category.value,
            title=f.title,
            description=f.description,
            file_path=f.file_path,
            line_range=f.line_range,
            suggestion=f.suggestion,
        )

    def _convert_report_to_dto(self, r: ReviewerReport) -> ReviewerReportDTO:
        return ReviewerReportDTO(
            perspective=r.perspective.value,
            findings=[self._convert_finding_to_dto(f) for f in r.findings],
            passed=r.passed,
            summary=r.summary,
            execution_time_ms=r.execution_time_ms,
        )

    def _convert_verdict_to_dto(self, v: ArbitrationVerdict) -> ArbitrationVerdictDTO:
        return ArbitrationVerdictDTO(
            session_id=v.session_id,
            is_approved=v.is_approved,
            status=v.status.value,
            max_severity=v.max_severity.value if v.max_severity else None,
            merged_findings=[self._convert_finding_to_dto(f) for f in v.merged_findings],
            deduplicated_count=v.deduplicated_count,
            auto_fix_prompts=v.auto_fix_prompts,
            summary=v.summary,
        )

    def review_intent(
        self,
        task_prompt: str,
        architecture_plan: str,
        code_diff: str,
        files_touched: list[str],
    ) -> ReviewerReportDTO:
        report = self._arbiter.intent_reviewer.review(
            task_prompt=task_prompt,
            architecture_plan=architecture_plan,
            code_diff=code_diff,
            files_touched=files_touched,
        )
        return self._convert_report_to_dto(report)

    def review_blind(
        self,
        code_diff: str,
        files_touched: list[str],
        public_signatures: list[str] | None = None,
    ) -> ReviewerReportDTO:
        report = self._arbiter.blind_reviewer.review(
            code_diff=code_diff,
            files_touched=files_touched,
            public_signatures=public_signatures,
        )
        return self._convert_report_to_dto(report)

    def arbitrate(
        self,
        session_id: str,
        report_a_dto: ReviewerReportDTO,
        report_b_dto: ReviewerReportDTO,
    ) -> ArbitrationVerdictDTO:
        harness_findings_a = [
            ReviewFinding(
                finding_id=f.finding_id,
                reviewer=ReviewerPerspective(f.reviewer),
                severity=FindingSeverity(f.severity),
                category=FindingCategory(f.category),
                title=f.title,
                description=f.description,
                file_path=f.file_path,
                line_range=f.line_range,
                suggestion=f.suggestion,
            )
            for f in report_a_dto.findings
        ]
        rep_a = ReviewerReport(
            perspective=ReviewerPerspective(report_a_dto.perspective),
            findings=harness_findings_a,
            passed=report_a_dto.passed,
            summary=report_a_dto.summary,
            execution_time_ms=report_a_dto.execution_time_ms,
        )

        harness_findings_b = [
            ReviewFinding(
                finding_id=f.finding_id,
                reviewer=ReviewerPerspective(f.reviewer),
                severity=FindingSeverity(f.severity),
                category=FindingCategory(f.category),
                title=f.title,
                description=f.description,
                file_path=f.file_path,
                line_range=f.line_range,
                suggestion=f.suggestion,
            )
            for f in report_b_dto.findings
        ]
        rep_b = ReviewerReport(
            perspective=ReviewerPerspective(report_b_dto.perspective),
            findings=harness_findings_b,
            passed=report_b_dto.passed,
            summary=report_b_dto.summary,
            execution_time_ms=report_b_dto.execution_time_ms,
        )

        verdict = self._arbiter.arbitrate(session_id=session_id, report_a=rep_a, report_b=rep_b)
        self._sessions[session_id] = verdict
        self._reports_a[session_id] = rep_a
        self._reports_b[session_id] = rep_b
        return self._convert_verdict_to_dto(verdict)

    def conduct_full_review(
        self,
        session_id: str,
        task_prompt: str,
        architecture_plan: str,
        code_diff: str,
        files_touched: list[str],
        public_signatures: list[str] | None = None,
    ) -> FullReviewResponse:
        rep_a, rep_b, verdict = self._arbiter.conduct_full_review(
            session_id=session_id,
            task_prompt=task_prompt,
            architecture_plan=architecture_plan,
            code_diff=code_diff,
            files_touched=files_touched,
            public_signatures=public_signatures,
        )
        self._sessions[session_id] = verdict
        self._reports_a[session_id] = rep_a
        self._reports_b[session_id] = rep_b

        return FullReviewResponse(
            session_id=session_id,
            report_a=self._convert_report_to_dto(rep_a),
            report_b=self._convert_report_to_dto(rep_b),
            verdict=self._convert_verdict_to_dto(verdict),
        )

    def get_verdict(self, session_id: str) -> ArbitrationVerdictDTO | None:
        v = self._sessions.get(session_id)
        if v:
            return self._convert_verdict_to_dto(v)
        return None

    def apply_auto_fix(self, session_id: str, finding_ids: list[str]) -> AutoFixResponse:
        verdict = self._sessions.get(session_id)
        if not verdict:
            return AutoFixResponse(
                session_id=session_id,
                applied_count=0,
                remaining_critical_count=0,
                fix_summary="未找到会话审查快照",
            )

        # Filter out fixed findings
        remaining = [f for f in verdict.merged_findings if f.finding_id not in finding_ids]
        applied_count = len(verdict.merged_findings) - len(remaining)

        # Re-evaluate approval
        remaining_critical = [f for f in remaining if f.severity == FindingSeverity.CRITICAL]
        new_is_approved = len(remaining_critical) == 0
        new_status = ArbitrationStatus.APPROVED if new_is_approved else ArbitrationStatus.BLOCKED_AUTO_FIX

        updated_verdict = ArbitrationVerdict(
            session_id=session_id,
            is_approved=new_is_approved,
            status=new_status,
            max_severity=FindingSeverity.CRITICAL if remaining_critical else None,
            merged_findings=remaining,
            deduplicated_count=verdict.deduplicated_count,
            auto_fix_prompts=[] if new_is_approved else verdict.auto_fix_prompts,
            summary=f"自动修复已应用: 修复了 {applied_count} 处缺陷，剩余 {len(remaining)} 处。",
        )
        self._sessions[session_id] = updated_verdict

        return AutoFixResponse(
            session_id=session_id,
            applied_count=applied_count,
            remaining_critical_count=len(remaining_critical),
            fix_summary=f"成功针对 {applied_count} 个指定缺陷生成并应用修复补丁。",
        )
