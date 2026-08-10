"""Agent Plugins 1.0.0 import API.

[INPUT]
- app.services.plugins.import_service::parse_plugin_zip, build_preview_result, confirm_plugin_import (POS: plugin import orchestration)
- myrm_agent_harness.agent.plugins::AgentPluginParser (POS: framework-level parser)

[OUTPUT]
- POST /plugins/import/preview — parse + preview components
- POST /plugins/import/confirm — persist selected components + bind agent

[POS]
Business HTTP layer for Agent Plugins import. GUI-First: preview shows the plugin
card, skills and MCP servers with diagnostics; confirm writes to SkillStore /
mcpServers UserConfig / Agent profile.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.skills.store.evolution_store import (
    get_evolution_skill_store_db_path,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["plugins-import"])

MAX_PLUGIN_ZIP_BYTES = 20 * 1024 * 1024  # 20 MB upload cap


class PluginMetaResponse(BaseModel):
    name: str
    version: str | None = None
    description: str | None = None
    author: dict[str, str] | None = None
    homepage: str | None = None
    repository: str | None = None
    license: str | None = None
    keywords: list[str] = Field(default_factory=list)


class PluginSkillPreview(BaseModel):
    name: str
    description: str
    file_count: int
    virtual_id: str
    security_issues: list[str] = Field(default_factory=list)
    oversized_content: bool = False


class PluginServerPreview(BaseModel):
    name: str
    type: str
    command: str | None = None
    url: str | None = None
    env_key_count: int = 0
    has_placeholders: bool = False
    virtual_id: str


class PluginDiagnosticResponse(BaseModel):
    component: str
    code: str
    message: str
    level: str


class PluginImportPreviewResponse(BaseModel):
    session_id: str
    plugin: PluginMetaResponse
    skills: list[PluginSkillPreview]
    servers: list[PluginServerPreview]
    diagnostics: list[PluginDiagnosticResponse]
    is_valid: bool


class PluginConfirmComponent(BaseModel):
    component: str  # "plugin" | "skill" | "mcp"
    virtual_id: str
    name: str
    resolution: Literal["install", "skip"]


class PluginImportConfirmRequest(BaseModel):
    session_id: str
    skills: list[PluginConfirmComponent]
    servers: list[PluginConfirmComponent]
    bind_agent_id: str | None = Field(
        default=None, description="Agent ID to bind MCP servers to"
    )


class PluginImportConfirmResponse(BaseModel):
    imported_skills: int
    skipped_skills: int
    imported_servers: int
    skipped_servers: int


@router.post("/preview", response_model=PluginImportPreviewResponse)
async def preview_plugin_import(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> PluginImportPreviewResponse:
    """Receive a plugin ZIP and return a component-level preview with diagnostics."""
    from app.services.plugins.import_service import (
        PluginArchiveSecurityError,
        PluginImportSession,
        PluginStaging,
        build_preview_result,
        parse_plugin_zip,
    )

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="A .zip file is required")

    zip_bytes = await file.read(MAX_PLUGIN_ZIP_BYTES + 1)
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(zip_bytes) > MAX_PLUGIN_ZIP_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Upload blocked: file exceeds the 20 MB limit.",
        )

    try:
        result = parse_plugin_zip(zip_bytes)
    except PluginArchiveSecurityError as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc), "error_code": exc.error_code},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_id = uuid.uuid4().hex
    # virtual_id keys must match build_preview_result (skill:<idx> / mcp:<idx>).
    skills_by_key = {f"skill:{idx}": skill for idx, skill in enumerate(result.skills)}
    servers_by_key = {f"mcp:{idx}": server for idx, server in enumerate(result.servers)}

    store = get_evolution_skill_store_db_path()
    staging = PluginStaging(store.parent)
    staging.save_session(
        session_id,
        PluginImportSession(
            plugin_result=result,
            skills_by_key=skills_by_key,
            servers_by_key=servers_by_key,
        ),
    )
    background_tasks.add_task(staging.cleanup_expired_sessions)

    preview = build_preview_result(result)
    return PluginImportPreviewResponse(
        session_id=session_id,
        plugin=PluginMetaResponse(**preview["plugin"]),
        skills=[PluginSkillPreview(**item) for item in preview["skills"]],
        servers=[PluginServerPreview(**item) for item in preview["servers"]],
        diagnostics=[
            PluginDiagnosticResponse(**item) for item in preview["diagnostics"]
        ],
        is_valid=preview["is_valid"],
    )


@router.post("/confirm", response_model=PluginImportConfirmResponse)
async def confirm_plugin_import(
    request: PluginImportConfirmRequest,
    background_tasks: BackgroundTasks,
) -> PluginImportConfirmResponse:
    """Confirm import decisions and persist skills + MCP servers."""
    from app.services.plugins.import_service import (
        PluginConfirmItem,
        PluginStaging,
        confirm_plugin_import,
    )

    store = get_evolution_skill_store_db_path()
    staging = PluginStaging(store.parent)

    try:
        session = staging.load_session(request.session_id)
    except Exception as exc:
        logger.error("Plugin import confirm failed to load session: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Import session is invalid or expired.",
        ) from exc

    skill_decisions = [
        PluginConfirmItem(
            component=item.component,
            virtual_id=item.virtual_id,
            resolution=item.resolution,
            name=item.name,
        )
        for item in request.skills
    ]
    server_decisions = [
        PluginConfirmItem(
            component=item.component,
            virtual_id=item.virtual_id,
            resolution=item.resolution,
            name=item.name,
        )
        for item in request.servers
    ]

    try:
        result = await confirm_plugin_import(
            session,
            skill_decisions=skill_decisions,
            server_decisions=server_decisions,
            bind_agent_id=request.bind_agent_id,
        )
    except Exception as exc:
        logger.error("Plugin import confirm failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Plugin import failed. Please retry.",
        ) from exc
    finally:
        staging.cleanup_session(request.session_id)
        background_tasks.add_task(staging.cleanup_expired_sessions)

    return PluginImportConfirmResponse(**result)
