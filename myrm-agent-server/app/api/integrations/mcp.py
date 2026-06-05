import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.mcp import MCPAgent, MCPClientManager
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

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.types import MCPServerConfig
from app.core.utils.errors import (
    external_service_error,
    timeout_error,
    validation_error,
)
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse
from app.platform_utils.deployment_capabilities import get_deployment_capabilities
from app.services.integrations.mcp_posture import (
    enforce_mcp_config_posture,
    enforce_mcp_runtime_posture,
    resolve_mcp_config_scan,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# =============================================================================
# 模块级单例（避免重复实例化）
# =============================================================================

# MCPAgent 实例复用（每次创建新实例会清空 _tool_server_mapping）
# 注意：在验证场景下，每次都会调用 get_tools_with_client 清空映射，所以复用实例没有副作用
_mcp_agent_instance: MCPAgent | None = None


def get_mcp_agent() -> MCPAgent:
    """获取 MCP Agent 实例（单例模式）"""
    global _mcp_agent_instance
    if _mcp_agent_instance is None:
        _mcp_agent_instance = MCPAgent()
    return _mcp_agent_instance


# MCP 响应验证器实例复用
_mcp_response_validator: MCPResponseValidator | None = None


def _get_response_validator() -> MCPResponseValidator:
    """获取 MCP 响应验证器实例（单例模式）

    注入业务层配置：settings.mcp.max_response_size
    """
    global _mcp_response_validator
    if _mcp_response_validator is None:
        _mcp_response_validator = MCPResponseValidator(max_response_size=settings.mcp.max_response_size)
    return _mcp_response_validator


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
    """MCP验证数据模型"""

    tools_count: int = Field(..., description="可用工具数量")
    service_name: str = Field(..., description="服务名称")
    instructions: str | None = Field(default=None, description="MCP服务的instructions，无则为空")
    tools: list[MCPToolDetail] = Field(default_factory=list, description="工具明细列表(名称/描述/风险注解)")
    config_scan: MCPScanData | None = Field(default=None, description="静态配置扫描摘要")
    runtime_scan: MCPScanData | None = Field(default=None, description="运行时表面扫描摘要")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


def _scan_result_to_data(
    result: MCPConfigScanResult | MCPRuntimeScanResult,
    *,
    allow_save: bool,
    requires_acknowledgement: bool,
) -> MCPScanData:
    max_sev = result.max_severity.value if isinstance(result, MCPConfigScanResult) and result.max_severity else None
    if isinstance(result, MCPRuntimeScanResult) and result.findings:
        max_sev = max((f.severity.value for f in result.findings), default=None)
    return MCPScanData(
        server_name=result.server_name,
        allow_save=allow_save,
        requires_acknowledgement=requires_acknowledgement,
        max_severity=max_sev,
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


async def _get_server_instructions(server_name: str, mcp_config: list[MCPServerConfig]) -> str | None:
    """获取 MCP 服务器的 instructions"""
    try:
        client = await MCPClientManager.initialize_client(mcp_config)
        async with client.session(server_name, auto_initialize=False) as session:
            init_result = await session.initialize()
            raw_instr = init_result.instructions
            out: str | None = raw_instr if isinstance(raw_instr, str) else None
            if out is None and hasattr(init_result, "serverInfo"):
                server_info = getattr(init_result, "serverInfo", None)
                if server_info is not None:
                    alt = getattr(server_info, "instructions", None)
                    out = alt if isinstance(alt, str) else None
            return out
    except Exception as e:
        logger.warning(f"Failed to get instructions from {server_name}: {e}")
        return None


class MCPOptionsData(BaseModel):
    """MCP 选项数据模型"""

    allow_stdio: bool = Field(..., description="是否允许 stdio 模式")
    allow_sse: bool = Field(..., description="是否允许 SSE 模式")
    allowed_types: list[str] = Field(..., description="允许的传输类型列表")
    require_https: bool = Field(..., description="是否强制 HTTPS")
    ssrf_protection_enabled: bool = Field(..., description="是否启用 SSRF 防护")
    verify_timeout: int = Field(..., description="验证超时时间（秒）")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


@router.get("/options", response_model=StandardSuccessResponse)
async def get_mcp_options() -> JSONResponse:
    """获取 MCP 配置选项

    返回当前部署环境下允许的 MCP 传输类型和安全配置。

    安全配置：
    - stdio 模式在 Sandbox 部署时被禁用
    - 生产环境强制 HTTPS
    - SSRF 防护默认启用
    """
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
    """Verify MCP connectivity after static scan, OSV check, and runtime surface scan.

    Pipeline: static scan -> OSV (stdio) -> dynamic verify -> runtime surface scan.

    Security controls also include rate limiting, stdio policy, SSRF/DNS pinning,
    HTTPS enforcement, timeouts, and response size limits.
    """
    # =========================================================================
    # P0: 严重安全检查（仅 Sandbox 模式）
    # =========================================================================

    try:
        # 0. Static pre-flight scan + OSV (no MCP connection yet)
        config_scan_result = await resolve_mcp_config_scan(mcp_server_config)
        enforce_mcp_config_posture(
            mcp_server_config,
            acknowledged_high_risks=acknowledged_high_risks,
            result=config_scan_result,
        )

        # 1. 检查 stdio 模式是否允许
        if mcp_server_config.type == "stdio" and not settings.mcp.allow_stdio:
            logger.warning(
                f"🚫 STDIO mode blocked: {mcp_server_config.name}",
                extra={"ip": request.client.host if request.client else "unknown"},
            )
            raise validation_error("STDIO mode is not allowed in current deployment environment, please use SSE or HTTP mode")

        # 2. SSRF 防护：验证 URL 安全性（SSE/HTTP 模式）
        if mcp_server_config.url and settings.mcp.enable_ssrf_protection:
            validator = MCPURLValidator(require_https=settings.mcp.require_https)

            try:
                resolved = await validator.validate_url(mcp_server_config.url)
                logger.info(
                    f"✅ URL validation passed: {mcp_server_config.url}",
                    extra={
                        "service": mcp_server_config.name,
                        "resolved_ips": resolved.resolved_ips,
                        "hostname": resolved.hostname,
                    },
                )
            except URLValidationError as e:
                logger.error(
                    f"🚨 SSRF attack blocked: {mcp_server_config.url}",
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

        # =========================================================================
        # P1: 功能验证
        # =========================================================================

        # 3. 获取工具列表和 instructions（带超时）
        mcp_agent = get_mcp_agent()  # 使用单例实例
        mcp_config_list = [mcp_server_config]

        # 并发获取工具和 instructions
        tools_task = asyncio.wait_for(
            mcp_agent.get_tools(mcp_config_list),
            timeout=settings.mcp.verify_timeout,
        )
        instructions_task = asyncio.wait_for(
            _get_server_instructions(mcp_server_config.name, mcp_config_list),
            timeout=settings.mcp.verify_timeout,
        )

        results = await asyncio.gather(tools_task, instructions_task, return_exceptions=True)
        tools_result, instructions_result = results[0], results[1]

        # 处理工具获取结果
        if isinstance(tools_result, BaseException):
            logger.error(f"Failed to get tools from MCP service: {mcp_server_config.name}: {tools_result}")
            raise tools_result
        tools_count = len(tools_result) if tools_result else 0

        # 4. 响应大小验证（仅 Sandbox 模式）
        if get_deployment_capabilities().validates_mcp_response_size:
            response_validator = _get_response_validator()
            try:
                response_validator.validate_tools_response(tools_result or [])
            except MCPResponseError as e:
                logger.error(
                    f"🚨 Response validation failed: {mcp_server_config.name}",
                    extra={"reason": e.reason},
                )
                raise validation_error(f"Response validation failed: {e.reason}. The MCP server returned too much data.") from e

        # 处理 instructions 获取结果（失败时返回 None，不影响整体验证）
        instructions_value: str | None = None
        if isinstance(instructions_result, BaseException):
            logger.warning(f"Failed to get instructions from {mcp_server_config.name}: {instructions_result}")
        elif isinstance(instructions_result, str):
            instructions_value = instructions_result

            # 5. Instructions 大小验证（仅 Sandbox 模式）
            if get_deployment_capabilities().validates_mcp_response_size:
                response_validator = _get_response_validator()
                try:
                    response_validator.validate_instructions_response(instructions_value)
                except MCPResponseError as e:
                    logger.error(
                        f"🚨 Instructions validation failed: {mcp_server_config.name}",
                        extra={"reason": e.reason},
                    )
                    # Instructions 验证失败不影响整体验证，但记录日志
                    instructions_value = None  # 清空 instructions

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

    # =========================================================================
    # 异常处理
    # =========================================================================

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
