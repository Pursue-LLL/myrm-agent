"""Business service coordinating L3 World Model macro context querying and workspace syncing.

[POS]
app/services/memory/world_model/service.py
Integrates Harness L3WorldModelEngine with workspace environment probes to deliver
one-stop macro context assembly for LLM System Prompt injection.

[INPUT]
- app.schemas.world_model: (RuntimeInfoDTO, WorldModelFieldsDTO, WorldModelQueryRequest, ...)
- app.services.memory.world_model.probe: ProjectEnvironmentProbe
- myrm_agent_harness.toolkits.memory: (L3WorldModelEngine, L3WorldModelField)

[OUTPUT]
- L3WorldModelService: Singleton business service managing L3 World Model lifecycles.
- get_world_model_service: Factory provider function.
"""

from __future__ import annotations

import time

from myrm_agent_harness.toolkits.memory import (
    L3WorldModelEngine,
    L3WorldModelField,
)

from app.schemas.world_model import (
    RuntimeInfoDTO,
    WorldModelFieldsDTO,
    WorldModelQueryRequest,
    WorldModelQueryResponse,
    WorldModelSyncRequest,
    WorldModelSyncResponse,
    WorldModelUpdateRequest,
    WorldModelUpdateResponse,
)
from app.services.memory.world_model.probe import ProjectEnvironmentProbe


class L3WorldModelService:
    """Service managing project world model state and macro prompt injection contexts."""

    def __init__(self) -> None:
        self._engine = L3WorldModelEngine()

    def query_macro_context(
        self,
        request: WorldModelQueryRequest,
    ) -> WorldModelQueryResponse:
        """Fetch or assemble the complete L3 macro context for a project scope."""
        project_id = request.project_id.strip() or "default"

        # If a workspace path was provided, probe and auto-sync if not synced yet
        if request.workspace_root:
            snapshot = ProjectEnvironmentProbe.probe_workspace(request.workspace_root)
            self._engine.merge_environment_snapshot(
                project_id=project_id,
                snapshot=snapshot,
                source_ref=f"workspace:{request.workspace_root}",
            )

        payload = self._engine.render_macro_context(project_id)
        return WorldModelQueryResponse(
            project_id=payload.project_id,
            version=payload.version,
            rendered_markdown=payload.rendered_markdown,
            field_breakdown=payload.field_breakdown,
            token_estimate=payload.token_estimate,
            has_active_constraints=payload.has_active_constraints,
        )

    def sync_workspace_environment(
        self,
        request: WorldModelSyncRequest,
    ) -> WorldModelSyncResponse:
        """Trigger environment probe on workspace root and sync into world model."""
        project_id = request.project_id.strip() or "default"
        snapshot = ProjectEnvironmentProbe.probe_workspace(request.workspace_root)
        record = self._engine.merge_environment_snapshot(
            project_id=project_id,
            snapshot=snapshot,
            source_ref=f"workspace_sync:{request.workspace_root}",
        )

        detected_dtos = [
            RuntimeInfoDTO(
                name=r.name,
                version=r.version,
                package_manager=r.package_manager,
                key_dependencies=r.key_dependencies,
            )
            for r in snapshot.runtimes
        ]

        return WorldModelSyncResponse(
            project_id=record.project_id,
            version=record.version,
            detected_runtimes=detected_dtos,
            config_markers=snapshot.config_markers,
            synced_at=time.time(),
        )

    def update_dimension(
        self,
        request: WorldModelUpdateRequest,
    ) -> WorldModelUpdateResponse:
        """Directly update a single dimension of the L3 World Model."""
        project_id = request.project_id.strip() or "default"
        field_enum = L3WorldModelField(request.field_name)

        record = self._engine.update_dimension(
            project_id=project_id,
            field_name=field_enum,
            content=request.content,
            source_ref=request.source_ref,
        )

        return WorldModelUpdateResponse(
            project_id=record.project_id,
            version=record.version,
            field_name=request.field_name,
            updated_at=record.updated_at,
        )

    def get_fields(self, project_id: str) -> WorldModelFieldsDTO:
        """Fetch raw fields of a project's L3 World Model."""
        clean_id = project_id.strip() or "default"
        record = self._engine.get_or_create_record(clean_id)
        return WorldModelFieldsDTO(
            general_rules=record.general_rules,
            project_environment=record.project_environment,
            project_contract=record.project_contract,
            domain_knowledge=record.domain_knowledge,
        )


_service_instance: L3WorldModelService | None = None


def get_world_model_service() -> L3WorldModelService:
    """Singleton provider for L3WorldModelService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = L3WorldModelService()
    return _service_instance
