"""
[POS] app/services/memory/memory_universal_mcp_service.py
[INPUT] logging, threading.Lock, myrm_agent_harness.toolkits.memory.universal_mcp_bridge, app.schemas.memory_universal_mcp
[OUTPUT] MemoryUniversalMcpService, get_memory_universal_mcp_service

Service orchestrating plug-and-play MCP configuration generation and memory tool discovery for external AI tools.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
from threading import Lock

from myrm_agent_harness.toolkits.memory.universal_mcp_bridge import (
    ClientConfigSnippet,
    ExternalClientConfigGenerator,
    ExternalClientKind,
    McpTransportKind,
    UniversalMcpMemoryBridge,
    UniversalMemoryBridgeOptions,
)

from app.schemas.memory_universal_mcp import (
    ClientConfigSnippetDTO,
    ExternalClientItemDTO,
    GenerateClientConfigRequestDTO,
    GenerateClientConfigResponseDTO,
    ListMcpToolsResponseDTO,
    ListSupportedClientsResponseDTO,
    McpToolDefinitionDTO,
)

logger = logging.getLogger(__name__)


class MemoryUniversalMcpService:
    """Service providing configuration generation and bridge introspection for external AI assistants."""

    def __init__(self, bridge: UniversalMcpMemoryBridge | None = None) -> None:
        self._lock: Lock = Lock()
        self._bridge: UniversalMcpMemoryBridge = bridge or UniversalMcpMemoryBridge()

    def generate_config(
        self,
        request: GenerateClientConfigRequestDTO,
    ) -> GenerateClientConfigResponseDTO:
        """Generate ready-to-copy MCP configuration snippets for external AI tools."""
        transport_kind = (
            McpTransportKind.SSE
            if request.transport.lower() == "sse"
            else McpTransportKind.STDIO
        )

        options = UniversalMemoryBridgeOptions(
            user_id=request.user_id,
            host=request.host,
            port=request.port,
            transport=transport_kind,
        )

        snippets: list[ClientConfigSnippet] = []

        if request.client_kind:
            kind_str = request.client_kind.lower()
            try:
                target_kind = ExternalClientKind(kind_str)
                snippet = ExternalClientConfigGenerator.generate(target_kind, options)
                snippets.append(snippet)
            except ValueError:
                logger.warning("Requested client kind '%s' not recognized, falling back to all", kind_str)
                snippets = ExternalClientConfigGenerator.generate_all(options)
        else:
            snippets = ExternalClientConfigGenerator.generate_all(options)

        dtos: list[ClientConfigSnippetDTO] = [
            ClientConfigSnippetDTO(
                client_kind=s.client_kind.value,
                transport=s.transport.value,
                target_config_file_path=s.target_config_file_path,
                config_format=s.config_format,
                raw_content=s.raw_content,
                instructions=s.instructions,
            )
            for s in snippets
        ]

        logger.info(
            "Generated %d client configuration snippets for user '%s' using transport '%s'",
            len(dtos),
            request.user_id,
            transport_kind.value,
        )

        return GenerateClientConfigResponseDTO(
            snippets=dtos,
            total=len(dtos),
        )

    def list_supported_clients(self) -> ListSupportedClientsResponseDTO:
        """Return catalog of all supported external AI clients with mount guidelines."""
        catalog: list[ExternalClientItemDTO] = [
            ExternalClientItemDTO(
                client_kind="claude_code",
                display_name="Claude Code (Anthropic CLI)",
                default_config_path="~/.claude.json",
                recommended_transport="stdio",
                description="Anthropic's terminal agent for high-velocity coding and terminal workflows.",
            ),
            ExternalClientItemDTO(
                client_kind="cursor",
                display_name="Cursor IDE",
                default_config_path=".cursor/mcp.json",
                recommended_transport="stdio",
                description="AI-first fork of VS Code with native codebase indexing.",
            ),
            ExternalClientItemDTO(
                client_kind="vscode_cline",
                display_name="VS Code Cline Extension",
                default_config_path="cline_mcp_settings.json",
                recommended_transport="stdio",
                description="Autonomous coding agent inside standard VS Code editor.",
            ),
            ExternalClientItemDTO(
                client_kind="codebuddy",
                display_name="CodeBuddy CLI",
                default_config_path="~/.codebuddy/.mcp.json",
                recommended_transport="stdio",
                description="Interactive code assistant for day-to-day engineering tasks.",
            ),
            ExternalClientItemDTO(
                client_kind="hermes",
                display_name="Hermes Companion Assistant",
                default_config_path="~/.hermes/config.yaml",
                recommended_transport="stdio",
                description="Local-first always-on desktop AI companion.",
            ),
        ]
        return ListSupportedClientsResponseDTO(clients=catalog, total=len(catalog))

    def list_exposed_tools(self) -> ListMcpToolsResponseDTO:
        """Return exposed memory MCP tool schemas."""
        definitions = self._bridge.get_tool_definitions()
        tools_dtos: list[McpToolDefinitionDTO] = []
        for defn in definitions:
            name = str(defn.get("name", ""))
            desc = str(defn.get("description", ""))
            input_schema = defn.get("inputSchema")
            required_params: list[str] = []
            if isinstance(input_schema, dict):
                req = input_schema.get("required")
                if isinstance(req, list):
                    required_params = [str(p) for p in req]

            tools_dtos.append(
                McpToolDefinitionDTO(
                    name=name,
                    description=desc,
                    required_params=required_params,
                )
            )

        return ListMcpToolsResponseDTO(tools=tools_dtos, total=len(tools_dtos))


_global_universal_mcp_service: MemoryUniversalMcpService | None = None
_mcp_service_lock: Lock = Lock()


def get_memory_universal_mcp_service() -> MemoryUniversalMcpService:
    """Singleton provider for MemoryUniversalMcpService."""
    global _global_universal_mcp_service
    if _global_universal_mcp_service is None:
        with _mcp_service_lock:
            if _global_universal_mcp_service is None:
                _global_universal_mcp_service = MemoryUniversalMcpService()
    return _global_universal_mcp_service
