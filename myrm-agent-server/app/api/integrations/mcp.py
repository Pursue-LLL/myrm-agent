import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.mcp import MCPAgent
from myrm_agent_harness.toolkits.mcp.security import (
    MCPConfigScanResult,
    MCPResponseError,
    MCPResponseValidator,
    MCPRuntimeScanResult,
    MCPURLValidator,
    URLValidationError,
)
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from app.api.integrations.mcp_probe_registry import (
    MCPProbeBody,
    MCPProbeData,
    MCPScanData,
    MCPScanFindingData,
    MCPToolDetail,
    MCPVerifyData,
    RegistryDetailData,
    RegistryEnvVarData,
    RegistrySearchData,
    RegistryServerData,
    _is_network_unreachable_connect_error,
    _is_tls_verification_connect_error,
    _scan_result_to_data,
    probe_mcp_endpoint,
    registry_detail,
    registry_search,
)
from app.api.integrations.mcp_probe_registry import (
    router as _probe_registry_router,
)
from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.types import MCPServerConfig
from app.core.utils.errors import (
    external_service_error,
    timeout_error,
    validation_error,
)
from app.core.utils.response_utils import success_response
from app.platform_utils.deployment_capabilities import get_deployment_capabilities
from app.schemas.responses import StandardSuccessResponse
from app.services.integrations.mcp_posture import (
    enforce_mcp_config_posture,
    enforce_mcp_runtime_posture,
    resolve_mcp_config_scan,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_mcp_agent_instance: MCPAgent | None = None


def get_mcp_agent() -> MCPAgent:
    """Return the singleton MCPAgent instance."""
    global _mcp_agent_instance
    if _mcp_agent_instance is None:
        _mcp_agent_instance = MCPAgent()
    return _mcp_agent_instance


_mcp_response_validator: MCPResponseValidator | None = None


def _get_response_validator() -> MCPResponseValidator:
    """Return the singleton MCPResponseValidator instance."""
    global _mcp_response_validator
    if _mcp_response_validator is None:
        _mcp_response_validator = MCPResponseValidator(max_response_size=settings.mcp.max_response_size)
    return _mcp_response_validator


def _config_scan_to_data(result: MCPConfigScanResult) -> MCPScanData:
    return _scan_result_to_data(
        result,
        allow_save=result.allow_save,
        requires_acknowledgement=result.requires_acknowledgement,
    )


def _runtime_scan_to_data(result: MCPRuntimeScanResult) -> MCPScanData:
    return _scan_result_to_data(
        result,
        allow_save=result.allow_use,
        requires_acknowledgement=not result.allow_use,
    )


class MCPOptionsData(BaseModel):
    """MCP deployment options response model."""

    allow_stdio: bool = Field(..., description="Whether stdio transport is allowed")
    allow_sse: bool = Field(..., description="Whether SSE transport is allowed")
    allowed_types: list[str] = Field(..., description="Allowed transport types")
    require_https: bool = Field(..., description="Whether HTTPS is enforced")
    ssrf_protection_enabled: bool = Field(..., description="Whether SSRF protection is enabled")
    verify_timeout: int = Field(..., description="Verification timeout in seconds")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


@router.get("/options", response_model=StandardSuccessResponse)
async def get_mcp_options() -> JSONResponse:
    """Return allowed MCP transport types and security settings for the deployment."""
    allowed_types = ["sse", "streamable_http"]
    if settings.mcp.allow_stdio:
        allowed_types.append("stdio")

    data = MCPOptionsData(
        allow_stdio=settings.mcp.allow_stdio,
        allow_sse=True,
        allowed_types=allowed_types,
        require_https=settings.mcp.require_https,
        ssrf_protection_enabled=settings.mcp.enable_ssrf_protection,
        verify_timeout=settings.mcp.verify_timeout,
    )
    return success_response(data=data.model_dump(by_alias=True))


class MCPScanBatchBody(BaseModel):
    """Batch static scan request for multiple MCP configurations."""

    configs: list[MCPServerConfig] = Field(default_factory=list)

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class MCPScanBatchData(BaseModel):
    """Batch static scan response."""

    results: list[MCPScanData] = Field(default_factory=list)

    class Config:
        alias_generator = to_camel
        populate_by_name = True


@router.post("/scan", response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.mcp_verify)
async def scan_mcp_config_endpoint(mcp_server_config: MCPServerConfig, request: Request) -> JSONResponse:
    """Static pre-flight scan for MCP configuration (no network connection)."""
    _ = request
    scan_result = await resolve_mcp_config_scan(mcp_server_config)
    return success_response(data=_config_scan_to_data(scan_result).model_dump(by_alias=True))


@router.post("/scan-batch", response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.mcp_verify)
async def scan_mcp_config_batch_endpoint(body: MCPScanBatchBody, request: Request) -> JSONResponse:
    """Batch static pre-flight scan for multiple MCP configurations."""
    _ = request
    results: list[MCPScanData] = []
    for config in body.configs:
        scan_result = await resolve_mcp_config_scan(config)
        results.append(_config_scan_to_data(scan_result))
    batch = MCPScanBatchData(results=results)
    return success_response(data=batch.model_dump(by_alias=True))


@router.post("/verify", response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.mcp_verify)
async def verify_mcp_service(
    mcp_server_config: MCPServerConfig,
    request: Request,
    acknowledged_high_risks: bool = Query(False),
) -> JSONResponse:
    """Verify MCP connectivity after static scan, OSV check, and runtime surface scan."""
    try:
        config_scan_result = await resolve_mcp_config_scan(mcp_server_config)
        enforce_mcp_config_posture(
            mcp_server_config,
            acknowledged_high_risks=acknowledged_high_risks,
            result=config_scan_result,
        )

        if mcp_server_config.type == "stdio" and not settings.mcp.allow_stdio:
            logger.warning(
                f"STDIO mode blocked: {mcp_server_config.name}",
                extra={"ip": request.client.host if request.client else "unknown"},
            )
            raise validation_error("STDIO mode is not allowed in current deployment environment, please use SSE or HTTP mode")

        if mcp_server_config.url and settings.mcp.enable_ssrf_protection:
            validator = MCPURLValidator(require_https=settings.mcp.require_https)
            try:
                resolved = await validator.validate_url(mcp_server_config.url)
                logger.info(
                    f"URL validation passed: {mcp_server_config.url}",
                    extra={
                        "service": mcp_server_config.name,
                        "resolved_ips": resolved.resolved_ips,
                        "hostname": resolved.hostname,
                    },
                )
            except URLValidationError as e:
                logger.error(
                    f"SSRF attack blocked: {mcp_server_config.url}",
                    extra={
                        "service": mcp_server_config.name,
                        "reason": e.reason,
                        "ip": request.client.host if request.client else "unknown",
                    },
                )
                raise validation_error(
                    f"URL validation failed: {e.reason}. "
                    f"Possible reasons: private IP, cloud metadata service, DNS resolution failure, or HTTPS required."
                ) from e

        mcp_agent = get_mcp_agent()

        # One handshake serves both results: get_tools() captures the server's
        # initialize instructions while enumerating, so verification never spawns a
        # second subprocess or opens a second HTTP connection.
        tools_result = await asyncio.wait_for(
            mcp_agent.get_tools([mcp_server_config]),
            timeout=settings.mcp.verify_timeout,
        )

        tools_count = len(tools_result) if tools_result else 0

        if get_deployment_capabilities().validates_mcp_response_size:
            response_validator = _get_response_validator()
            try:
                response_validator.validate_tools_response(tools_result or [])
            except MCPResponseError as e:
                logger.error(
                    f"Response validation failed: {mcp_server_config.name}",
                    extra={"reason": e.reason},
                )
                raise validation_error(f"Response validation failed: {e.reason}. The MCP server returned too much data.") from e

        instructions_value = mcp_agent.get_server_instructions(mcp_server_config.name)
        if instructions_value is not None and get_deployment_capabilities().validates_mcp_response_size:
            try:
                _get_response_validator().validate_instructions_response(instructions_value)
            except MCPResponseError as e:
                logger.error(
                    f"Instructions validation failed: {mcp_server_config.name}",
                    extra={"reason": e.reason},
                )
                instructions_value = None

        tool_details: list[MCPToolDetail] = []
        runtime_tool_pairs: list[tuple[str, str]] = []
        if tools_result:
            for t in tools_result:
                meta = getattr(t, "metadata", {}) or {}
                description = t.description or ""
                tool_details.append(
                    MCPToolDetail(
                        name=t.name,
                        description=description,
                        read_only_hint=bool(meta.get("readOnlyHint", False)),
                        destructive_hint=bool(meta.get("destructiveHint", False)),
                        idempotent_hint=bool(meta.get("idempotentHint", False)),
                        open_world_hint=bool(meta.get("openWorldHint", False)),
                    )
                )
                runtime_tool_pairs.append((t.name, description))

        runtime_scan_result = enforce_mcp_runtime_posture(
            mcp_server_config,
            instructions=instructions_value,
            tools=runtime_tool_pairs,
        )

        logger.warning(
            "MCP service verified successfully",
            extra={
                "service_name": mcp_server_config.name,
                "service_type": mcp_server_config.type,
                "service_url": mcp_server_config.url if mcp_server_config.url else None,
                "tools_count": tools_count,
                "has_instructions": instructions_value is not None,
                "ip": request.client.host if request.client else "unknown",
            },
        )

        data = MCPVerifyData(
            tools_count=tools_count,
            service_name=mcp_server_config.name,
            instructions=instructions_value,
            tools=tool_details,
            config_scan=_config_scan_to_data(config_scan_result),
            runtime_scan=_runtime_scan_to_data(runtime_scan_result),
        )
        return success_response(data=data.model_dump())

    except asyncio.TimeoutError as e:
        logger.error(f"MCP service verification timeout: {mcp_server_config.name}")
        raise timeout_error(operation="MCP service verification") from e
    except ValueError as e:
        logger.error(f"MCP service verification parameter error: {str(e)}")
        if "Unsupported transport type" in str(e):
            raise validation_error(
                f"Unsupported transport type '{mcp_server_config.type}', "
                f"please use 'sse', 'streamable_http', or 'stdio' (if allowed)"
            ) from e
        raise validation_error(f"Parameter validation failed: {str(e)}") from e
    except ConnectionError as e:
        logger.error(f"MCP service connection failed: {str(e)}")
        raise external_service_error("MCP", f"Connection failed: {str(e)}") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MCP service verification error: {str(e)}", exc_info=True)
        raise external_service_error("MCP", f"Verification failed: {str(e)}") from e


@router.get("/resource")
@limiter.limit(settings.rate_limit.mcp_verify)
async def read_mcp_resource(
    request: Request,
    uri: str = Query(..., description="MCP resource URI (e.g. ui://server/path)"),
    server: str = Query(..., description="MCP server name that owns the resource"),
) -> JSONResponse:
    """Proxy endpoint for frontend to fetch MCP App UI resources."""
    import base64

    from myrm_agent_harness.toolkits.mcp.connection_manager import MCPConnectionManager

    manager = MCPConnectionManager._instance
    if manager is None:
        raise external_service_error("MCP", "MCP connection pool not initialized")

    connections = manager._connections
    if not connections:
        raise external_service_error("MCP", "No active MCP connections")

    resource_bytes: bytes | None = None
    last_error: str = ""
    for conn in connections.values():
        try:
            resource_bytes = await asyncio.wait_for(
                conn.read_resource(server, uri),
                timeout=settings.mcp.verify_timeout,
            )
            break
        except RuntimeError as e:
            last_error = str(e)
            continue
        except asyncio.TimeoutError as exc:
            raise timeout_error(operation="MCP resource read") from exc
        except Exception as e:
            last_error = str(e)
            logger.warning("MCP resource read failed for server '%s': %s", server, e)
            continue

    if resource_bytes is None:
        raise external_service_error("MCP", f"Resource not found: {last_error}")

    content_b64 = base64.b64encode(resource_bytes).decode("ascii")
    mime_type = "text/html"
    if uri.endswith(".js"):
        mime_type = "application/javascript"
    elif uri.endswith(".css"):
        mime_type = "text/css"
    elif uri.endswith(".json"):
        mime_type = "application/json"

    return success_response(
        data={
            "content": content_b64,
            "mime_type": mime_type,
            "uri": uri,
            "server": server,
        }
    )


router.include_router(_probe_registry_router)

__all__ = [
    "MCPOptionsData",
    "MCPProbeBody",
    "MCPProbeData",
    "MCPScanBatchBody",
    "MCPScanBatchData",
    "MCPScanData",
    "MCPScanFindingData",
    "MCPToolDetail",
    "MCPVerifyData",
    "RegistryDetailData",
    "RegistryEnvVarData",
    "RegistrySearchData",
    "RegistryServerData",
    "_is_network_unreachable_connect_error",
    "_is_tls_verification_connect_error",
    "get_mcp_agent",
    "get_mcp_options",
    "probe_mcp_endpoint",
    "read_mcp_resource",
    "registry_detail",
    "registry_search",
    "router",
    "scan_mcp_config_batch_endpoint",
    "scan_mcp_config_endpoint",
    "verify_mcp_service",
]
