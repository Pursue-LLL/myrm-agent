"""Agent Plugins 1.0.0 import API.

[INPUT]
- app.services.plugins.import_service::parse_plugin_zip, build_preview_result,
  load_preview_context, confirm_plugin_import, list_installed_plugins,
  uninstall_plugin (POS: plugin import orchestration)
- myrm_agent_harness.agent.plugins.rules::MAX_PLUGIN_ZIP_BYTES (POS: upload ceiling shared
  with the exporter)

[OUTPUT]
- POST /plugins/import/preview — parse + preview components (conflict, deployment-block
  and unresolved-reference flags, what each expert would be granted)
- POST /plugins/import/confirm — persist selected components (``replace`` overwrites a
  same-name skill or the user's own expert) + bind agent; reports per-component failures
- GET /plugins/import/installed — provenance-grouped list of imported plugins
- DELETE /plugins/import/{plugin_name} — uninstall a plugin (MCP entries +
  agent bindings + bundled files)

[POS]
Business HTTP layer for Agent Plugins import. GUI-First: preview shows the plugin
card, skills (with security / oversized / name-conflict / deployment-block markers),
MCP servers and experts with diagnostics; confirm installs skills, writes the
mcpServers UserConfig and creates or updates expert profiles.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from myrm_agent_harness.agent.plugins.rules import MAX_PLUGIN_ZIP_BYTES
from pydantic import BaseModel, Field

from app.core.skills.store.evolution_store import (
    get_evolution_skill_store_db_path,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["plugins-import"])


class CapabilityDiffResponse(BaseModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    has_escalation: bool = False


class PluginMetaResponse(BaseModel):
    name: str
    version: str | None = None
    description: str | None = None
    author: dict[str, str] | None = None
    homepage: str | None = None
    repository: str | None = None
    license: str | None = None
    keywords: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    effective_tier: str = "read_only"
    risk_level: str = "low"
    capability_diff: CapabilityDiffResponse | None = None


class PluginSkillPreview(BaseModel):
    name: str
    description: str
    file_count: int
    virtual_id: str
    security_issues: list[str] = Field(default_factory=list)
    oversized_content: bool = False
    blocked_reason: str | None = Field(default=None, description="Why this deployment cannot install the skill")
    conflict: bool = False


class PluginServerPreview(BaseModel):
    name: str
    type: str
    command: str | None = None
    url: str | None = None
    env_key_count: int = 0
    has_placeholders: bool = False
    virtual_id: str
    missing_artifact: str | None = None
    is_runnable: bool = True
    missing_artifacts: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    blocked_reason: str | None = Field(default=None, description="Why this deployment cannot use the connector")


class PluginAgentPreview(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    max_iterations: int | None = None
    effective_max_iterations: int | None = Field(default=None, description="Loop budget after import limits")
    skill_names: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    granted_tools: list[str] = Field(default_factory=list, description="Requested tools that will be enabled")
    withheld_tools: list[str] = Field(default_factory=list, description="Requested tools left for the user to enable")
    mcp_names: list[str] = Field(default_factory=list)
    subagent_names: list[str] = Field(default_factory=list)
    is_subagent: bool = False
    is_entry_agent: bool = False
    virtual_id: str
    conflict: bool = Field(default=False, description="An expert with the same name already exists")
    existing_agent_id: str | None = None
    existing_is_built_in: bool = False
    unresolved_skills: list[str] = Field(default_factory=list)
    unresolved_connectors: list[str] = Field(default_factory=list)
    unresolved_subagents: list[str] = Field(default_factory=list)


class PluginDiagnosticResponse(BaseModel):
    component: str
    code: str
    message: str
    level: str


class PluginDeploymentFlags(BaseModel):
    allows_local_skills: bool = True
    allow_stdio: bool = True


class PluginImportPreviewResponse(BaseModel):
    session_id: str
    plugin: PluginMetaResponse
    skills: list[PluginSkillPreview]
    servers: list[PluginServerPreview]
    agents: list[PluginAgentPreview] = Field(default_factory=list)
    workspace_file_count: int = 0
    deployment: PluginDeploymentFlags = Field(default_factory=lambda: PluginDeploymentFlags())
    diagnostics: list[PluginDiagnosticResponse]
    is_valid: bool


class PluginConfirmComponent(BaseModel):
    component: str  # "plugin" | "skill" | "mcp" | "agent"
    virtual_id: str
    name: str
    resolution: Literal["install", "replace", "skip"]


class PluginImportConfirmRequest(BaseModel):
    session_id: str
    skills: list[PluginConfirmComponent]
    servers: list[PluginConfirmComponent]
    agents: list[PluginConfirmComponent] = Field(default_factory=list)
    bind_agent_id: str | None = Field(default=None, description="Agent ID to bind MCP servers to")


class PluginComponentFailure(BaseModel):
    component: Literal["skill", "mcp", "agent"]
    name: str
    code: str = Field(description="Machine-readable reason, localized by the client")
    message: str


class PluginAgentResult(BaseModel):
    agent_id: str
    package_name: str
    stored_name: str
    action: Literal["created", "replaced"]
    previous_version_saved: bool = False
    withheld_tools: list[str] = Field(default_factory=list)
    unresolved_skills: list[str] = Field(default_factory=list)
    unresolved_connectors: list[str] = Field(default_factory=list)
    unresolved_subagents: list[str] = Field(default_factory=list)


class PluginImportConfirmResponse(BaseModel):
    imported_skills: int
    skipped_skills: int
    imported_servers: int
    skipped_servers: int
    imported_agents: int = 0
    skipped_agents: int = 0
    required_secret_keys: list[str] = Field(
        default_factory=list,
        description="Secret keys the imported MCP servers depend on (Scoped Secret Injection)",
    )
    created_agent_ids: list[str] = Field(
        default_factory=list,
        description="IDs of created or replaced Agent profiles",
    )
    agents: list[PluginAgentResult] = Field(default_factory=list)
    failures: list[PluginComponentFailure] = Field(
        default_factory=list,
        description="Selected components that could not be imported (nothing half-written is left behind)",
    )


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
        list_installed_plugins,
        load_preview_context,
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
        result = await asyncio.to_thread(parse_plugin_zip, zip_bytes)
    except PluginArchiveSecurityError as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc), "error_code": exc.error_code},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_id = uuid.uuid4().hex
    # virtual_id keys must match build_preview_result (skill:<idx> / mcp:<idx> / agent:<idx>).
    skills_by_key = {f"skill:{idx}": skill for idx, skill in enumerate(result.skills)}
    servers_by_key = {f"mcp:{idx}": server for idx, server in enumerate(result.servers)}
    agents_by_key = {f"agent:{idx}": agent for idx, agent in enumerate(result.agents)}

    store = get_evolution_skill_store_db_path()
    staging = PluginStaging(store.parent)
    staging.save_session(
        session_id,
        PluginImportSession(
            plugin_result=result,
            skills_by_key=skills_by_key,
            servers_by_key=servers_by_key,
            agents_by_key=agents_by_key,
        ),
    )
    background_tasks.add_task(staging.cleanup_expired_sessions)

    # Detect installed capabilities for capability diff (permission escalation detection)
    installed_plugins = await list_installed_plugins()
    plugin_name = result.meta.name if result.meta else ""
    installed_caps: set[str] | None = None
    for p in installed_plugins:
        if p.get("name") == plugin_name:
            raw_caps = p.get("capabilities")
            installed_caps = {str(cap) for cap in raw_caps} if isinstance(raw_caps, list) else set()
            break

    context = await load_preview_context([agent.name for agent in result.agents])
    preview = await asyncio.to_thread(build_preview_result, result, context, installed_caps)
    return PluginImportPreviewResponse.model_validate({"session_id": session_id, **preview})


@router.post("/confirm", response_model=PluginImportConfirmResponse)
async def confirm_plugin_import(
    request: PluginImportConfirmRequest,
    background_tasks: BackgroundTasks,
) -> PluginImportConfirmResponse:
    """Confirm import decisions and persist skills + MCP servers."""
    from app.services.plugins import import_service as _import_service
    from app.services.plugins.import_service import (
        PluginConfirmItem,
        PluginStaging,
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

    def _decisions(items: list[PluginConfirmComponent]) -> list[PluginConfirmItem]:
        return [
            PluginConfirmItem(
                component=item.component,
                virtual_id=item.virtual_id,
                resolution=item.resolution,
                name=item.name,
            )
            for item in items
        ]

    try:
        result = await _import_service.confirm_plugin_import(
            session,
            skill_decisions=_decisions(request.skills),
            server_decisions=_decisions(request.servers),
            agent_decisions=_decisions(request.agents),
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

    return PluginImportConfirmResponse.model_validate(result)


class InstalledServerInfo(BaseModel):
    """One imported MCP server belonging to a plugin."""

    name: str
    enabled: bool = False


class InstalledPluginResponse(BaseModel):
    """One installed plugin (provenance-grouped from global mcpServers entries)."""

    name: str
    servers: list[str] = Field(default_factory=list)
    server_meta: list[InstalledServerInfo] = Field(default_factory=list)
    has_bundled_files: bool = False


class PluginUninstallResult(BaseModel):
    plugin_name: str
    removed_servers: int = 0
    unbound_agents: int = 0
    removed_files: bool = False


@router.get("/installed", response_model=list[InstalledPluginResponse])
async def list_installed_plugins() -> list[InstalledPluginResponse]:
    """List plugins imported with at least one MCP server."""
    from app.services.plugins.import_service import list_installed_plugins as _list

    items = await _list()
    return [InstalledPluginResponse.model_validate(item) for item in items]


@router.delete("/{plugin_name}", response_model=PluginUninstallResult)
async def uninstall_plugin(plugin_name: str) -> PluginUninstallResult:
    """Uninstall a plugin: remove its MCP servers, agent bindings, and files."""
    from app.services.plugins.import_service import uninstall_plugin as _uninstall

    result = await _uninstall(plugin_name)
    return PluginUninstallResult.model_validate(result)
