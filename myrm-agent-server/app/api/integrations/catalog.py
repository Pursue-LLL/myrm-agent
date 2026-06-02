"""Integration Catalog API endpoints.

Provides a preconfigured service directory for users to browse and one-click
enable integrations. The catalog entries are backed by static JSON data and
do not require external service dependencies.
"""

import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from pydantic.config import ConfigDict

from app.core.integrations.catalog import CatalogEntry, CatalogRegistry
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class CatalogEntryResponse(BaseModel):
    """Serialized catalog entry for the frontend."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    name: str
    name_zh: str
    description: str
    description_zh: str
    icon: str
    category: str
    connector_type: str
    auth_type: str
    help_url: str | None = None
    help_text: str | None = None
    help_text_zh: str | None = None
    env_key: str | None = None
    credential_fields: list[dict[str, str]] | None = None
    tags: list[str] = Field(default_factory=list)
    website: str | None = None
    mcp_config: dict[str, object] | None = None


class CatalogListResponse(BaseModel):
    """Response for the catalog list endpoint."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    entries: list[CatalogEntryResponse]
    categories: list[str]
    total: int


def _entry_to_response(entry: CatalogEntry) -> CatalogEntryResponse:
    """Convert a CatalogEntry to its API response form."""

    mcp_config_dict: dict[str, object] | None = None
    if entry.mcp_config:
        mcp_config_dict = entry.mcp_config.model_dump(exclude_none=True)

    return CatalogEntryResponse(
        id=entry.id,
        name=entry.name,
        name_zh=entry.name_zh,
        description=entry.description,
        description_zh=entry.description_zh,
        icon=entry.icon,
        category=entry.category,
        connector_type=entry.connector_type.value,
        auth_type=entry.auth.type.value,
        help_url=entry.auth.help_url,
        help_text=entry.auth.help_text,
        help_text_zh=entry.auth.help_text_zh,
        env_key=entry.auth.env_key,
        credential_fields=[f.model_dump() for f in entry.auth.credential_fields] if entry.auth.credential_fields else None,
        tags=entry.tags,
        website=entry.website,
        mcp_config=mcp_config_dict,
    )


@router.get("", response_model=StandardSuccessResponse)
async def list_catalog(
    category: str | None = Query(default=None, description="Filter by category"),
    q: str | None = Query(default=None, description="Search query"),
) -> JSONResponse:
    """List all available integration services from the catalog.

    Supports optional category filtering and text search.
    """
    registry = CatalogRegistry.get_instance()

    if q:
        entries = registry.search(q)
    elif category:
        entries = registry.list_by_category(category)
    else:
        entries = registry.list_all()

    categories = registry.get_categories()
    response_entries = [_entry_to_response(e) for e in entries]

    data = CatalogListResponse(
        entries=response_entries,
        categories=categories,
        total=len(response_entries),
    )
    return success_response(data=data.model_dump(by_alias=True))


@router.get("/{entry_id}", response_model=StandardSuccessResponse)
async def get_catalog_entry(entry_id: str) -> JSONResponse:
    """Get a single catalog entry by ID."""
    registry = CatalogRegistry.get_instance()
    entry = registry.get_by_id(entry_id)

    if entry is None:
        from app.core.utils.errors import not_found_error

        raise not_found_error(f"Integration '{entry_id}' not found in catalog")

    return success_response(data=_entry_to_response(entry).model_dump(by_alias=True))
