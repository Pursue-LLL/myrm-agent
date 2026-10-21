"""Integration Catalog data models.

Defines the schema for preconfigured service entries that users can browse
and one-click enable from the Integration Catalog UI.
"""

from enum import Enum
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator
from pydantic.alias_generators import to_camel
from pydantic.config import ConfigDict


class ConnectorType(str, Enum):
    """Underlying engine used to connect to this service."""

    MCP = "mcp"
    OPENAPI = "openapi"


class AuthType(str, Enum):
    """Authentication method required by the service."""

    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BEARER = "bearer"
    NONE = "none"


class CredentialFieldInject(str, Enum):
    """How a credential value is injected into the MCP config."""

    ARG_PLACEHOLDER = "arg_placeholder"
    ENV = "env"
    HEADER = "header"


class DeploymentScope(str, Enum):
    """Deployment compatibility scope for a catalog integration entry."""

    ALL_MODES = "all_modes"
    LOCAL_TAURI_ONLY = "local_tauri_only"


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})


def _is_loopback_url(url: str | None) -> bool:
    if not url:
        return False
    trimmed = url.strip()
    if not trimmed:
        return False
    candidate = trimmed if "://" in trimmed else f"http://{trimmed}"
    try:
        parsed = urlparse(candidate)
    except Exception:
        return False
    return (parsed.hostname or "").lower().strip() in _LOOPBACK_HOSTS


class CredentialField(BaseModel):
    """Describes a single credential input field for multi-credential services."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    key: str = Field(..., description="Placeholder key in args (e.g. '{{app_id}}') or env variable name")
    label: str = Field(..., description="Display label in connect dialog")
    label_zh: str = Field(default="", description="Chinese display label")
    inject: CredentialFieldInject = Field(..., description="Injection method")


class AuthRequirements(BaseModel):
    """Describes what credentials the user must provide to connect."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    type: AuthType = Field(..., description="Authentication method")
    env_key: str | None = Field(
        default=None,
        description="Single env key for simple services (legacy path)",
    )
    credential_fields: list[CredentialField] | None = Field(
        default=None,
        description="Structured credential fields for multi-credential services",
    )
    help_url: str | None = Field(
        default=None,
        description="URL where user can obtain credentials",
    )
    help_text: str | None = Field(
        default=None,
        description="Short instruction displayed in the connect dialog",
    )
    help_text_zh: str | None = Field(
        default=None,
        description="Chinese instruction for connect dialog",
    )


class MCPPreConfig(BaseModel):
    """Preconfigured MCP server connection template."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str = Field(..., description="MCP server name")
    type: Literal["sse", "stdio", "streamable_http"] = Field(..., description="Transport type")
    url: str | None = Field(default=None, description="Server URL (SSE/HTTP)")
    command: str | None = Field(default=None, description="Command (stdio)")
    args: list[str] | None = Field(default=None, description="Arguments (stdio)")
    env: dict[str, str] | None = Field(default=None, description="Preset environment variables (non-secret)")
    headers: dict[str, str] | None = Field(
        default=None,
        description="HTTP headers for SSE/streamable_http (values may use {{CREDENTIAL}} placeholders)",
    )
    description: str = Field(default="", description="Service description for LLM")
    host_serial: bool = Field(
        default=False,
        description="Force serial tool scheduling for stateful host editors (UE, Blender)",
    )
    keepalive_interval: float | None = Field(
        default=None,
        ge=5.0,
        le=3600.0,
        description="Keepalive ping interval in seconds for long-running MCP connections",
    )
    probe_url: str | None = Field(
        default=None,
        description="URL to probe for connectivity diagnostics before connecting",
    )
    deployment_scope: DeploymentScope | None = Field(
        default=None,
        description="Optional deployment compatibility hint for GUI guardrails",
    )
    post_connect_guide: str | None = Field(
        default=None,
        description="Setup guide displayed in connect dialog (English)",
    )
    post_connect_guide_zh: str | None = Field(
        default=None,
        description="Setup guide displayed in connect dialog (Chinese)",
    )

    @model_validator(mode="after")
    def validate_local_tauri_scope(self) -> "MCPPreConfig":
        """Ensure local/tauri-only catalog entries always point to loopback endpoints."""
        if self.deployment_scope != DeploymentScope.LOCAL_TAURI_ONLY:
            return self

        probe_candidate = self.probe_url or self.url
        if probe_candidate is None:
            raise ValueError("deployment_scope=local_tauri_only requires probe_url or url")
        if not _is_loopback_url(probe_candidate):
            raise ValueError("deployment_scope=local_tauri_only requires a loopback probe/url")
        return self


class OpenAPIPreConfig(BaseModel):
    """Preconfigured OpenAPI service connection template."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    spec_url: str = Field(..., description="OpenAPI spec URL")
    name: str = Field(..., description="Service name")
    description: str = Field(default="", description="Service description")


class CatalogEntry(BaseModel):
    """A single service in the Integration Catalog.

    Each entry describes a preconfigured integration that users can browse
    and enable with minimal configuration.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str = Field(..., description="Unique identifier (e.g. 'notion', 'github')")
    name: str = Field(..., description="Display name")
    name_zh: str = Field(default="", description="Chinese display name")
    description: str = Field(..., description="Short description")
    description_zh: str = Field(default="", description="Chinese description")
    icon: str = Field(..., description="Icon identifier for frontend rendering")
    category: str = Field(..., description="Category slug (productivity, development, etc.)")
    connector_type: ConnectorType = Field(..., description="Underlying engine")
    mcp_config: MCPPreConfig | None = Field(default=None, description="MCP config template (when connector_type=mcp)")
    openapi_config: OpenAPIPreConfig | None = Field(
        default=None, description="OpenAPI config template (when connector_type=openapi)"
    )
    auth: AuthRequirements = Field(..., description="Authentication requirements")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    website: str | None = Field(default=None, description="Official service website")
