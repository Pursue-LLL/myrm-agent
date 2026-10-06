"""
[POS] app/services/memory/memory_mcp_service.py
[INPUT] myrm_agent_harness.toolkits.memory.agent_surface.mcp, app/schemas/memory_mcp.py
[OUTPUT] MemoryMcpService, get_memory_mcp_service

Business service managing standard MCP server interop gateway and ai-memory wire parity.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
from threading import Lock

from myrm_agent_harness.agent.context_management.handoff import AgentHandoffEngine
from myrm_agent_harness.toolkits.memory.agent_surface.mcp import (
    AiMemoryWireAdapter,
    create_interop_memory_mcp_server,
)
from myrm_agent_harness.toolkits.memory.privacy_gate import MemoryPrivacyBoundaryGate

from app.schemas.memory_mcp import (
    AiMemoryFinalizeRequestDTO,
    AiMemoryFinalizeResponseDTO,
    AiMemoryQueryRequestDTO,
    AiMemoryQueryResponseDTO,
    AiMemoryRememberRequestDTO,
    AiMemoryRememberResponseDTO,
    McpServerInfoDTO,
)

logger = logging.getLogger(__name__)


class MemoryMcpService:
    """Service mediating requests between FastAPI endpoints and Harness MCP wire adapter."""

    def __init__(
        self,
        handoff_engine: AgentHandoffEngine | None = None,
        privacy_gate: MemoryPrivacyBoundaryGate | None = None,
        server_name: str = "myrm-memory-mcp",
    ) -> None:
        self._engine = handoff_engine or AgentHandoffEngine()
        self._gate = privacy_gate or MemoryPrivacyBoundaryGate()
        self._server, self._info = create_interop_memory_mcp_server(
            handoff_engine=self._engine,
            privacy_gate=self._gate,
            server_name=server_name,
        )
        self._adapter = AiMemoryWireAdapter(
            handoff_engine=self._engine,
            privacy_gate=self._gate,
        )
        logger.info("MemoryMcpService initialized with server '%s'", server_name)

    def get_info(self) -> McpServerInfoDTO:
        """Fetch metadata describing exposed MCP tools and protocol compatibility."""
        return McpServerInfoDTO(
            server_name=self._info.server_name,
            version=self._info.version,
            compatible_with=list(self._info.compatible_with),
            tools_exposed=list(self._info.tools_exposed),
        )

    def query(self, request: AiMemoryQueryRequestDTO) -> AiMemoryQueryResponseDTO:
        """Execute memory search returning ai-memory markdown format."""
        formatted_md = self._adapter.query_memory(query=request.query, limit=request.limit)
        # Parse result count from formatted header if present
        count = 0
        if "results)" in formatted_md:
            try:
                start_idx = formatted_md.index("(") + 1
                end_idx = formatted_md.index(" results)")
                count = int(formatted_md[start_idx:end_idx].strip())
            except (ValueError, IndexError):
                count = 1
        elif "No matching memories" not in formatted_md:
            count = 1

        return AiMemoryQueryResponseDTO(
            query=request.query,
            content_markdown=formatted_md,
            count=count,
        )

    def get_handoff(self, target_profile_id: str | None = None) -> str:
        """Fetch human-readable markdown of active handoff memorandum."""
        return self._adapter.get_handoff(target_profile_id=target_profile_id)

    def finalize_session(self, request: AiMemoryFinalizeRequestDTO) -> AiMemoryFinalizeResponseDTO:
        """Finalize agent working session and write durable handoff memorandum."""
        msg = self._adapter.finalize_session(
            summary=request.summary,
            next_steps=request.next_steps,
            failed_approaches=request.failed_approaches,
            session_id=request.session_id,
        )
        # Extract handoff id from message snippet
        handoff_id = "handoff-unknown"
        if "[" in msg and "]" in msg:
            start = msg.index("[") + 1
            end = msg.index("]")
            handoff_id = msg[start:end]

        return AiMemoryFinalizeResponseDTO(
            handoff_id=handoff_id,
            status="recorded",
            message=msg,
        )

    def remember(self, request: AiMemoryRememberRequestDTO) -> AiMemoryRememberResponseDTO:
        """Ingest architectural memory fact under privacy boundary gate."""
        msg = self._adapter.remember(
            topic=request.topic,
            note=request.note,
            source_file=request.source_file,
        )
        if "REJECTED" in msg:
            status_str = "rejected"
        elif "Sanitized" in msg:
            status_str = "sanitized_and_stored"
        else:
            status_str = "stored"

        return AiMemoryRememberResponseDTO(
            topic=request.topic,
            status=status_str,
            message=msg,
        )


_service_lock = Lock()
_service_instance: MemoryMcpService | None = None


def get_memory_mcp_service() -> MemoryMcpService:
    """Singleton provider for MemoryMcpService."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = MemoryMcpService()
    return _service_instance
