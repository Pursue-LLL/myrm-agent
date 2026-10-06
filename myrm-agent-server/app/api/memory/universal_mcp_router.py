"""
[POS] app/api/memory/universal_mcp_router.py
[INPUT] fastapi, app.schemas.memory_universal_mcp, app.services.memory.memory_universal_mcp_service
[OUTPUT] router

FastAPI router exposing endpoints for Universal MCP Memory Bridge and External Client Configuration Generator.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_universal_mcp import (
    GenerateClientConfigRequestDTO,
    GenerateClientConfigResponseDTO,
    ListMcpToolsResponseDTO,
    ListSupportedClientsResponseDTO,
)
from app.services.memory.memory_universal_mcp_service import (
    MemoryUniversalMcpService,
    get_memory_universal_mcp_service,
)

router = APIRouter()


@router.post(
    "/universal-mcp/config",
    response_model=GenerateClientConfigResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Generate plug-and-play MCP configuration snippets for external AI tools",
)
def generate_client_config(
    request: GenerateClientConfigRequestDTO,
    service: MemoryUniversalMcpService = Depends(get_memory_universal_mcp_service),
) -> GenerateClientConfigResponseDTO:
    """Generate ready-to-use configuration JSON/YAML snippets for Claude Code, Cursor, Cline, CodeBuddy, and Hermes."""
    return service.generate_config(request)


@router.get(
    "/universal-mcp/clients",
    response_model=ListSupportedClientsResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="List supported external AI coding and companion clients",
)
def list_supported_clients(
    service: MemoryUniversalMcpService = Depends(get_memory_universal_mcp_service),
) -> ListSupportedClientsResponseDTO:
    """Retrieve catalog of supported external AI clients with mounting guidelines and default config locations."""
    return service.list_supported_clients()


@router.get(
    "/universal-mcp/tools",
    response_model=ListMcpToolsResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="List standardized memory tools exposed via MCP to external agents",
)
def list_exposed_mcp_tools(
    service: MemoryUniversalMcpService = Depends(get_memory_universal_mcp_service),
) -> ListMcpToolsResponseDTO:
    """Introspect standardized memory recall, store, list, and manage MCP tool signatures."""
    return service.list_exposed_tools()
