"""OpenAPI Services API endpoints.

Provides spec parsing preview and the built-in SaaS connector presets for
OpenAPI service configuration in the Agent editor.

[INPUT]
- myrm_agent_harness.toolkits.openapi_bridge (POS: OpenAPI bridge framework)

[OUTPUT]
- router: FastAPI router with /openapi-services/* endpoints

[POS]
OpenAPI Services API. Enables frontend to preview parsed specs and pick
a pre-configured SaaS connector before saving service configurations.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.openapi_bridge import (
    OpenAPIBridge,
    OpenAPIServiceConfig,
    ParsedSpec,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/openapi-services", tags=["openapi-services"])

_bridge = OpenAPIBridge()


class ParseSpecRequest(BaseModel):
    """Request to parse an OpenAPI spec for preview."""

    spec_url: str | None = Field(default=None, description="URL to fetch spec from")
    spec_content: str | None = Field(default=None, description="Inline spec content (JSON/YAML)")


class EndpointPreview(BaseModel):
    """Lightweight endpoint metadata for the preview listing.

    Deliberately excludes ``param_schema``: large specs (e.g. GitHub, 300+
    endpoints) would otherwise ship full JSON Schemas to the frontend, which
    only needs identifiers and display metadata.
    """

    operation_id: str
    method: str
    path: str
    summary: str
    description: str
    tags: list[str]
    deprecated: bool


class ParseSpecResponse(BaseModel):
    """Parsed spec preview response for frontend."""

    title: str
    version: str
    description: str
    base_url: str
    spec_version: str
    endpoints: list[EndpointPreview]
    tags: dict[str, str]
    endpoint_count: int


class SaaSPreset(BaseModel):
    """A built-in preset for a SaaS OpenAPI connector."""

    name: str
    description: str
    spec_url: str
    auth_type: str
    icon_url: str | None = None
    selected_endpoints: list[str] | None = None


BUILTIN_SAAS_PRESETS: list[dict[str, str | list[str]]] = [
    {
        "name": "GitHub (Public API)",
        "description": "Interact with GitHub Repositories, Issues, and PRs.",
        "spec_url": "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json",
        "auth_type": "bearer",
        "icon_url": "https://github.githubassets.com/favicons/favicon.png",
        "selected_endpoints": ["issues/get", "issues/create", "issues/create-comment", "pulls/get", "repos/get"],
    },
    {
        "name": "Jira Software",
        "description": "Manage Jira issues, projects, and agile boards.",
        "spec_url": "https://developer.atlassian.com/cloud/jira/platform/swagger.v3.json",
        "auth_type": "basic",
        "icon_url": "https://wac-cdn.atlassian.com/assets/img/favicons/jira/favicon.ico",
        "selected_endpoints": ["getIssue", "createIssue", "addComment", "searchForIssuesUsingJql"],
    },
    {
        "name": "Notion API",
        "description": "Query databases and read/write pages in Notion.",
        "spec_url": "https://developers.notion.com/reference/openapi.json",
        "auth_type": "bearer",
        "icon_url": "https://www.notion.so/images/favicon.ico",
        "selected_endpoints": ["queryDatabase", "retrievePage", "createPage", "appendBlockChildren"],
    },
]


@router.get("/presets", response_model=list[SaaSPreset])
async def get_saas_presets() -> list[dict[str, str | list[str]]]:
    """Get the list of pre-configured SaaS OpenAPI connector blueprints."""
    return BUILTIN_SAAS_PRESETS


@router.post("/parse-spec", response_model=ParseSpecResponse)
async def parse_spec(request: ParseSpecRequest) -> ParseSpecResponse:
    """Parse an OpenAPI spec and return endpoint listing for preview.

    Frontend uses this to display available endpoints before user selects
    which ones to expose as agent tools.
    """
    if not request.spec_url and not request.spec_content:
        raise HTTPException(status_code=400, detail="Either spec_url or spec_content is required")

    try:
        config = OpenAPIServiceConfig(
            name="preview",
            spec_url=request.spec_url,
            spec_content=request.spec_content,
        )
        spec: ParsedSpec = await _bridge.preview_spec(config)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to parse spec: %s", e)
        raise HTTPException(status_code=500, detail="Spec parsing failed") from e

    return ParseSpecResponse(
        title=spec.title,
        version=spec.version,
        description=spec.description,
        base_url=spec.base_url,
        spec_version=spec.spec_version,
        endpoints=[
            EndpointPreview(
                operation_id=ep.operation_id,
                method=ep.method,
                path=ep.path,
                summary=ep.summary,
                description=ep.description,
                tags=ep.tags,
                deprecated=ep.deprecated,
            )
            for ep in spec.endpoints
        ],
        tags=spec.tags,
        endpoint_count=len(spec.endpoints),
    )
