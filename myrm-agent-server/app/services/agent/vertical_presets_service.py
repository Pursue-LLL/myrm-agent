"""Service layer for Five Vertical Role Persona Presets and Sub-Bot Sandbox Tester (Item 64).

[INPUT]
- RegisterPresetRequest, SubBotTestRequestDTO, RecordA2AStepRequest schemas.
- PresetsCatalog, SubBotSandboxTester, A2AFlowInspector from harness.

[OUTPUT]
- VerticalRolePresetDTO, SubBotTestResultDTO, A2AFlowTraceDTO.

[POS]
- Bridge between FastAPI vertical presets router and underlying harness sandbox and presets catalog.
"""

from __future__ import annotations

import threading
from typing import ClassVar

from myrm_agent_harness.agent.sub_agents.vertical_presets import (
    A2AFlowInspector,
    A2AFlowStep,
    A2AFlowTrace,
    PresetsCatalog,
    ReasoningEffort,
    SubBotSandboxTester,
    SubBotTestRequest,
    SubBotTestResult,
    VerticalRoleCategory,
    VerticalRolePreset,
)

from app.schemas.vertical_presets import (
    A2AFlowStepDTO,
    A2AFlowTraceDTO,
    ReasoningEffortDTOEnum,
    RegisterPresetRequest,
    SubBotTestRequestDTO,
    SubBotTestResultDTO,
    VerticalRoleCategoryDTOEnum,
    VerticalRolePresetDTO,
)


class VerticalPresetsService:
    """Thread-safe orchestration service managing vertical presets, sandbox runs, and A2A telemetry."""

    _catalog: ClassVar[PresetsCatalog] = PresetsCatalog()
    _tester: ClassVar[SubBotSandboxTester] = SubBotSandboxTester(catalog=_catalog)
    _inspector: ClassVar[A2AFlowInspector] = A2AFlowInspector()
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def _to_preset_dto(cls, p: VerticalRolePreset) -> VerticalRolePresetDTO:
        return VerticalRolePresetDTO(
            role_id=p.role_id,
            category=VerticalRoleCategoryDTOEnum(p.category.value),
            display_name=p.display_name,
            description=p.description,
            persona_prompt=p.persona_prompt,
            recommended_skills=list(p.recommended_skills),
            recommended_tools=list(p.recommended_tools),
            reasoning_effort=ReasoningEffortDTOEnum(p.reasoning_effort.value),
            typical_tasks=list(p.typical_tasks),
        )

    @classmethod
    def _to_result_dto(cls, r: SubBotTestResult) -> SubBotTestResultDTO:
        return SubBotTestResultDTO(
            test_id=r.test_id,
            role_id=r.role_id,
            success=r.success,
            output_text=r.output_text,
            tool_calls_made=list(r.tool_calls_made),
            execution_time_ms=r.execution_time_ms,
            logs=list(r.logs),
            error_message=r.error_message,
        )

    @classmethod
    def _to_step_dto(cls, s: A2AFlowStep) -> A2AFlowStepDTO:
        return A2AFlowStepDTO(
            step_id=s.step_id,
            source_agent_id=s.source_agent_id,
            target_agent_id=s.target_agent_id,
            action=s.action,
            payload_summary=s.payload_summary,
            result_summary=s.result_summary,
            duration_ms=s.duration_ms,
            timestamp=s.timestamp,
        )

    @classmethod
    def _to_trace_dto(cls, t: A2AFlowTrace) -> A2AFlowTraceDTO:
        return A2AFlowTraceDTO(
            trace_id=t.trace_id,
            session_id=t.session_id,
            root_agent_id=t.root_agent_id,
            steps=[cls._to_step_dto(s) for s in t.steps],
            total_duration_ms=t.total_duration_ms,
            is_loop_detected=t.is_loop_detected,
        )

    @classmethod
    def list_presets(
        cls,
        category: VerticalRoleCategoryDTOEnum | None = None,
    ) -> list[VerticalRolePresetDTO]:
        """List presets, optionally filtered by category."""
        with cls._lock:
            cat_filter = VerticalRoleCategory(category.value) if category else None
            presets = cls._catalog.list_presets(category=cat_filter)
            return [cls._to_preset_dto(p) for p in presets]

    @classmethod
    def get_preset(cls, role_id: str) -> VerticalRolePresetDTO | None:
        """Fetch a specific vertical preset by role ID."""
        with cls._lock:
            preset = cls._catalog.get_preset(role_id)
            if preset is None:
                return None
            return cls._to_preset_dto(preset)

    @classmethod
    def register_preset(cls, req: RegisterPresetRequest) -> VerticalRolePresetDTO:
        """Register or update a preset in the catalog."""
        with cls._lock:
            preset = VerticalRolePreset(
                role_id=req.role_id,
                category=VerticalRoleCategory(req.category.value),
                display_name=req.display_name,
                description=req.description,
                persona_prompt=req.persona_prompt,
                recommended_skills=list(req.recommended_skills),
                recommended_tools=list(req.recommended_tools),
                reasoning_effort=ReasoningEffort(req.reasoning_effort.value),
                typical_tasks=list(req.typical_tasks),
            )
            cls._catalog.register_preset(preset)
            return cls._to_preset_dto(preset)

    @classmethod
    def run_sandbox_test(cls, req: SubBotTestRequestDTO) -> SubBotTestResultDTO:
        """Execute an isolated sandbox test for a specific specialist bot."""
        with cls._lock:
            request_model = SubBotTestRequest(
                role_id=req.role_id,
                test_prompt=req.test_prompt,
                mock_inputs=dict(req.mock_inputs),
                timeout_seconds=req.timeout_seconds,
            )
            result = cls._tester.run_test(request_model)
            return cls._to_result_dto(result)

    @classmethod
    def record_a2a_step(
        cls,
        session_id: str,
        root_agent_id: str,
        step_dto: A2AFlowStepDTO,
    ) -> A2AFlowTraceDTO:
        """Append an A2A communication step and return updated trace telemetry."""
        with cls._lock:
            step = A2AFlowStep(
                step_id=step_dto.step_id,
                source_agent_id=step_dto.source_agent_id,
                target_agent_id=step_dto.target_agent_id,
                action=step_dto.action,
                payload_summary=step_dto.payload_summary,
                result_summary=step_dto.result_summary,
                duration_ms=step_dto.duration_ms,
                timestamp=step_dto.timestamp,
            )
            trace = cls._inspector.record_step(session_id, root_agent_id, step)
            return cls._to_trace_dto(trace)

    @classmethod
    def get_a2a_trace(cls, session_id: str) -> A2AFlowTraceDTO | None:
        """Retrieve the A2A communication trace for a session."""
        with cls._lock:
            trace = cls._inspector.get_trace(session_id)
            if trace is None:
                return None
            return cls._to_trace_dto(trace)

    @classmethod
    def list_a2a_traces(cls) -> list[A2AFlowTraceDTO]:
        """List all tracked A2A execution traces."""
        with cls._lock:
            traces = cls._inspector.list_traces()
            return [cls._to_trace_dto(t) for t in traces]

    @classmethod
    def clear(cls) -> None:
        """Reset presets to baseline and clear A2A traces (used for isolated testing)."""
        with cls._lock:
            cls._catalog.reset_to_defaults()
            cls._inspector.clear()
