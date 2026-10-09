"""[POS]: app/services/memory/job_compounding_service.py
[INPUT]: Harness job compounding models, engines, server DTOs, and workspace paths.
[OUTPUT]: DomainJobCompoundingService providing job description building, boundary check, and compounding maturity evaluation.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    CompoundedRule,
    CompoundingMaturityTracker,
    JobDescriptionBuilder,
    JobDescriptionSpec,
    PreferenceCompoundingEngine,
    RuleType,
)

from app.schemas.job_compounding import (
    ApprovalBoundaryDTO,
    CheckApprovalRequestDTO,
    CheckApprovalResponseDTO,
    CompoundedRuleDTO,
    CompoundingMaturityReportDTO,
    JobDescriptionSpecDTO,
    RecordRuleRequestDTO,
    SaveJobDescriptionRequestDTO,
)


class DomainJobCompoundingService:
    """Service orchestrating 4-pillar job descriptions, approval gates, and compounded experience."""

    def __init__(self, workspace_dir: Path | str | None = None) -> None:
        if workspace_dir is None:
            base_dir = Path("/tmp/myrm_sandbox_workspace")
            base_dir.mkdir(parents=True, exist_ok=True)
            self._workspace_dir = base_dir
        else:
            self._workspace_dir = Path(workspace_dir)

        self._jobs: dict[str, JobDescriptionSpec] = {}
        self._engine = PreferenceCompoundingEngine(base_storage_dir=self._workspace_dir)
        self._maturity_tracker = CompoundingMaturityTracker()

    def save_job_description(self, request: SaveJobDescriptionRequestDTO) -> JobDescriptionSpecDTO:
        """Constructs and saves a domain-specific job description with 4 pillars."""
        spec = JobDescriptionBuilder.build_spec(
            agent_id=request.agent_id,
            job_title=request.job_title,
            target_scope=request.target_scope,
            tools_and_sources=request.tools_and_sources,
            work_style=request.work_style,
            autonomous_actions=request.autonomous_actions,
            requires_approval_actions=request.requires_approval_actions,
        )
        self._jobs[request.agent_id] = spec
        return self._spec_to_dto(spec)

    def get_job_description(self, agent_id: str) -> JobDescriptionSpecDTO | None:
        """Retrieves active job description for the given agent."""
        spec = self._jobs.get(agent_id)
        if spec is None:
            return None
        return self._spec_to_dto(spec)

    def check_approval_boundary(self, request: CheckApprovalRequestDTO) -> CheckApprovalResponseDTO:
        """Evaluates whether an action requires explicit human escalation."""
        spec = self._jobs.get(request.agent_id)
        if spec is None:
            # Default conservative evaluation if no job description exists
            needs_approval = "delete" in request.action_name or "exec" in request.action_name
            reason = "Default conservative policy (no job description configured)"
            return CheckApprovalResponseDTO(
                agent_id=request.agent_id,
                action_name=request.action_name,
                needs_approval=needs_approval,
                reason=reason,
            )

        needs_approval, reason = JobDescriptionBuilder.evaluate_action_boundary(
            spec=spec, action_name=request.action_name
        )

        return CheckApprovalResponseDTO(
            agent_id=request.agent_id,
            action_name=request.action_name,
            needs_approval=needs_approval,
            reason=reason,
        )

    def record_compounded_rule(self, request: RecordRuleRequestDTO) -> CompoundedRuleDTO:
        """Records a new compounded rule extracted from operational feedback."""
        try:
            rule_type = RuleType(request.rule_type)
        except ValueError:
            rule_type = RuleType.POSITIVE_PREFERENCE

        rule = self._engine.record_rule(
            agent_id=request.agent_id,
            rule_type=rule_type,
            statement=request.statement,
            trigger_condition=request.trigger_condition,
            evidence_source=request.evidence_source,
        )

        return self._rule_to_dto(rule)

    def list_compounded_rules(self, agent_id: str, rule_type: str | None = None) -> list[CompoundedRuleDTO]:
        """Lists compounded rules for the specified agent, optionally filtered by type."""
        filter_type: RuleType | None = None
        if rule_type:
            try:
                filter_type = RuleType(rule_type)
            except ValueError:
                pass

        rules = self._engine.list_rules(agent_id=agent_id, rule_type=filter_type)
        return [self._rule_to_dto(r) for r in rules]

    def evaluate_maturity(self, agent_id: str) -> CompoundingMaturityReportDTO:
        """Computes compounding maturity score and tier evaluation."""
        spec = self._jobs.get(agent_id)
        if spec is None:
            spec = JobDescriptionBuilder.build_spec(
                agent_id=agent_id,
                job_title="General Assistant",
                target_scope="General task execution and domain support",
            )
        rules = self._engine.list_rules(agent_id=agent_id)
        report = CompoundingMaturityTracker.evaluate_maturity(spec=spec, rules=rules)

        return CompoundingMaturityReportDTO(
            agent_id=report.agent_id,
            job_title=report.job_title,
            total_rules_count=report.total_rules_count,
            positive_preferences_count=report.positive_preferences_count,
            negative_constraints_count=report.negative_constraints_count,
            inspection_lessons_count=report.inspection_lessons_count,
            maturity_score=report.maturity_score,
            tier=report.tier.value,
            summary=report.summary,
        )

    def _spec_to_dto(self, spec: JobDescriptionSpec) -> JobDescriptionSpecDTO:
        """Converts harness domain spec to API DTO."""
        return JobDescriptionSpecDTO(
            agent_id=spec.agent_id,
            job_title=spec.job_title,
            target_scope=spec.target_scope,
            tools_and_sources=list(spec.tools_and_sources),
            work_style=spec.work_style,
            approval_boundary=ApprovalBoundaryDTO(
                autonomous_actions=list(spec.approval_boundary.autonomous_actions),
                requires_approval_actions=list(spec.approval_boundary.requires_approval_actions),
            ),
            created_at=spec.created_at,
            updated_at=spec.updated_at,
        )

    def _rule_to_dto(self, rule: CompoundedRule) -> CompoundedRuleDTO:
        """Converts harness domain rule to API DTO."""
        return CompoundedRuleDTO(
            rule_id=rule.rule_id,
            agent_id=rule.agent_id,
            rule_type=rule.rule_type.value,
            statement=rule.statement,
            trigger_condition=rule.trigger_condition,
            evidence_source=rule.evidence_source,
            hit_count=rule.hit_count,
            created_at=rule.created_at,
        )


_job_compounding_service_instance: DomainJobCompoundingService | None = None


def get_job_compounding_service() -> DomainJobCompoundingService:
    """Dependency provider yielding the singleton DomainJobCompoundingService instance."""
    global _job_compounding_service_instance
    if _job_compounding_service_instance is None:
        _job_compounding_service_instance = DomainJobCompoundingService()
    return _job_compounding_service_instance

