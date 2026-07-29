from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.web_search.web_searcher import SearchServiceConfig
from pydantic import BaseModel, Field

from app.core.integrations.search_catalog.registry import SearchProviderCatalogRegistry
from app.core.utils.errors import external_service_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse
from app.services.integrations.search_verify import verify_search_config_live, invalidate_search_verify_cache

router = APIRouter()


class SearchEngineVerifyRequest(BaseModel):
    """Search provider verification request."""

    search_service: str = Field(..., description="Provider slug")
    num_results: int = Field(default=1, description="Number of results")
    api_key: str | None = Field(None, description="API key")
    api_base: str | None = Field(None, description="API base URL (SearXNG)")
    query: str | None = Field(None, description="Optional probe query")


class SearchVerifyData(BaseModel):
    """Search verification response payload."""

    service_type: str = Field(..., description="Provider slug")
    results_count: int = Field(default=1, description="Result count from probe")


class SearchProviderResponse(BaseModel):
    slug: str
    connector: str
    name: str
    name_zh: str
    deployment_scope: str
    requires_api_key: bool
    requires_api_base: bool
    backend_ready: bool


@router.get("/providers", response_model=StandardSuccessResponse)
async def list_search_providers(
    is_local: bool = Query(default=True, alias="isLocal", description="Local/Tauri vs cloud sandbox"),
) -> JSONResponse:
    """Return search provider manifest entries for Settings UI."""
    registry = SearchProviderCatalogRegistry.get_instance()
    entries = registry.list_for_deploy_mode(is_local=is_local)
    payload = [
        SearchProviderResponse(
            slug=entry.slug,
            connector=entry.connector.value,
            name=entry.name,
            name_zh=entry.name_zh,
            deployment_scope=entry.deployment_scope.value,
            requires_api_key=entry.requires_api_key,
            requires_api_base=entry.requires_api_base,
            backend_ready=entry.backend_ready,
        ).model_dump(by_alias=True)
        for entry in entries
    ]
    return success_response(data={"providers": payload, "maxChainSize": registry.max_chain_size()})


@router.post("/verify", response_model=StandardSuccessResponse)
async def verify_search_engine(request: SearchEngineVerifyRequest) -> JSONResponse:
    """Verify a search provider configuration with a live probe."""
    registry = SearchProviderCatalogRegistry.get_instance()
    if not registry.is_selectable_slug(request.search_service):
        raise validation_error(f"Unknown or unavailable search provider: {request.search_service}")

    entry = registry.get_by_slug(request.search_service)
    if entry is None:
        raise validation_error(f"Unknown search provider: {request.search_service}")

    if entry.requires_api_base and not request.api_base:
        raise validation_error("api_base is required for this search provider")
    if entry.requires_api_key and not request.api_key:
        raise validation_error(f"API key is required when using {request.search_service}")

    cfg = SearchServiceConfig(
        search_service=request.search_service,
        api_key=request.api_key,
        api_base=request.api_base,
    )
    try:
        ok = await verify_search_config_live(cfg, query=request.query)
        if not ok:
            raise external_service_error("Search service", "Search probe returned no results")
        invalidate_search_verify_cache()
        data = SearchVerifyData(service_type=request.search_service, results_count=1)
        return success_response(data=data.model_dump())
    except HTTPException:
        raise
    except Exception as exc:
        raise external_service_error("Search service", str(exc)) from exc
