import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.mcp import MCPAgent, MCPClientManager
from myrm_agent_harness.toolkits.mcp.security import (
    MCPResponseError,
    MCPResponseValidator,
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


class MCPVerifyData(BaseModel):
    """MCP验证数据模型"""

    tools_count: int = Field(..., description="可用工具数量")
    service_name: str = Field(..., description="服务名称")
    instructions: str | None = Field(default=None, description="MCP服务的instructions，无则为空")
    tools: list[MCPToolDetail] = Field(default_factory=list, description="工具明细列表(名称/描述/风险注解)")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


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


@router.post("/verify", response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.mcp_verify)
async def verify_mcp_service(mcp_server_config: MCPServerConfig, request: Request) -> JSONResponse:
    """验证MCP服务是否有效

    验证单个MCP服务器配置是否正确，连接是否正常。

    安全检查（仅 Sandbox 模式）：
    1. 应用层限流：10次/分钟 + 100次/小时（防止瞬时高并发）
    2. STDIO 模式权限检查
    3. SSRF 防护（URL 黑名单、DNS 解析验证）
    4. HTTPS 强制（生产环境）
    5. 超时控制（防止 DoS）
    6. 响应大小限制（防止内存溢出）

    返回工具数量、服务名称和 instructions（如果有）。

    注意：限流是纯技术保护，与业务配额无关。
    """
    # =========================================================================
    # P0: 严重安全检查（仅 Sandbox 模式）
    # =========================================================================

    try:
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

        # =========================================================================
        # P2: 审计日志
        # =========================================================================

        logger.warning(
            "📋 MCP service verified successfully",
            extra={
                "service_name": mcp_server_config.name,
                "service_type": mcp_server_config.type,
                "service_url": mcp_server_config.url if mcp_server_config.url else None,
                "tools_count": tools_count,
                "has_instructions": instructions_value is not None,
                "ip": request.client.host if request.client else "unknown",
            },
        )

        tool_details: list[MCPToolDetail] = []
        if tools_result:
            for t in tools_result:
                meta = getattr(t, "metadata", {}) or {}
                tool_details.append(MCPToolDetail(
                    name=t.name,
                    description=t.description or "",
                    read_only_hint=bool(meta.get("readOnlyHint", False)),
                    destructive_hint=bool(meta.get("destructiveHint", False)),
                    idempotent_hint=bool(meta.get("idempotentHint", False)),
                    open_world_hint=bool(meta.get("openWorldHint", False)),
                ))

        data = MCPVerifyData(
            tools_count=tools_count,
            service_name=mcp_server_config.name,
            instructions=instructions_value,
            tools=tool_details,
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

    except Exception as e:
        logger.error(f"MCP service verification error: {str(e)}", exc_info=True)
        raise external_service_error("MCP", f"Verification failed: {str(e)}") from e
