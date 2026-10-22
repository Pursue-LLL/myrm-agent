"""MCP Registry search/detail proxy and localhost connectivity probe endpoints.

[INPUT]
- app.config.settings::settings (POS: Server configuration)
- app.core.infra.limiter::limiter (POS: Rate limiter)
- app.core.utils.errors::external_service_error, validation_error (POS: Error response helpers)
- app.core.utils.response_utils::success_response (POS: Standard JSON response builder)
- app.platform_utils.deployment_capabilities::get_deployment_capabilities (POS: Deployment mode capabilities)
- app.services.integrations.mcp_registry::get_mcp_registry (POS: Smithery MCP registry client)

[OUTPUT]
- router: FastAPI APIRouter with /registry/search, /registry/detail/{qualified_name}, and /probe
- RegistryServerData, RegistrySearchData, RegistryEnvVarData, RegistryDetailData
- MCPProbeBody, MCPProbeData
- _is_tls_verification_connect_error, _is_network_unreachable_connect_error

[POS]
Sub-router included by ``app.api.integrations.mcp``.
"""

from __future__ import annotations

import errno
import logging
import ssl
import time
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.utils.errors import external_service_error, validation_error
from app.core.utils.response_utils import success_response
from app.platform_utils.deployment_capabilities import get_deployment_capabilities
from app.schemas.responses import StandardSuccessResponse

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.mcp.security import MCPConfigScanResult, MCPRuntimeScanResult

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Registry proxy endpoints
# =============================================================================


class RegistryServerData(BaseModel):
    """Single server in registry search results."""

    qualified_name: str
    display_name: str
    description: str = ""
    icon_url: str | None = None
    homepage: str | None = None
    use_count: int = 0

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class RegistrySearchData(BaseModel):
    """Paged search result from MCP registry."""

    servers: list[RegistryServerData] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total_pages: int = 1

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class RegistryEnvVarData(BaseModel):
    """Required env var template from registry metadata."""

    name: str
    description: str = ""
    required: bool = True

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class RegistryDetailData(BaseModel):
    """Full detail for a single registry server."""

    qualified_name: str
    display_name: str
    description: str = ""
    icon_url: str | None = None
    homepage: str | None = None
    use_count: int = 0
    transport_type: str = "stdio"
    env_vars: list[RegistryEnvVarData] = Field(default_factory=list)

    class Config:
        alias_generator = to_camel
        populate_by_name = True


@router.get("/registry/search", response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.mcp_verify)
async def registry_search(
    request: Request,
    q: str = Query("", description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=50, description="Results per page"),
) -> JSONResponse:
    """Search the MCP server registry via Smithery with LRU caching."""
    _ = request
    from app.services.integrations.mcp_registry import get_mcp_registry

    try:
        registry = get_mcp_registry()
        result = await registry.search(query=q, page=page, page_size=page_size)
        data = RegistrySearchData(
            servers=[
                RegistryServerData(
                    qualified_name=s.qualified_name,
                    display_name=s.display_name,
                    description=s.description,
                    icon_url=s.icon_url,
                    homepage=s.homepage,
                    use_count=s.use_count,
                )
                for s in result.servers
            ],
            page=result.page,
            page_size=result.page_size,
            total_pages=result.total_pages,
        )
        return success_response(data=data.model_dump(by_alias=True))
    except Exception as e:
        logger.error("MCP registry search failed: %s", e)
        raise external_service_error("MCP Registry", f"Search failed: {e}") from e


@router.get("/registry/detail/{qualified_name:path}", response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.mcp_verify)
async def registry_detail(
    request: Request,
    qualified_name: str,
) -> JSONResponse:
    """Get full detail for a single MCP server from the registry."""
    _ = request
    from app.services.integrations.mcp_registry import get_mcp_registry

    try:
        registry = get_mcp_registry()
        detail = await registry.get_detail(qualified_name)
        data = RegistryDetailData(
            qualified_name=detail.qualified_name,
            display_name=detail.display_name,
            description=detail.description,
            icon_url=detail.icon_url,
            homepage=detail.homepage,
            use_count=detail.use_count,
            transport_type=detail.transport_type,
            env_vars=[
                RegistryEnvVarData(
                    name=ev.name,
                    description=ev.description,
                    required=ev.required,
                )
                for ev in detail.env_vars
            ],
        )
        return success_response(data=data.model_dump(by_alias=True))
    except Exception as e:
        logger.error("MCP registry detail failed for %s: %s", qualified_name, e)
        raise external_service_error("MCP Registry", f"Detail lookup failed: {e}") from e


# =============================================================================
# Connection probe endpoint
# =============================================================================


class MCPProbeBody(BaseModel):
    """Request body for probing an MCP endpoint reachability."""

    url: str = Field(..., description="URL to probe (e.g. http://127.0.0.1:8000/mcp)")
    timeout: float = Field(default=5.0, ge=1.0, le=15.0, description="Probe timeout in seconds")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class MCPProbeData(BaseModel):
    """Result of an MCP connectivity probe."""

    status: Literal["reachable", "unreachable", "cloud_not_supported"] = Field(
        ...,
        description="reachable | unreachable | cloud_not_supported",
    )
    latency_ms: float | None = Field(default=None, description="Round-trip time if reachable")
    error: str | None = Field(default=None, description="Human-readable error if unreachable")
    reason_code: (
        Literal[
            "reachable",
            "connection_refused",
            "connection_unreachable",
            "tls_verification_failed",
            "connection_timeout",
            "probe_failed_unknown",
            "loopback_unavailable_in_cloud",
        ]
        | None
    ) = Field(
        default=None,
        description="Machine-friendly reason code for frontend UX routing",
    )
    recommended_mode: (
        Literal[
            "local_or_tauri",
            "start_local_editor_mcp",
            "verify_local_network_and_editor",
        ]
        | None
    ) = Field(
        default=None,
        description="Suggested mode for user action (e.g. local_or_tauri)",
    )
    should_block_connect: bool | None = Field(
        default=None,
        description="Whether the frontend should stop the connect flow immediately",
    )

    class Config:
        alias_generator = to_camel
        populate_by_name = True


_TLS_VERIFY_ERROR_MARKERS = (
    "certificate verify failed",
    "certificateverifyfailed",
    "self-signed certificate",
    "unable to get local issuer certificate",
    "certificate has expired",
    "hostname/ip does not match certificate",
    "hostname does not match",
)

_CONNECT_UNREACHABLE_ERRNOS = frozenset(
    {
        errno.EADDRNOTAVAIL,
        errno.EHOSTDOWN,
        errno.EHOSTUNREACH,
        errno.ENETDOWN,
        errno.ENETUNREACH,
    }
)

_CONNECT_UNREACHABLE_MARKERS = (
    "network is unreachable",
    "no route to host",
    "host is down",
    "cannot assign requested address",
)


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    stack: list[BaseException] = [exc]
    ordered: list[BaseException] = []
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        ordered.append(current)
        cause = getattr(current, "__cause__", None)
        if isinstance(cause, BaseException):
            stack.append(cause)
        context = getattr(current, "__context__", None)
        if isinstance(context, BaseException) and context is not cause:
            stack.append(context)
    return ordered


def _is_tls_verification_connect_error(exc: Exception) -> bool:
    chain = _iter_exception_chain(exc)
    if any(isinstance(item, ssl.SSLCertVerificationError) for item in chain):
        return True
    parts = [str(part) for part in chain]
    lowered = " | ".join(part.lower() for part in parts if part)
    return any(marker in lowered for marker in _TLS_VERIFY_ERROR_MARKERS)


def _is_network_unreachable_connect_error(exc: Exception) -> bool:
    chain = _iter_exception_chain(exc)
    lowered = " | ".join(str(part).lower() for part in chain if str(part))
    if any(marker in lowered for marker in _CONNECT_UNREACHABLE_MARKERS):
        return True
    return any(isinstance(item, OSError) and item.errno in _CONNECT_UNREACHABLE_ERRNOS for item in chain)


@router.post("/probe", response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.mcp_verify)
async def probe_mcp_endpoint(body: MCPProbeBody, request: Request) -> JSONResponse:
    """Probe a local MCP server URL for reachability before connecting."""
    _ = request
    caps = get_deployment_capabilities()
    if caps.is_sandbox_instance:
        data = MCPProbeData(
            status="cloud_not_supported",
            reason_code="loopback_unavailable_in_cloud",
            recommended_mode="local_or_tauri",
            should_block_connect=True,
        )
        return success_response(data=data.model_dump(by_alias=True))

    parsed = urlparse(body.url)
    hostname = parsed.hostname or ""
    safe_probe_host = parsed.hostname or ""
    if ":" in safe_probe_host and not safe_probe_host.startswith("["):
        safe_probe_host = f"[{safe_probe_host}]"
    safe_probe_port = f":{parsed.port}" if parsed.port is not None else ""
    safe_probe_target = f"{parsed.scheme}://{safe_probe_host}{safe_probe_port}{parsed.path}"
    if hostname not in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        raise validation_error("Probe is restricted to localhost addresses only (127.0.0.1, localhost, ::1)")

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=body.timeout) as client:
            await client.get(body.url)
            latency = (time.monotonic() - start) * 1000
            data = MCPProbeData(
                status="reachable",
                latency_ms=round(latency, 1),
                reason_code="reachable",
                should_block_connect=False,
            )
            return success_response(data=data.model_dump(by_alias=True))
    except httpx.ConnectError as exc:
        if _is_tls_verification_connect_error(exc):
            data = MCPProbeData(
                status="unreachable",
                error="TLS certificate verification failed — trust the MCP certificate or configure a valid CA bundle",
                reason_code="tls_verification_failed",
                should_block_connect=True,
            )
            return success_response(data=data.model_dump(by_alias=True))
        if _is_network_unreachable_connect_error(exc):
            data = MCPProbeData(
                status="unreachable",
                error="Local network route unavailable — verify localhost routing, VPN/proxy policy, and editor MCP settings",
                reason_code="connection_unreachable",
                recommended_mode="verify_local_network_and_editor",
                should_block_connect=True,
            )
            return success_response(data=data.model_dump(by_alias=True))
        data = MCPProbeData(
            status="unreachable",
            error="Connection refused — editor or MCP server not running",
            reason_code="connection_refused",
            recommended_mode="start_local_editor_mcp",
            should_block_connect=True,
        )
        return success_response(data=data.model_dump(by_alias=True))
    except httpx.ConnectTimeout:
        data = MCPProbeData(
            status="unreachable",
            error="Connection timed out — host unreachable",
            reason_code="connection_timeout",
            recommended_mode="verify_local_network_and_editor",
            should_block_connect=True,
        )
        return success_response(data=data.model_dump(by_alias=True))
    except Exception:
        logger.exception("Unexpected MCP probe failure for target=%s", safe_probe_target)
        data = MCPProbeData(
            status="unreachable",
            error="Connectivity check failed unexpectedly — verify editor MCP settings and retry",
            reason_code="probe_failed_unknown",
            recommended_mode="verify_local_network_and_editor",
            should_block_connect=True,
        )
        return success_response(data=data.model_dump(by_alias=True))


class MCPToolDetail(BaseModel):
    """Single MCP tool metadata returned by the verify endpoint."""

    name: str
    description: str = ""
    read_only_hint: bool = False
    destructive_hint: bool = False
    idempotent_hint: bool = False
    open_world_hint: bool = False

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class MCPScanFindingData(BaseModel):
    """Single MCP security scan finding."""

    threat_type: str
    severity: str
    description: str
    field: str = ""
    recommendation: str = ""

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class MCPScanData(BaseModel):
    """Static MCP configuration scan result."""

    server_name: str
    allow_save: bool
    requires_acknowledgement: bool
    max_severity: str | None = None
    findings: list[MCPScanFindingData] = Field(default_factory=list)

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class MCPVerifyData(BaseModel):
    """MCP verification response model."""

    tools_count: int = Field(..., description="Available tool count")
    service_name: str = Field(..., description="Service name")
    instructions: str | None = Field(default=None, description="MCP server instructions")
    tools: list[MCPToolDetail] = Field(default_factory=list, description="Tool metadata list")
    config_scan: MCPScanData | None = Field(default=None, description="Static config scan summary")
    runtime_scan: MCPScanData | None = Field(default=None, description="Runtime surface scan summary")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


def _scan_result_to_data(
    result: MCPConfigScanResult | MCPRuntimeScanResult,
    *,
    allow_save: bool,
    requires_acknowledgement: bool,
) -> MCPScanData:
    return MCPScanData(
        server_name=result.server_name,
        allow_save=allow_save,
        requires_acknowledgement=requires_acknowledgement,
        max_severity=result.max_severity.value if result.max_severity else None,
        findings=[
            MCPScanFindingData(
                threat_type=finding.threat_type,
                severity=finding.severity.value,
                description=finding.description,
                field=finding.field,
                recommendation=finding.recommendation,
            )
            for finding in result.findings
        ],
    )
