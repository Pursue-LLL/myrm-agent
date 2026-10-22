"""[INPUT] BindWorkspaceBlueprintRequest, workspace identifiers, and session requests.
[OUTPUT] WorkspaceBlueprintService managing workspace-to-blueprint bindings and auto-reuse resolution.
[POS] Service layer for Per-Project Workspace Team Blueprint Auto-Reuse (Item 36).
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.coordination.workspace_blueprint import (
    AutoReusePolicy,
    WorkspaceBlueprintBinding,
    WorkspaceBlueprintResolution,
    WorkspaceBlueprintStore,
)

from app.schemas.workspace_blueprint import (
    AutoReusePolicyEnum,
    BindWorkspaceBlueprintRequest,
    WorkspaceBlueprintBindingDTO,
    WorkspaceBlueprintListResponse,
    WorkspaceBlueprintResolutionDTO,
)

logger = logging.getLogger(__name__)


def _to_binding_dto(b: WorkspaceBlueprintBinding) -> WorkspaceBlueprintBindingDTO:
    return WorkspaceBlueprintBindingDTO(
        workspace_id=b.workspace_id,
        blueprint_id=b.blueprint_id,
        team_name=b.team_name,
        auto_reuse_policy=AutoReusePolicyEnum(b.auto_reuse_policy.value),
        bound_at=b.bound_at,
        last_used_at=b.last_used_at,
        member_count=b.member_count,
        total_budget_tokens=b.total_budget_tokens,
        project_label=b.project_label,
        blueprint_snapshot=dict(b.blueprint_snapshot),
    )


def _to_resolution_dto(r: WorkspaceBlueprintResolution) -> WorkspaceBlueprintResolutionDTO:
    return WorkspaceBlueprintResolutionDTO(
        workspace_id=r.workspace_id,
        binding=_to_binding_dto(r.binding) if r.binding else None,
        can_auto_instantiate=r.can_auto_instantiate,
        status_label=r.status_label,
        resolution_rationale=r.resolution_rationale,
    )


class WorkspaceBlueprintService:
    """Service governing workspace team template binding, auto-reuse, and resolution."""

    def __init__(self, store: WorkspaceBlueprintStore | None = None) -> None:
        self._store = store or WorkspaceBlueprintStore()

    def bind_blueprint(
        self,
        workspace_id: str,
        req: BindWorkspaceBlueprintRequest,
    ) -> WorkspaceBlueprintBindingDTO:
        """Bind or update a team blueprint for a workspace."""
        binding = self._store.bind_blueprint(
            workspace_id=workspace_id,
            blueprint_id=req.blueprint_id,
            team_name=req.team_name,
            auto_reuse_policy=AutoReusePolicy(req.auto_reuse_policy.value),
            member_count=req.member_count,
            total_budget_tokens=req.total_budget_tokens,
            project_label=req.project_label,
            blueprint_snapshot=req.blueprint_snapshot,
        )
        return _to_binding_dto(binding)

    def resolve_blueprint(self, workspace_id: str) -> WorkspaceBlueprintResolutionDTO:
        """Resolve active blueprint disposition for a project workspace."""
        res = self._store.resolve_blueprint(workspace_id)
        return _to_resolution_dto(res)

    def record_usage(self, workspace_id: str) -> bool:
        """Mark workspace blueprint as recently instantiated or used."""
        return self._store.record_usage(workspace_id)

    def unbind_blueprint(self, workspace_id: str) -> bool:
        """Unbind team blueprint from workspace."""
        return self._store.unbind_blueprint(workspace_id)

    def get_binding(self, workspace_id: str) -> WorkspaceBlueprintBindingDTO | None:
        """Fetch active binding for a workspace."""
        binding = self._store.get_binding(workspace_id)
        return _to_binding_dto(binding) if binding else None

    def list_bindings(self) -> WorkspaceBlueprintListResponse:
        """List all active workspace bindings."""
        bindings = self._store.list_bindings()
        dtos = [_to_binding_dto(b) for b in bindings]
        return WorkspaceBlueprintListResponse(
            bindings=dtos,
            total_count=len(dtos),
        )

    def clear(self) -> None:
        """Purge all workspace bindings."""
        self._store.clear()


_global_store = WorkspaceBlueprintStore()
_global_service = WorkspaceBlueprintService(_global_store)


def get_workspace_blueprint_service() -> WorkspaceBlueprintService:
    """FastAPI dependency provider for WorkspaceBlueprintService."""
    return _global_service
