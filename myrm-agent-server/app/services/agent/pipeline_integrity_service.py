"""Service implementing Open Source Handoff Gap Lint & Pipeline Integrity Doctor (Item 53).

[INPUT]
- PipelineDefinitionDTO, HandoffStepDTO, LintPipelineRequest, AutoHealPipelineRequest.

[OUTPUT]
- PipelineIntegrityDoctorReportDTO, DecisionChainLinkDTO, PipelineDefinitionDTO.

[POS]
- Server-side business service wrapping the Harness PipelineIntegrityDoctor engine.
"""

from __future__ import annotations

import time

from myrm_agent_harness.agent.sub_agents.pipeline_integrity import (
    HandoffMetadata,
    HandoffStep,
    PipelineDefinition,
    PipelineIntegrityDoctor,
    StepStage,
)

from app.schemas.pipeline_integrity import (
    DecisionChainLinkDTO,
    GapCategoryEnum,
    GapSeverityEnum,
    HandoffGapDiagnosticDTO,
    HandoffMetadataDTO,
    HandoffStepDTO,
    PipelineDefinitionDTO,
    PipelineIntegrityDoctorReportDTO,
    StepStageEnum,
)


def _convert_dto_to_domain_step(dto: HandoffStepDTO) -> HandoffStep:
    """Convert a schema DTO step into a domain HandoffStep."""
    metadata = None
    if dto.metadata:
        metadata = HandoffMetadata(
            source_agent=dto.metadata.source_agent,
            target_agent=dto.metadata.target_agent,
            transfer_reason=dto.metadata.transfer_reason,
            context_keys=list(dto.metadata.context_keys),
        )

    return HandoffStep(
        step_id=dto.step_id,
        stage=StepStage(dto.stage.value),
        agent_role=dto.agent_role,
        requires_approval=dto.requires_approval,
        requires_verification=dto.requires_verification,
        produced_artifacts=list(dto.produced_artifacts),
        metadata=metadata,
    )


def _convert_domain_step_to_dto(step: HandoffStep) -> HandoffStepDTO:
    """Convert a domain HandoffStep into a schema DTO step."""
    metadata_dto = None
    if step.metadata:
        metadata_dto = HandoffMetadataDTO(
            source_agent=step.metadata.source_agent,
            target_agent=step.metadata.target_agent,
            transfer_reason=step.metadata.transfer_reason,
            context_keys=list(step.metadata.context_keys),
        )

    return HandoffStepDTO(
        step_id=step.step_id,
        stage=StepStageEnum(step.stage.value),
        agent_role=step.agent_role,
        requires_approval=step.requires_approval,
        requires_verification=step.requires_verification,
        produced_artifacts=list(step.produced_artifacts),
        metadata=metadata_dto,
    )


class PipelineIntegrityService:
    """Business service providing pipeline integrity analysis, gap detection, and healing."""

    _instance: PipelineIntegrityService | None = None

    def __init__(self) -> None:
        """Initialize service with Harness PipelineIntegrityDoctor and report cache."""
        self._doctor = PipelineIntegrityDoctor()
        self._latest_reports: dict[str, PipelineIntegrityDoctorReportDTO] = {}

    @classmethod
    def get_instance(cls) -> PipelineIntegrityService:
        """Retrieve singleton service instance."""
        if cls._instance is None:
            cls._instance = PipelineIntegrityService()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton service instance for test isolation."""
        cls._instance = None

    def lint_pipeline(self, pipeline_dto: PipelineDefinitionDTO) -> PipelineIntegrityDoctorReportDTO:
        """Perform comprehensive integrity analysis on provided pipeline definition."""
        domain_steps = [_convert_dto_to_domain_step(s) for s in pipeline_dto.steps]
        domain_pipeline = PipelineDefinition(
            pipeline_id=pipeline_dto.pipeline_id,
            name=pipeline_dto.name,
            steps=domain_steps,
            version=pipeline_dto.version,
        )

        domain_report = self._doctor.lint_pipeline(domain_pipeline)

        diagnostic_dtos = [
            HandoffGapDiagnosticDTO(
                rule_id=diag.rule_id,
                category=GapCategoryEnum(diag.category.value),
                severity=GapSeverityEnum(diag.severity.value),
                step_id=diag.step_id,
                message=diag.message,
                suggested_fix=diag.suggested_fix,
            )
            for diag in domain_report.gaps
        ]

        chain_dtos = [
            DecisionChainLinkDTO(
                step_id=link.step_id,
                from_role=link.from_role,
                to_role=link.to_role,
                stage=StepStageEnum(link.stage.value),
                reason=link.reason,
            )
            for link in domain_report.decision_chain
        ]

        report_dto = PipelineIntegrityDoctorReportDTO(
            pipeline_id=domain_report.pipeline_id,
            total_steps=domain_report.total_steps,
            is_healthy=domain_report.is_healthy,
            gaps=diagnostic_dtos,
            decision_chain=chain_dtos,
            scanned_at=domain_report.scanned_at or time.time(),
        )

        self._latest_reports[report_dto.pipeline_id] = report_dto
        return report_dto

    def auto_heal_pipeline(self, pipeline_dto: PipelineDefinitionDTO) -> PipelineDefinitionDTO:
        """Automatically synthesize remediations for detected pipeline integrity gaps."""
        domain_steps = [_convert_dto_to_domain_step(s) for s in pipeline_dto.steps]
        domain_pipeline = PipelineDefinition(
            pipeline_id=pipeline_dto.pipeline_id,
            name=pipeline_dto.name,
            steps=domain_steps,
            version=pipeline_dto.version,
        )

        healed_domain = self._doctor.auto_heal_pipeline(domain_pipeline)
        healed_steps_dto = [_convert_domain_step_to_dto(s) for s in healed_domain.steps]

        return PipelineDefinitionDTO(
            pipeline_id=healed_domain.pipeline_id,
            name=healed_domain.name,
            steps=healed_steps_dto,
            version=healed_domain.version,
        )

    def inspect_decision_chain(self, steps_dto: list[HandoffStepDTO]) -> list[DecisionChainLinkDTO]:
        """Extract a transparent, inspectable chain of delegation decisions."""
        domain_steps = [_convert_dto_to_domain_step(s) for s in steps_dto]
        domain_chain = self._doctor.inspect_decision_chain(domain_steps)

        return [
            DecisionChainLinkDTO(
                step_id=link.step_id,
                from_role=link.from_role,
                to_role=link.to_role,
                stage=StepStageEnum(link.stage.value),
                reason=link.reason,
            )
            for link in domain_chain
        ]

    def get_latest_report(self, pipeline_id: str) -> PipelineIntegrityDoctorReportDTO | None:
        """Retrieve most recent diagnostic report for a specific pipeline ID."""
        return self._latest_reports.get(pipeline_id)

    def get_sample_pipelines(self) -> dict[str, PipelineDefinitionDTO]:
        """Provide predefined sample pipelines representing healthy and gapped configurations."""
        healthy_pipeline = PipelineDefinitionDTO(
            pipeline_id="sample-healthy",
            name="Sample Fully Compliant Pipeline",
            steps=[
                HandoffStepDTO(
                    step_id="step-route",
                    stage=StepStageEnum.ROUTING,
                    agent_role="orchestrator",
                ),
                HandoffStepDTO(
                    step_id="step-code",
                    stage=StepStageEnum.EXECUTION,
                    agent_role="coder",
                    requires_verification=True,
                    metadata=HandoffMetadataDTO(
                        source_agent="orchestrator",
                        target_agent="coder",
                        transfer_reason="Execute required feature code",
                    ),
                ),
                HandoffStepDTO(
                    step_id="step-gate",
                    stage=StepStageEnum.REVIEW,
                    agent_role="reviewer",
                    requires_approval=True,
                    metadata=HandoffMetadataDTO(
                        source_agent="coder",
                        target_agent="reviewer",
                        transfer_reason="Review PR implementation",
                    ),
                ),
                HandoffStepDTO(
                    step_id="step-ship",
                    stage=StepStageEnum.DELIVERY,
                    agent_role="deployer",
                    produced_artifacts=["app_bundle_v1.tar.gz"],
                    metadata=HandoffMetadataDTO(
                        source_agent="reviewer",
                        target_agent="deployer",
                        transfer_reason="Publish release package",
                    ),
                ),
            ],
            version="1.0.0",
        )

        gapped_pipeline = PipelineDefinitionDTO(
            pipeline_id="sample-gapped",
            name="Sample Gapped Pipeline (Missing Gates & Metadata)",
            steps=[
                HandoffStepDTO(
                    step_id="step-arch",
                    stage=StepStageEnum.ANALYSIS,
                    agent_role="architect",
                ),
                HandoffStepDTO(
                    step_id="step-code",
                    stage=StepStageEnum.EXECUTION,
                    agent_role="coder",
                    # Missing handoff metadata!
                ),
                HandoffStepDTO(
                    step_id="step-ship",
                    stage=StepStageEnum.DELIVERY,
                    agent_role="deployer",
                    requires_approval=False,  # Missing approval gate!
                    requires_verification=False,  # Missing verification!
                    produced_artifacts=[],  # Missing publish artifact!
                ),
            ],
            version="0.9.0",
        )

        return {
            "healthy": healthy_pipeline,
            "gapped": gapped_pipeline,
        }
