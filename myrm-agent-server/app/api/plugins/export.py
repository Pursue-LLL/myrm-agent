"""Agent Plugins 1.0.0 expert export API.

[INPUT]
- app.services.plugins.export_service::preview_expert_export, export_expert (POS: export orchestration.)
- app.api.skills.schemas::RedactionResponse (POS: the redaction diff shape shared with skill export.)

[OUTPUT]
- POST /plugins/export/preview — what exporting an expert would ship (experts, skills, connectors,
  workspace files), what is left out, and the secret-redaction findings that need a decision
- POST /plugins/export — the verified package (ZIP); every finding must be redacted or explicitly kept

[POS]
Business HTTP layer for sharing an expert. GUI-First: the preview feeds one review dialog
(same redaction review as single-skill export), the export call carries the user's decisions.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.skills.schemas import RedactionResponse
from app.services.plugins.export_service import (
    ExportError,
    ExportErrorCode,
    ExportPreview,
    export_expert,
    preview_expert_export,
    secret_names_of,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["plugins-export"])

_STATUS_BY_CODE = {
    ExportErrorCode.EXPERT_NOT_FOUND: 404,
    ExportErrorCode.BUILT_IN_EXPERT: 422,
    ExportErrorCode.CHANGED_SINCE_PREVIEW: 409,
    ExportErrorCode.REVIEW_REQUIRED: 409,
    ExportErrorCode.PACKAGE_REJECTED: 422,
}


class ExportExpertCard(BaseModel):
    name: str
    description: str = ""
    is_entry: bool = False
    skill_names: list[str] = Field(default_factory=list)
    connector_names: list[str] = Field(default_factory=list)
    subagent_names: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    recommended_model: str | None = Field(default=None, description="Shown to the recipient; never applied")


class ExportSkillCard(BaseModel):
    name: str = Field(description="Skill name experts reference")
    source: str = Field(description="custom (files travel) | preset (referenced by name)")
    file_count: int = 0
    version: str | None = None
    origin: str | None = Field(default=None, description="Where a custom skill was installed from, if not authored here")


class ExportConnectorCard(BaseModel):
    name: str
    type: str
    secret_keys: list[str] = Field(default_factory=list, description="Secrets the recipient must provide")


class ExportWorkspaceFile(BaseModel):
    path: str
    size: int


class ExportOmittedItem(BaseModel):
    kind: str
    name: str
    reason: str
    owner: str | None = None


class ExportPreviewRequest(BaseModel):
    agent_id: str = Field(min_length=1)


class ExportPreviewResponse(BaseModel):
    plugin_name: str
    version: str
    experts: list[ExportExpertCard]
    skills: list[ExportSkillCard]
    connectors: list[ExportConnectorCard]
    workspace_files: list[ExportWorkspaceFile]
    omitted: list[ExportOmittedItem]
    redactions: dict[str, list[RedactionResponse]] | None = None
    is_safe: bool
    review_digest: str
    package_bytes: int | None = None
    build_error: str | None = Field(default=None, description="Why the package cannot be built (export would fail alike)")


class ExportRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    apply_redactions: bool = False
    ignored_redactions: dict[str, list[int]] | None = Field(
        default=None, description="Review path -> indices of findings the user chose to keep"
    )
    review_digest: str | None = Field(default=None, description="From the preview; required when findings are kept")


@router.post("/preview", response_model=ExportPreviewResponse)
async def preview_export(request: ExportPreviewRequest) -> ExportPreviewResponse:
    try:
        preview = await preview_expert_export(request.agent_id)
    except ExportError as exc:
        raise _http_error(exc) from exc
    return _preview_response(preview)


@router.post("")
async def export_plugin(request: ExportRequest) -> Response:
    try:
        package = await export_expert(
            request.agent_id,
            apply_redactions=request.apply_redactions,
            ignored_redactions=request.ignored_redactions,
            review_digest=request.review_digest,
        )
    except ExportError as exc:
        raise _http_error(exc) from exc
    return Response(
        content=package.zip_content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{package.filename}"'},
    )


def _http_error(exc: ExportError) -> HTTPException:
    return HTTPException(
        status_code=_STATUS_BY_CODE[exc.code],
        detail={"message": exc.message, "error_code": exc.code.value},
    )


def _preview_response(preview: ExportPreview) -> ExportPreviewResponse:
    plan = preview.plan
    experts = [
        ExportExpertCard(
            name=draft.agent.name,
            description=draft.agent.description,
            is_entry=draft.agent.is_entry_agent,
            skill_names=list(draft.agent.skill_names),
            connector_names=list(draft.agent.mcp_names),
            subagent_names=list(draft.agent.subagent_names),
            tool_names=list(draft.agent.tool_names),
            recommended_model=_recommended_model(draft.agent.metadata),
        )
        for draft in plan.experts
    ]
    skills = [
        ExportSkillCard(
            name=skill.package_name,
            source="custom",
            file_count=len(skill.files),
            version=skill.version,
            origin=skill.origin_source,
        )
        for skill in plan.skills
    ] + [ExportSkillCard(name=name, source="preset") for name in plan.preset_skill_names]
    connectors = [
        ExportConnectorCard(
            name=server.name,
            type=server.server_type,
            secret_keys=secret_names_of(server),
        )
        for server in plan.connectors
    ]
    redactions = {
        path: [
            RedactionResponse(
                line_number=item["line_number"],
                original=item["original"],
                redacted=item["redacted"],
                reason=item["reason"],
            )
            for item in findings
        ]
        for path, findings in preview.redactions.items()
    }
    return ExportPreviewResponse(
        plugin_name=plan.plugin_name,
        version=preview.version,
        experts=experts,
        skills=skills,
        connectors=connectors,
        workspace_files=[ExportWorkspaceFile(path=path, size=len(content)) for path, content in plan.workspace_files.items()],
        omitted=[
            ExportOmittedItem(kind=item.kind, name=item.name, reason=item.reason.value, owner=item.owner) for item in plan.omitted
        ],
        redactions=redactions or None,
        is_safe=not redactions,
        review_digest=preview.review_digest,
        package_bytes=preview.package_bytes,
        build_error=preview.build_error,
    )


def _recommended_model(metadata: dict[str, object]) -> str | None:
    model = metadata.get("recommended_model")
    return model if isinstance(model, str) else None
