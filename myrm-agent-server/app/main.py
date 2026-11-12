"""FastAPI 应用程序入口

[INPUT]
app.api.router::api_router / route_loader (POS: API 路由聚合；路由组按需导入)
app.server.lazy_routes::LazyRouteMiddleware (POS: 请求命中的路由组先挂载再路由)
app.server.lifespan::optimized_lifespan (POS: 生命周期函数)
myrm_agent_harness.agent.security.workspace_trust (POS: 工作区信任子包公共面；导入即向 MCP 传输注册拉起子进程前的信任闸)
app.config.settings::settings (POS: 统一配置中心)
app.core.monitoring::FASTAPI_TELEMETRY (POS: FastAPI 原生遥测策略：不产出 HTTP 请求 span，不自建导出器)

[OUTPUT]
FastAPI 应用实例：HTTP 服务入口，生命周期管理，中间件注册，Prometheus metrics暴露，
OpenAPI schema（含 bearerAuth security scheme 和 API 认证说明）

[POS]
应用入口。创建 FastAPI 实例，注册路由和中间件，管理启动/关闭生命周期。
`/api/v1` 下的路由组按需导入：启动只挂载 health 组，其余组在首个命中其路径的请求到达、或启动后的后台预加载时挂载；
OpenAPI 生成前加载全部路由组，文档与完全加载的路由表一致。
MCP 传输在没有注册信任闸时不做任何检查，所以信任闸随本模块导入而注册，不依赖哪个路由组被加载。
支持三种运行模式（Desktop/WebUI Local/WebUI Remote），根据环境变量动态配置监听地址和端口。
通过 _custom_openapi() 注入 bearerAuth security scheme，使 Swagger UI Authorize 按钮可用。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

# 导入即向 MCP 传输注册工作区信任闸；路由组按需加载后，不能再指望某个路由模块的导入链顺带注册它。
import myrm_agent_harness.agent.security.workspace_trust  # noqa: F401
from fastapi import FastAPI

from app.api.channels.channel_ingress import router as channel_ingress_router
from app.api.internal.agent_audit import router as internal_agent_audit_router
from app.api.internal.agent_interrupt import router as internal_agent_interrupt_router
from app.api.internal.background_shell_status import (
    router as internal_background_shell_status_router,
)
from app.api.internal.org_policy_sync.org_managed_approval_policy_sync import (
    router as internal_org_managed_approval_policy_sync_router,
)
from app.api.internal.org_policy_sync.org_mcp_sync import (
    router as internal_org_mcp_sync_router,
)
from app.api.internal.org_policy_sync.org_model_policy_sync import (
    frontend_router as org_model_policy_frontend_router,
)
from app.api.internal.org_policy_sync.org_model_policy_sync import (
    router as internal_org_model_policy_sync_router,
)
from app.api.internal.skills_killswitch import (
    router as internal_skills_killswitch_router,
)
from app.api.mem0_compat.router import mem0_compat_router
from app.api.openai_compat.router import openai_compat_router
from app.api.router import api_router, route_loader
from app.api.webui.router import router as webui_router
from app.config.logging import configure_logging
from app.config.settings import settings
from app.core.monitoring import FASTAPI_TELEMETRY
from app.core.security.integration_write_patterns import (
    register_server_integration_write_patterns,
)
from app.core.utils.errors import register_exception_handlers
from app.database.operations.db_operational_handlers import (
    register_database_operational_handlers,
)
from app.middleware.trailing_slash_alias import collect_slashed_router_paths, register_trailing_slash_aliases
from app.server.exceptions import general_exception_handler, not_found_handler
from app.server.lazy_routes import AttachedRouter, LazyRouteMiddleware
from app.server.lifespan import optimized_lifespan
from app.server.middlewares import register_middlewares
from app.server.openapi_security import OPENAPI_API_DESCRIPTION, install_custom_openapi

logger = logging.getLogger(__name__)

configure_logging()
register_server_integration_write_patterns()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=OPENAPI_API_DESCRIPTION,
    lifespan=optimized_lifespan,
    telemetry=FASTAPI_TELEMETRY,
)

app.state.route_loader = route_loader
install_custom_openapi(app, prepare=route_loader.load_all)

register_middlewares(app)

app.include_router(api_router, prefix=settings.api_prefix)
app.include_router(channel_ingress_router, prefix="/api")
app.include_router(internal_agent_interrupt_router, prefix="/api")
app.include_router(internal_agent_audit_router)
app.include_router(internal_background_shell_status_router)
app.include_router(internal_org_mcp_sync_router)
app.include_router(internal_org_model_policy_sync_router)
app.include_router(internal_org_managed_approval_policy_sync_router)
app.include_router(org_model_policy_frontend_router, prefix=settings.api_prefix)
app.include_router(internal_skills_killswitch_router)
app.include_router(openai_compat_router)
app.include_router(mem0_compat_router)
app.include_router(webui_router)

register_database_operational_handlers(app)
register_exception_handlers(app)
app.add_exception_handler(404, not_found_handler)
app.add_exception_handler(Exception, general_exception_handler)
# 必须在全部 include_router 之后：以已注册路由表为准，为以斜杠结尾的集合端点补齐「去斜杠」别名，
# 避免经 Next 代理（尾斜杠被吃掉）后触发跨源 307，导致桌面端会话/项目列表加载失败。
slash_aliases = register_trailing_slash_aliases(app)


def _alias_attached_routes(attached: Sequence[AttachedRouter]) -> None:
    """路由组按需挂载后，把该组的集合端点补进别名索引，与「路由表为唯一事实来源」保持一致。"""
    slash_aliases.add(
        path
        for mounted in attached
        for path in collect_slashed_router_paths(mounted.router, f"{settings.api_prefix}{mounted.prefix}")
    )


route_loader.on_attached(_alias_attached_routes)
# 必须最后挂载（即最外层）：请求命中的路由组要先于别名改写与路由匹配完成挂载。
app.add_middleware(LazyRouteMiddleware, loader=route_loader, api_prefix=settings.api_prefix)


@app.get("/health")
async def health_check() -> str:
    return "ok"


if __name__ == "__main__":
    import uvicorn

    from app.config.deploy_mode import is_webui_mode

    if is_webui_mode():
        port = settings.webui.port
        if settings.webui.allow_remote:
            host = "0.0.0.0"
            logger.info("Starting in WebUI Remote mode: %s:%d", host, port)
        else:
            host = "127.0.0.1"
            logger.info("Starting in WebUI Local mode: %s:%d", host, port)
    else:
        host = "127.0.0.1"
        port = settings.port
        logger.info("Starting in Desktop Sidecar mode: %s:%d", host, port)

    uvicorn.run(app, host=host, port=port)
