"""Business-specific type definitions

This module contains type definitions used across the business layer.
"""

from __future__ import annotations

from typing import Literal, Self

from myrm_agent_harness.agent.config.llm import CustomModelDef
from myrm_agent_harness.toolkits.mcp.config import MCPAuthProvider
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

# Chat history types
ContentItem = str | list[dict[str, object]] | dict[str, object]
ChatHistoryReq = list[list[Literal["human", "assistant"] | ContentItem]]


class ModelConfig(BaseModel):
    """Model configuration for LLM (Business Layer)

    Mirrors framework ``LLMConfig`` with frontend API compatibility (camelCase support)
    and multi-key credential pool support. Defined standalone because ``LLMConfig`` is not
    usable as a typing base under strict mypy for this package layout.

    Attributes:
        model: Model name (e.g., "gpt-4", "claude-3-opus")
        api_key: Primary API key for authentication
        base_url: Optional custom API base URL
        api_keys: All active API keys for credential pool rotation (None = single key mode)
        credential_pool_strategy: Dispatch strategy for credential pool (round_robin/fill_first/least_used/random)
    """

    model: str = Field(..., description="Model name", min_length=1)
    api_key: str = Field(..., description="API key", min_length=1)
    base_url: str | None = Field(default=None, description="API base URL")
    temperature: float | None = Field(default=None, description="Temperature parameter")
    streaming: bool = Field(default=True, description="Enable streaming")
    model_kwargs: dict[str, object] | None = Field(default=None, description="Model-specific parameters")
    max_context_tokens: int | None = Field(
        default=None,
        description="Context window size for dynamic compression and summary thresholds",
    )
    supports_vision: bool = Field(default=False, description="Whether the model supports vision/image input")
    supports_video: bool = Field(default=False, description="Whether the model supports native video input (e.g. Gemini)")
    custom_model_def: CustomModelDef | None = Field(
        default=None,
        description="Custom model definition for self-hosted endpoints (Ollama/LM Studio/vLLM)",
    )

    api_keys: list[str] | None = Field(
        default=None,
        description="All active API keys for credential pool (rate-limit aware rotation)",
    )
    credential_pool_strategy: str | None = Field(
        default=None,
        description="Dispatch strategy for credential pool: round_robin, fill_first, least_used, random",
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)

    @field_validator("model", "api_key", mode="before")
    @classmethod
    def _strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("base_url", mode="before")
    @classmethod
    def _normalize_base_url(cls, v: str | None) -> str | None:
        if not isinstance(v, str):
            return v
        normalized = v.strip().rstrip("/")
        return normalized or None


class ModelsConfig(BaseModel):
    """Multi-model configuration

    Configure multiple models for different Agent tasks, enabling flexible
    model selection for different purposes.

    Attributes:
        main: Main Agent model for reasoning and decision making (required)
        filter: Filter/summary model (optional) for large tool result filtering
                and context summarization. Defaults to main model if not provided.
        planner: Planner model (optional) for task planning.
                 Defaults to main model if not provided.

    Example:
        >>> models_cfg = ModelsConfig(
        ...     main=ModelConfig(model="gpt-4o", api_key="..."),
        ...     filter=ModelConfig(model="gpt-4o-mini", api_key="..."),
        ... )
    """

    main: ModelConfig = Field(..., description="Main Agent model for reasoning and decision making")
    filter: ModelConfig | None = Field(
        default=None,
        description="Filter/summary model (optional) for large tool result filtering and context summarization",
    )
    planner: ModelConfig | None = Field(
        default=None,
        description="Planner model (optional) for task planning",
    )
    vision_fallback: ModelConfig | None = Field(
        default=None,
        description="Vision fallback model (optional) for converting images to text when main model lacks vision",
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MCPServerConfig(BaseModel):
    """MCP server configuration for the business layer.

    Mirrors framework ``MCPConfig`` with frontend API compatibility (camelCase support).

    Example:
        >>> config = MCPServerConfig(
        ...     name="filesystem",
        ...     type="stdio",
        ...     command="npx",
        ...     args=["-y", "@modelcontextprotocol/server-filesystem"],
        ...     description="File system operations"
        ... )
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
        arbitrary_types_allowed=True,
    )

    name: str = Field(..., description="MCP server name (unique identifier)")
    type: str = Field(..., description="Connection type: sse, stdio, streamable_http")
    url: str | None = Field(default=None, description="URL for SSE or HTTP connections")
    command: str | None = Field(default=None, description="Command for stdio connections")
    args: list[str] | None = Field(default=None, description="Arguments for stdio connections")
    description: str = Field(
        default="",
        description="Service description for LLM skill selection",
    )
    headers: dict[str, str] | None = Field(
        default=None,
        description=(
            "HTTP headers for SSE/streamable_http connections. "
            "Values may contain {{secret:KEY_NAME}} references resolved at connection time."
        ),
    )
    extra_params: dict[str, object] | None = Field(default=None, description="Additional parameters for client")
    required_secrets: list[str] | None = Field(
        default=None,
        description="List of secret keys this MCP server is allowed to access (Scoped Secret Injection)",
    )
    tool_include: list[str] | None = Field(
        default=None,
        description=(
            "Tool whitelist: only these tool names register. Per-agent selection is "
            "injected here at agent build time. None/empty = no constraint; precedence over tool_exclude."
        ),
    )
    tool_exclude: list[str] | None = Field(
        default=None,
        description="Tool blacklist: all but these register. Ignored when tool_include is set.",
    )
    host_serial: bool = Field(
        default=False,
        description=(
            "When true, treat all tools from this MCP server as host-stateful and force serial scheduling "
            "(overrides read-only parallel hints)."
        ),
    )
    connect_timeout: float = Field(
        default=15.0,
        description="Connection timeout in seconds (stdio startup may be slow)",
    )
    execute_timeout: float = Field(
        default=120.0,
        description="Tool execution timeout in seconds (complex operations like DB queries need more time)",
    )
    keepalive_interval: float | None = Field(
        default=None,
        ge=5.0,
        le=3600.0,
        description=(
            "Optional remote MCP keepalive interval in seconds. "
            "Applies to SSE/streamable_http only; None uses framework default."
        ),
    )
    ssl_verify: bool | str | None = Field(
        default=None,
        description=(
            "TLS certificate verification for HTTP/SSE transports. "
            "None or True = default; False = disable; "
            "str = CA bundle path (PEM file or OpenSSL capath directory)"
        ),
    )
    client_cert: str | None = Field(
        default=None,
        description="TLS client certificate path for mTLS (supports ~ expansion)",
    )
    client_key: str | None = Field(
        default=None,
        description="TLS client private key path (optional, if separate from cert)",
    )
    client_key_password: str | None = Field(
        default=None,
        description=(
            "Passphrase for an encrypted client private key. Encrypted at rest with the rest of mcpServers config; never logged."
        ),
    )
    auth_provider: MCPAuthProvider | None = Field(
        default=None,
        exclude=True,
        description="Authentication provider for remote connections (business layer injects)",
    )
    oversized_result_handler: object | None = Field(
        default=None,
        exclude=True,
        description="Callback to persist oversized MCP tool outputs (business layer injects)",
    )

    @field_validator("url", mode="before")
    @classmethod
    def _normalize_url(cls, v: str | None) -> str | None:
        if not isinstance(v, str):
            return v
        normalized = v.strip().rstrip("/")
        return normalized or None

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_transport_type(cls, v: str | None) -> str | None:
        if not isinstance(v, str):
            return v
        normalized = v.strip().lower().replace("-", "_")
        if normalized in ("streamable_http", "streamablehttp", "http"):
            return "streamable_http"
        return normalized

    @model_validator(mode="after")
    def _validate_transport(self) -> Self:
        if self.type not in ("stdio", "sse", "streamable_http"):
            raise ValueError(
                f"MCPConfig '{self.name}': unsupported type='{self.type}' "
                "(expected stdio | sse | streamable_http)"
            )
        if self.type in ("sse", "streamable_http") and not self.url:
            raise ValueError(f"MCPConfig '{self.name}': type='{self.type}' requires 'url'")
        if self.type == "stdio" and not self.command:
            raise ValueError(f"MCPConfig '{self.name}': type='stdio' requires 'command'")
        if self.client_key and not self.client_cert:
            raise ValueError(
                f"MCPConfig '{self.name}': 'client_key' requires 'client_cert' "
                f"(a private key cannot be used without its certificate)"
            )
        if self.client_key_password and not self.client_cert:
            raise ValueError(
                f"MCPConfig '{self.name}': 'client_key_password' requires 'client_cert' "
                f"(set the client certificate whose key is passphrase-protected)"
            )
        return self


__all__ = [
    "ModelConfig",
    "ModelsConfig",
    "MCPServerConfig",
]
