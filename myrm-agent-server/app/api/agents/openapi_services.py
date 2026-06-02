"""OpenAPI Services API endpoints.

Provides spec parsing preview and test request capabilities for
OpenAPI service configuration in the Agent editor.

[INPUT]
- myrm_agent_harness.toolkits.openapi_bridge (POS: OpenAPI bridge framework)

[OUTPUT]
- router: FastAPI router with /openapi-services/* endpoints

[POS]
OpenAPI Services API. Enables frontend to preview parsed specs and test
connectivity before saving service configurations.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.openapi_bridge import (
    OpenAPIBridge,
    OpenAPIServiceConfig,
    ParsedEndpoint,
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


class ParseSpecResponse(BaseModel):
    """Parsed spec preview response for frontend."""

    title: str
    version: str
    description: str
    base_url: str
    spec_version: str
    endpoints: list[ParsedEndpoint]
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
        "selected_endpoints": [
            "issues/get",
            "issues/create",
            "issues/create-comment",
            "pulls/get",
            "repos/get"
        ],
    },
    {
        "name": "Jira Software",
        "description": "Manage Jira issues, projects, and agile boards.",
        "spec_url": "https://developer.atlassian.com/cloud/jira/platform/swagger.v3.json",
        "auth_type": "basic",
        "icon_url": "https://wac-cdn.atlassian.com/assets/img/favicons/jira/favicon.ico",
        "selected_endpoints": [
            "getIssue",
            "createIssue",
            "addComment",
            "searchForIssuesUsingJql"
        ],
    },
    {
        "name": "Notion API",
        "description": "Query databases and read/write pages in Notion.",
        "spec_url": "https://developers.notion.com/reference/openapi.json",
        "auth_type": "bearer",
        "icon_url": "https://www.notion.so/images/favicon.ico",
        "selected_endpoints": [
            "queryDatabase",
            "retrievePage",
            "createPage",
            "appendBlockChildren"
        ],
    }
]


@router.get("/presets", response_model=list[SaaSPreset])
async def get_saas_presets() -> list[dict[str, str | list[str]]]:
    """Get the list of pre-configured SaaS OpenAPI connector blueprints."""
    return BUILTIN_SAAS_PRESETS


class TestRequestPayload(BaseModel):
    """Request to test an OpenAPI endpoint."""

    service_config: OpenAPIServiceConfig
    operation_id: str
    params: dict[str, str] = Field(default_factory=dict)


class TestRequestResponse(BaseModel):
    """Test request result."""

    success: bool
    status_message: str
    response_body: str = ""


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
        raise HTTPException(status_code=500, detail=f"Spec parsing failed: {e}") from e

    return ParseSpecResponse(
        title=spec.title,
        version=spec.version,
        description=spec.description,
        base_url=spec.base_url,
        spec_version=spec.spec_version,
        endpoints=spec.endpoints,
        tags=spec.tags,
        endpoint_count=len(spec.endpoints),
    )


@router.post("/test-request", response_model=TestRequestResponse)
async def test_request(payload: TestRequestPayload) -> TestRequestResponse:
    """Execute a test request against a configured OpenAPI endpoint.

    Used by frontend to verify connectivity and authentication before saving.
    """
    try:
        spec = await _bridge.preview_spec(payload.service_config)
    except ValueError as e:
        return TestRequestResponse(success=False, status_message=f"Spec error: {e}")

    target_ep = None
    for ep in spec.endpoints:
        if ep.operation_id == payload.operation_id:
            target_ep = ep
            break

    if not target_ep:
        return TestRequestResponse(
            success=False,
            status_message=f"Endpoint '{payload.operation_id}' not found in spec",
        )

    try:
        from myrm_agent_harness.toolkits.openapi_bridge import OpenAPIExecutor

        base_url = payload.service_config.base_url or spec.base_url
        if not base_url:
            return TestRequestResponse(success=False, status_message="No base URL available")

        executor = OpenAPIExecutor(
            base_url=base_url,
            auth_config=payload.service_config.auth,
            timeout=min(payload.service_config.request_timeout, 15.0),
            max_retries=0,
        )

        import re
        path_param_names = set(re.findall(r"\{(\w+)\}", target_ep.path))
        p_params = {k: v for k, v in payload.params.items() if k in path_param_names}
        q_params = {k: v for k, v in payload.params.items() if k not in path_param_names}

        result = await executor.execute(
            method=target_ep.method,
            path=target_ep.path,
            path_params=p_params or None,
            query_params=q_params or None,
        )
        await executor.close()

        is_error = result.startswith("Error")
        return TestRequestResponse(
            success=not is_error,
            status_message="Request successful" if not is_error else "Request returned error",
            response_body=result[:2000],
        )
    except Exception as e:
        return TestRequestResponse(success=False, status_message=f"Request failed: {e}")
