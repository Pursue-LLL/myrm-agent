"""Service mediating coding agent wave pipeline progression and strict stage gates (Item 45).

[INPUT]
- CreateWaveSessionRequest, UpdateWaveTaskRequest.

[OUTPUT]
- CodingWaveService orchestrating multi-wave development cycles, role routing,
  and progress artifact serialization.

[POS]
- Service layer for optional Coding Agent Wave Preset Pipeline.
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.coordination.wave_orchestrator import (
    CodingAgentWaveEngine,
    WaveExecutionProgress,
    WavePresetConfig,
    WaveTaskNode,
    WaveTaskStatusEnum,
)

from app.schemas.coding_wave import (
    WaveExecutionProgressDTO,
    WavePresetConfigDTO,
    WaveTaskNodeDTO,
)

logger = logging.getLogger(__name__)


def _node_to_dto(node: WaveTaskNode) -> WaveTaskNodeDTO:
    return WaveTaskNodeDTO(
        task_id=node.task_id,
        stage=node.stage,
        title=node.title,
        role=node.role,
        model_override=node.model_override,
        status=node.status,
        output_summary=node.output_summary,
    )


def _node_from_dto(dto: WaveTaskNodeDTO) -> WaveTaskNode:
    return WaveTaskNode(
        task_id=dto.task_id,
        stage=dto.stage,
        title=dto.title,
        role=dto.role,
        model_override=dto.model_override,
        status=dto.status,
        output_summary=dto.output_summary,
    )


def _progress_to_dto(prog: WaveExecutionProgress) -> WaveExecutionProgressDTO:
    return WaveExecutionProgressDTO(
        session_id=prog.session_id,
        current_stage=prog.current_stage,
        tasks=[_node_to_dto(t) for t in prog.tasks],
        is_completed=prog.is_completed,
        updated_at=prog.updated_at,
    )


def _preset_from_dto(dto: WavePresetConfigDTO | None) -> WavePresetConfig | None:
    if dto is None:
        return None
    return WavePresetConfig(
        preset_id=dto.preset_id,
        name=dto.name,
        description=dto.description,
        role_model_routing=dict(dto.role_model_routing),
    )


class CodingWaveService:
    """Thread-safe application service coordinating coding agent wave cycles."""

    def __init__(self) -> None:
        self._engine = CodingAgentWaveEngine()
        self._default_preset = WavePresetConfig()
        self._lock = threading.Lock()

    def create_wave_session(
        self,
        session_id: str,
        preset_dto: WavePresetConfigDTO | None = None,
        custom_tasks_dto: list[WaveTaskNodeDTO] | None = None,
    ) -> WaveExecutionProgressDTO:
        with self._lock:
            domain_preset = _preset_from_dto(preset_dto)
            domain_tasks = (
                [_node_from_dto(t) for t in custom_tasks_dto]
                if custom_tasks_dto is not None
                else None
            )
            progress = self._engine.create_wave_session(
                session_id=session_id,
                preset=domain_preset,
                custom_tasks=domain_tasks,
            )
            return _progress_to_dto(progress)

    def get_progress(self, session_id: str) -> WaveExecutionProgressDTO | None:
        with self._lock:
            progress = self._engine.get_progress(session_id)
            if progress is None:
                return None
            return _progress_to_dto(progress)

    def update_task_status(
        self,
        session_id: str,
        task_id: str,
        status: WaveTaskStatusEnum,
        output_summary: str | None = None,
    ) -> WaveTaskNodeDTO:
        with self._lock:
            node = self._engine.update_task_status(
                session_id=session_id,
                task_id=task_id,
                status=status,
                output_summary=output_summary,
            )
            return _node_to_dto(node)

    def advance_stage(self, session_id: str) -> WaveExecutionProgressDTO:
        with self._lock:
            progress = self._engine.advance_stage(session_id)
            return _progress_to_dto(progress)

    def export_progress_json(self, session_id: str) -> str:
        with self._lock:
            return self._engine.export_progress_json(session_id)

    def get_default_preset(self) -> WavePresetConfigDTO:
        with self._lock:
            p = self._default_preset
            return WavePresetConfigDTO(
                preset_id=p.preset_id,
                name=p.name,
                description=p.description,
                role_model_routing=dict(p.role_model_routing),
            )


_global_coding_wave_service = CodingWaveService()


def get_coding_wave_service() -> CodingWaveService:
    """Retrieve global singleton CodingWaveService instance."""
    return _global_coding_wave_service
