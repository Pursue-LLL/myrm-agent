"""Integrations API router

Main router that aggregates all external integration validation endpoints
and the Integration Catalog service directory.
"""

import logging

from fastapi import APIRouter

from app.api.integrations import (
    catalog,
    hardware,
    im_contacts,
    integration_memory,
    llms,
    mcp,
    mcp_oauth,
    oauth,
    retrieval,
    search,
)

logger = logging.getLogger(__name__)

# Create main router
router = APIRouter()

# Include sub-routers with appropriate prefixes
router.include_router(hardware.router, prefix="/hardware", tags=["integrations-hardware"])
router.include_router(llms.router, prefix="/llm", tags=["integrations-llm"])
router.include_router(search.router, prefix="/search", tags=["integrations-search"])
router.include_router(mcp.router, prefix="/mcp", tags=["integrations-mcp"])
router.include_router(mcp_oauth.router, prefix="/mcp/oauth", tags=["integrations-mcp-oauth"])
router.include_router(retrieval.router, prefix="/retrieval", tags=["integrations-retrieval"])
router.include_router(catalog.router, prefix="/catalog", tags=["integrations-catalog"])
router.include_router(oauth.router, prefix="/oauth", tags=["integrations-oauth"])
router.include_router(im_contacts.router, prefix="/contacts", tags=["integrations-contacts"])
router.include_router(integration_memory.router, prefix="/memory", tags=["integrations-memory"])
