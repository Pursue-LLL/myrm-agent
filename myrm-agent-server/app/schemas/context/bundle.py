"""Context bundle API schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContextBundleSceneHealth(BaseModel):
    scene: str
    path: str
    index_status: Literal["ready", "degraded", "missing"] = "missing"


class ContextBundleHealthResponse(BaseModel):
    bundle_id: str
    schema_version: int
    volume_layout_version: int
    state_dir: str
    memory_base_path: str
    harness_dir: str
    writable: bool
    manifest_exists: bool
    deploy_mode: str
    storage_mode: str
    scenes: list[ContextBundleSceneHealth] = Field(default_factory=list)
    migration_actions_pending: int = 0
    warnings: list[str] = Field(default_factory=list)


class ContextBundleMigrationResponse(BaseModel):
    ok: bool
    bundle_id: str
    schema_version: int
    writable: bool
    manifest_exists: bool
    actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
