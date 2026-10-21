"""Service layer for Clean-Code Assembly Pipeline and Architecture Dependency Linter (Item 62).

[INPUT]
- CleanCodeAssemblyPipelineEngine and ArchitectureDependencyLinter from harness.
- Requests from clean_code_pipeline schemas.

[OUTPUT]
- CleanCodeTaskDTO, StageArtifactDTO, ArchitectureViolationDTO, LinterResultDTO.

[POS]
- Bridge between FastAPI clean_code_pipeline router and underlying harness engine.
"""

from __future__ import annotations

import threading
import uuid
from typing import ClassVar

from myrm_agent_harness.agent.sub_agents.clean_code_pipeline import (
    ArchitectureDependencyLinter,
    ArchitectureViolation,
    CleanCodeAssemblyPipelineEngine,
    CleanCodeTask,
    DependencyRule,
    LinterResult,
    StageArtifact,
)

from app.schemas.clean_code_pipeline import (
    AdvanceStageRequest,
    ArchitectureViolationDTO,
    CleanCodeTaskDTO,
    CreateCleanCodeTaskRequest,
    DependencyRuleDTO,
    LinterCheckRequest,
    LinterResultDTO,
    PipelineStageDTOEnum,
    StageArtifactDTO,
    StageStatusDTOEnum,
    ViolationTypeDTOEnum,
)


class CleanCodePipelineService:
    """Thread-safe orchestration service for Clean-Code assembly pipelines."""

    _engine: ClassVar[CleanCodeAssemblyPipelineEngine] = CleanCodeAssemblyPipelineEngine()
    _task_session_map: ClassVar[dict[str, str]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def _to_rule(cls, dto: DependencyRuleDTO) -> DependencyRule:
        return DependencyRule(
            source_layer=dto.source_layer,
            allowed_target_layers=dto.allowed_target_layers,
        )

    @classmethod
    def _to_violation_dto(cls, v: ArchitectureViolation) -> ArchitectureViolationDTO:
        return ArchitectureViolationDTO(
            source_module=v.source_module,
            target_module=v.target_module,
            violation_type=ViolationTypeDTOEnum(v.violation_type.value),
            rule_description=v.rule_description,
            remediation_suggestion=v.remediation_suggestion,
        )

    @classmethod
    def _to_artifact_dto(cls, a: StageArtifact) -> StageArtifactDTO:
        return StageArtifactDTO(
            stage=PipelineStageDTOEnum(a.stage.value),
            title=a.title,
            content=a.content,
            metadata=dict(a.metadata),
        )

    @classmethod
    def _to_task_dto(cls, task: CleanCodeTask) -> CleanCodeTaskDTO:
        session_id = cls._task_session_map.get(task.task_id, "default")
        artifacts_dto = {
            k: cls._to_artifact_dto(v) for k, v in task.artifacts.items()
        }
        return CleanCodeTaskDTO(
            task_id=task.task_id,
            session_id=session_id,
            title=task.title,
            spec_prompt=task.spec_prompt,
            current_stage=PipelineStageDTOEnum(task.current_stage.value),
            status=StageStatusDTOEnum(task.status.value),
            artifacts=artifacts_dto,
            stage_history=list(task.stage_history),
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @classmethod
    def create_task(cls, req: CreateCleanCodeTaskRequest) -> CleanCodeTaskDTO:
        """Create and start a new Clean-Code assembly pipeline."""
        task_id = req.task_id or f"clean-task-{uuid.uuid4().hex[:8]}"
        with cls._lock:
            cls._task_session_map[task_id] = req.session_id
            task = cls._engine.start_pipeline(
                task_id=task_id,
                title=req.title,
                spec_prompt=req.spec_prompt,
            )
        return cls._to_task_dto(task)

    @classmethod
    def advance_stage(cls, task_id: str, req: AdvanceStageRequest) -> CleanCodeTaskDTO:
        """Advance the pipeline to the next stage with deliverable and optional source code check."""
        with cls._lock:
            task = cls._engine.get_task(task_id)
            if not task:
                msg = f"Clean-code task '{task_id}' not found."
                raise KeyError(msg)

            # If source code is provided, run architecture linting gate
            if req.source_code_map:
                lint_res = cls._engine.lint_and_gate_check(task_id, req.source_code_map)
                if not lint_res.is_valid:
                    # Task is now BLOCKED by engine
                    return cls._to_task_dto(task)

            # Advance stage
            updated_task = cls._engine.advance_stage(
                task_id=task_id,
                artifact_title=req.artifact_title,
                artifact_content=req.artifact_content,
                metadata=req.metadata,
            )
        return cls._to_task_dto(updated_task)

    @classmethod
    def get_task(cls, task_id: str) -> CleanCodeTaskDTO:
        """Retrieve task state by task_id."""
        with cls._lock:
            task = cls._engine.get_task(task_id)
        if not task:
            msg = f"Clean-code task '{task_id}' not found."
            raise KeyError(msg)
        return cls._to_task_dto(task)

    @classmethod
    def list_tasks(cls, session_id: str | None = None) -> list[CleanCodeTaskDTO]:
        """List tasks optionally filtered by session_id."""
        with cls._lock:
            tasks = cls._engine.list_tasks()
        result: list[CleanCodeTaskDTO] = []
        for t in tasks:
            t_session = cls._task_session_map.get(t.task_id, "default")
            if session_id is None or t_session == session_id:
                result.append(cls._to_task_dto(t))
        return result

    @classmethod
    def run_linter(cls, req: LinterCheckRequest) -> LinterResultDTO:
        """Ad-hoc static AST architecture analysis on source code map."""
        rules = [cls._to_rule(r) for r in req.custom_rules] if req.custom_rules else None
        linter = ArchitectureDependencyLinter(rules=rules)
        res: LinterResult = linter.lint_project_modules(req.source_code_map)
        return LinterResultDTO(
            is_valid=res.is_valid,
            violations=[cls._to_violation_dto(v) for v in res.violations],
            scanned_files_count=res.scanned_files_count,
            dependency_edges=[[u, v] for u, v in res.dependency_edges],
        )

    @classmethod
    def clear(cls) -> None:
        """Reset service in-memory state (useful in test teardown)."""
        with cls._lock:
            cls._engine.clear()
            cls._task_session_map.clear()
