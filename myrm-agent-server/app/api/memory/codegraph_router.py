"""FastAPI router for CodeGraph memory asset and impact analysis.

[INPUT]
- REST API requests for CodeGraph scanning, impact analysis, and symbol queries.

[OUTPUT]
- FastAPI router exposing CodeGraph memory asset management endpoints.

[POS]
- app.api.memory.codegraph_router
"""

import logging

from fastapi import APIRouter, Query

from app.schemas.codegraph import (
    AnalyzeImpactRequest,
    AnalyzeImpactResponse,
    CodeGraphAssetResponse,
    ScanWorkspaceRequest,
    ScanWorkspaceResponse,
    SymbolListResponse,
)
from app.services.memory.codegraph_service import (
    codegraph_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/codegraph", tags=["memory-codegraph"])


@router.post("/scan", response_model=ScanWorkspaceResponse)
async def scan_workspace_endpoint(
    request: ScanWorkspaceRequest,
) -> ScanWorkspaceResponse:
    """Scan and index workspace source files into CodeGraph memory store."""
    logger.info("Scanning workspace for CodeGraph: %s", request.workspace_dir)
    return codegraph_service.scan_workspace(
        workspace_dir=request.workspace_dir,
        incremental=request.incremental,
        max_files=request.max_files,
    )


@router.post("/impact", response_model=AnalyzeImpactResponse)
async def analyze_impact_endpoint(
    request: AnalyzeImpactRequest,
) -> AnalyzeImpactResponse:
    """Evaluate ripple effect and blast radius before modifying a code symbol."""
    logger.info("Analyzing impact for symbol: %s", request.symbol_name)
    return codegraph_service.analyze_impact(
        symbol_name=request.symbol_name,
        file_path=request.file_path,
        max_depth=request.max_depth,
    )


@router.get("/symbols", response_model=SymbolListResponse)
async def query_symbols_endpoint(
    query: str = Query(default="", description="Substring filter for symbol name"),
    kind: str = Query(default="", description="Filter by kind: FUNCTION, CLASS, METHOD"),
    limit: int = Query(default=50, ge=1, le=200, description="Max symbols to return"),
) -> SymbolListResponse:
    """List or search discovered code symbols in the workspace CodeGraph."""
    return codegraph_service.query_symbols(
        query=query,
        kind=kind,
        limit=limit,
    )


@router.get("/asset", response_model=CodeGraphAssetResponse)
async def get_codegraph_asset_endpoint() -> CodeGraphAssetResponse:
    """Retrieve metadata snapshot for current CodeGraph memory asset."""
    return codegraph_service.get_asset_metadata()
