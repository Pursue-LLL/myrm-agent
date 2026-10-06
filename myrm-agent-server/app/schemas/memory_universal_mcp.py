"""
[POS] app/schemas/memory_universal_mcp.py
[INPUT] pydantic
[OUTPUT] GenerateClientConfigRequestDTO, ClientConfigSnippetDTO, GenerateClientConfigResponseDTO, ExternalClientItemDTO, ListSupportedClientsResponseDTO, McpToolDefinitionDTO, ListMcpToolsResponseDTO

Pydantic DTOs for Universal MCP Memory Bridge and External Client Config Generator.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GenerateClientConfigRequestDTO(BaseModel):
    """Payload to generate MCP config snippets for external AI tools."""

    model_config = ConfigDict(extra="forbid")

    client_kind: str | None = Field(
        default=None,
        description="Target client kind (claude_code, cursor, vscode_cline, codebuddy, hermes). If omitted, generates for all clients.",
    )
    user_id: str = Field(
        default="default_user",
        description="Unified user identity lease anchor to ensure instant cross-tool convergence",
    )
    transport: str = Field(
        default="stdio",
        description="MCP transport kind ('stdio' or 'sse')",
    )
    host: str = Field(
        default="127.0.0.1",
        description="Host for SSE transport",
    )
    port: int = Field(
        default=8000,
        description="Port for SSE transport",
    )


class ClientConfigSnippetDTO(BaseModel):
    """Generated plug-and-play configuration snippet for an external AI assistant."""

    model_config = ConfigDict(extra="forbid")

    client_kind: str = Field(..., description="Target client kind identifier")
    transport: str = Field(..., description="Transport kind used (stdio / sse)")
    target_config_file_path: str = Field(..., description="Default or standard config file location on host")
    config_format: str = Field(..., description="Format: 'json' or 'yaml'")
    raw_content: str = Field(..., description="Ready-to-copy raw configuration snippet text")
    instructions: str = Field(..., description="Step-by-step guidance on how to mount this snippet")


class GenerateClientConfigResponseDTO(BaseModel):
    """Response containing generated client configuration snippets."""

    model_config = ConfigDict(extra="forbid")

    snippets: list[ClientConfigSnippetDTO] = Field(default_factory=list, description="Generated snippets")
    total: int = Field(..., ge=0, description="Total number of generated snippets")


class ExternalClientItemDTO(BaseModel):
    """Details of a supported external client."""

    model_config = ConfigDict(extra="forbid")

    client_kind: str = Field(..., description="Client identifier")
    display_name: str = Field(..., description="Human-readable client name")
    default_config_path: str = Field(..., description="Default configuration file location")
    recommended_transport: str = Field(..., description="Recommended transport (stdio / sse)")
    description: str = Field(..., description="Client integration summary")


class ListSupportedClientsResponseDTO(BaseModel):
    """Response containing all supported external AI clients."""

    model_config = ConfigDict(extra="forbid")

    clients: list[ExternalClientItemDTO] = Field(default_factory=list, description="Supported clients")
    total: int = Field(..., ge=0, description="Total supported clients")


class McpToolDefinitionDTO(BaseModel):
    """Definition of an exposed memory MCP tool."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Tool function name")
    description: str = Field(..., description="Tool purpose description")
    required_params: list[str] = Field(default_factory=list, description="List of required parameter names")


class ListMcpToolsResponseDTO(BaseModel):
    """Response listing exposed memory MCP tools."""

    model_config = ConfigDict(extra="forbid")

    tools: list[McpToolDefinitionDTO] = Field(default_factory=list, description="Exposed tools")
    total: int = Field(..., ge=0, description="Total exposed tools")
