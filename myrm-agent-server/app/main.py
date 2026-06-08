"""FastAPI 应用程序入口

[INPUT]
app.api::api_router (POS: API 路由聚合)
app.server.lifespan::optimized_lifespan (POS: 生命周期函数)
app.config.settings::settings (POS: 统一配置中心)

[OUTPUT]
FastAPI 应用实例：HTTP 服务入口，生命周期管理，中间件注册，Prometheus metrics暴露

[POS]
应用入口。创建 FastAPI 实例，注册路由和中间件，管理启动/关闭生命周期。
支持三种运行模式（Desktop/WebUI Local/WebUI Remote），根据环境变量动态配置监听地址和端口。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.ai_agents.general_agent.tools import (
    _tool_layer_bootstrap,  # noqa: F401 — side-effect import: registers server-layer tools into harness _TOOL_LAYERS
)
from app.api.internal.agent_interrupt import router as internal_agent_interrupt_router
from app.api.internal.skills_killswitch import router as internal_skills_killswitch_router
from app.api.channels.channel_ingress import router as channel_ingress_router
from app.api.openai_compat.router import openai_compat_router
from app.api.router import api_router
from app.api.webui.router import router as webui_router
from app.config.logging import configure_logging
from app.config.settings import settings
from app.core.utils.errors import register_exception_handlers
from app.database.db_operational_handlers import register_database_operational_handlers
from app.server.exceptions import general_exception_handler, not_found_handler
from app.server.lifespan import optimized_lifespan
from app.server.middlewares import register_middlewares

logger = logging.getLogger(__name__)

configure_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI Agent后端服务",
    lifespan=optimized_lifespan,
)

register_middlewares(app)

app.include_router(api_router, prefix=settings.api_prefix)
app.include_router(channel_ingress_router, prefix="/api")
app.include_router(internal_agent_interrupt_router, prefix="/api")
app.include_router(internal_skills_killswitch_router)
app.include_router(openai_compat_router)
app.include_router(webui_router)

app.add_exception_handler(404, not_found_handler)
app.add_exception_handler(Exception, general_exception_handler)

register_exception_handlers(app)
register_database_operational_handlers(app)


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
