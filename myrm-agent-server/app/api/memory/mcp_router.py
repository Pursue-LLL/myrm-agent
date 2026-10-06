"""
[POS] app/api/memory/mcp_router.py
[INPUT] fastapi, app/schemas/memory_mcp.py, app/services/memory/memory_mcp_service.py
[OUTPUT] router

FastAPI router exposing standard memory MCP server interop and ai-memory wire parity endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.schemas.memory_mcp import (
    AiMemoryFinalizeRequestDTO,
    AiMemoryFinalizeResponseDTO,
    AiMemoryQueryRequestDTO,
    AiMemoryQueryResponseDTO,
    AiMemoryRememberRequestDTO,
    AiMemoryRememberResponseDTO,
    McpServerInfoDTO,
)
from app.services.memory.memory_mcp_service import (
    MemoryMcpService,
    get_memory_mcp_service,
)

router = APIRouter()


@router.get(
    "/mcp/info",
    response_model=McpServerInfoDTO,
    status_code=status.HTTP_200_OK,
    summary="Get memory MCP server metadata and registered tools",
)
def get_mcp_server_info(
    service: MemoryMcpService = Depends(get_memory_mcp_service),
) -> McpServerInfoDTO:
    """Fetch active MCP server gateway information and supported tool signatures."""
    return service.get_info()


@router.post(
    "/mcp/query",
    response_model=AiMemoryQueryResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Query memories using ai-memory compatible wire signature",
)
def query_memory_mcp(
    request: AiMemoryQueryRequestDTO,
    service: MemoryMcpService = Depends(get_memory_mcp_service),
) -> AiMemoryQueryResponseDTO:
    """Execute memory search formatted in standard ai-memory markdown."""
    return service.query(request)


@router.get(
    "/mcp/handoff",
    response_model=str,
    status_code=status.HTTP_200_OK,
    summary="Fetch active handoff memorandum in ai-memory markdown format",
)
def get_mcp_handoff(
    target_profile_id: str | None = Query(default=None, description="Optional target profile identifier"),
    service: MemoryMcpService = Depends(get_memory_mcp_service),
) -> str:
    """Retrieve active pending handoff memorandum formatted as human-readable markdown."""
    return service.get_handoff(target_profile_id=target_profile_id)


@router.post(
    "/mcp/finalize",
    response_model=AiMemoryFinalizeResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Finalize session into durable handoff memorandum",
)
def finalize_session_mcp(
    request: AiMemoryFinalizeRequestDTO,
    service: MemoryMcpService = Depends(get_memory_mcp_service),
) -> AiMemoryFinalizeResponseDTO:
    """Finalize agent working session and persist immutable handoff memorandum."""
    return service.finalize_session(request)


@router.post(
    "/mcp/remember",
    response_model=AiMemoryRememberResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Ingest architectural fact under privacy boundary gate",
)
def remember_mcp(
    request: AiMemoryRememberRequestDTO,
    service: MemoryMcpService = Depends(get_memory_mcp_service),
) -> AiMemoryRememberResponseDTO:
    """Store architectural fact, auto-sanitizing or blocking credentials under privacy policy."""
    return service.remember(request)
