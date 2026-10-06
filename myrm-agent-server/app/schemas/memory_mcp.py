"""
[POS] app/schemas/memory_mcp.py
[INPUT] pydantic
[OUTPUT] AiMemoryQueryRequestDTO, AiMemoryQueryResponseDTO, AiMemoryFinalizeRequestDTO, AiMemoryFinalizeResponseDTO, AiMemoryRememberRequestDTO, AiMemoryRememberResponseDTO, McpServerInfoDTO

Pydantic DTOs for standard Memory MCP Server interoperability and ai-memory wire parity.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AiMemoryQueryRequestDTO(BaseModel):
    """Payload for memory search matching ai-memory query_memory signature."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Keywords or natural language question to search")
    limit: int = Field(default=5, ge=1, le=50, description="Maximum number of memories to return")


class AiMemoryQueryResponseDTO(BaseModel):
    """Response matching ai-memory formatted markdown output."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="Query string executed")
    content_markdown: str = Field(..., description="Formatted markdown string of memories")
    count: int = Field(ge=0, description="Total matching items found")


class AiMemoryFinalizeRequestDTO(BaseModel):
    """Payload matching ai-memory finalize-session tool signature."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., min_length=1, description="Summary of current working session and accomplishments")
    next_steps: list[str] = Field(default_factory=list, description="Immediate next action items for successor")
    failed_approaches: list[str] = Field(
        default_factory=list, description="Approaches attempted and discarded with reasons"
    )
    session_id: str | None = Field(default=None, description="Optional active session identifier")


class AiMemoryFinalizeResponseDTO(BaseModel):
    """Confirmation output for session finalization."""

    model_config = ConfigDict(extra="forbid")

    handoff_id: str = Field(..., description="Durable handoff memorandum ID")
    status: str = Field(default="recorded", description="Status of the handoff record")
    message: str = Field(..., description="Human-readable status summary")


class AiMemoryRememberRequestDTO(BaseModel):
    """Payload matching ai-memory remember/save_fact tool signature."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., min_length=1, description="Domain topic, entity name, or rule category")
    note: str = Field(..., min_length=1, description="Fact, rule, or architectural constraint content")
    source_file: str | None = Field(default=None, description="Optional source file or reference origin")


class AiMemoryRememberResponseDTO(BaseModel):
    """Confirmation output for memory fact ingestion under privacy gate."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., description="Memory topic/entity")
    status: str = Field(..., description="Result status: stored, sanitized_and_stored, or rejected")
    message: str = Field(..., description="Execution summary description")


class McpServerInfoDTO(BaseModel):
    """Metadata describing active memory MCP server gateway."""

    model_config = ConfigDict(extra="forbid")

    server_name: str = Field(default="myrm-memory-mcp", description="Name of the MCP server")
    version: str = Field(default="1.0.0", description="Semantic version of server")
    compatible_with: list[str] = Field(
        default_factory=lambda: ["ai-memory-v1", "claude-code", "cursor-ide", "codex"],
        description="List of compatible tool and client protocols",
    )
    tools_exposed: list[str] = Field(
        default_factory=list, description="List of registered MCP tool names"
    )
