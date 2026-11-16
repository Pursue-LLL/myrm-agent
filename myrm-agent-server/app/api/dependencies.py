"""API dependency injection.

[INPUT]
app.platform_utils::get_session_factory (POS: 数据库会话工厂)
app.config.settings::settings (POS: 统一配置中心)
app.services.agent.llm_access (POS: WebUI 配置驱动的 LLM 解析)
app.core.utils.session_id::is_safe_session_id (POS: session_id/chat_id 文件路径插值白名单校验)
app.core.utils.errors::not_found_error (POS: 统一的 404 错误构造)

[OUTPUT]
get_deploy_identity: 单机部署身份标识
get_db / get_db_session: 数据库会话依赖
get_workspace_root: 工作区根目录
get_llm_for_user: 用户 LLM 实例
require_internal_service_key: 内部服务密钥验证
require_safe_session_id: 路由器级守卫，路径参数 session_id 在白名单外一律 404，不触达存储
verify_voice_enabled: 语音交互特性门控

[POS]
API 层统一依赖注入入口。所有 FastAPI 端点的依赖应从此模块导入。
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import AsyncIterator

from fastapi import Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.deploy_identity import get_deploy_identity
from app.core.utils.errors import not_found_error
from app.core.utils.session_id import is_safe_session_id
from app.platform_utils.workspace_root import get_workspace_root
from app.services.agent.llm_access import (
    get_llm_for_user,
    get_optional_llm_for_user,
)

logger = logging.getLogger(__name__)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Async database session factory for FastAPI dependency injection."""
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield session


get_db = get_db_session


async def require_internal_service_key(
    x_service_key: str | None = Header(None, alias="X-Service-Key"),
) -> None:
    """Validate internal service key from X-Service-Key header."""
    from app.config.settings import settings

    expected_key = settings.internal_service_key.get_secret_value()

    if not expected_key:
        raise HTTPException(
            status_code=500,
            detail="Internal service key is not configured",
        )

    if not x_service_key:
        raise HTTPException(
            status_code=401,
            detail="Internal service key is required",
        )

    if not hmac.compare_digest(x_service_key, expected_key):
        raise HTTPException(
            status_code=403,
            detail="Invalid internal service key",
        )


def verify_voice_enabled() -> None:
    """Reject requests when voice_interaction feature is disabled."""
    from myrm_agent_harness.core.features import get_features

    if not get_features().enabled("voice_interaction"):
        raise HTTPException(
            status_code=403,
            detail="Voice interaction is disabled via Feature Gate",
        )


async def require_safe_session_id(request: Request) -> None:
    """Answer 404 for a path `session_id` outside the safe charset, before any handler uses it.

    Declared on a router, it covers every route of that router (nested routers included) that
    carries the parameter, so a route added later cannot skip the check; routes without it pass.
    404 rather than 400 so the response does not tell an unsafe id from an unknown one, and the id
    is not echoed back. Handlers then never build a storage key from such an id: the local storage
    backend rejects a NUL byte, a newline or `..` in a key, which fails the read instead of
    finding nothing.
    """
    session_id: str | None = request.path_params.get("session_id")
    if session_id is not None and not is_safe_session_id(session_id):
        raise not_found_error(resource="Session")


__all__ = [
    "get_deploy_identity",
    "get_db",
    "get_db_session",
    "get_llm_for_user",
    "get_optional_llm_for_user",
    "get_workspace_root",
    "require_internal_service_key",
    "require_safe_session_id",
    "verify_voice_enabled",
]
