"""API dependency injection.

[INPUT]
app.platform_utils::get_session_factory (POS: 数据库会话工厂)
app.config.settings::settings (POS: 统一配置中心)

[OUTPUT]
get_deploy_identity: 单机部署身份标识
get_db / get_db_session: 数据库会话依赖
get_workspace_root: 工作区根目录
get_llm_for_user: 用户 LLM 实例
require_internal_service_key: 内部服务密钥验证
verify_voice_enabled: 语音交互特性门控

[POS]
API 层统一依赖注入入口。所有 FastAPI 端点的依赖应从此模块导入。
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Header, HTTPException
from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_deploy_identity() -> str:
    """Return deploy-mode identity sentinel for single-tenant runtime.

    - 'sandbox' when running inside a control-plane sandbox
    - 'local' for desktop / local WebUI
    """
    from app.config.deploy_mode import get_deploy_mode

    mode = get_deploy_mode().value
    return "sandbox" if mode == "sandbox" else "local"


def get_workspace_root() -> Path:
    """Return the workspace root directory from settings, or cwd as fallback."""
    from app.config.settings import settings

    if hasattr(settings, "workspace_root") and settings.workspace_root:
        return Path(settings.workspace_root)
    return Path.cwd()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Async database session factory for FastAPI dependency injection."""
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield session


get_db = get_db_session


async def get_llm_for_user(model_id: str | None = None) -> BaseChatModel:
    """Return an LLM instance configured for the authenticated user."""
    from myrm_agent_harness.toolkits.llms import llm_manager

    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.model_resolver import resolve_model_config

    configs = await load_user_configs()

    if model_id:
        model_cfg = resolve_model_config(configs.providers_dict, model_override=model_id)
    else:
        model_cfg = configs.model_cfg

    llm: BaseChatModel = await llm_manager.get_llm_from_config(
        model_cfg, streaming=False, api_keys=getattr(model_cfg, "api_keys", None)
    )
    return llm


async def get_optional_llm_for_user(model_id: str | None = None) -> BaseChatModel:
    """Return an LLM instance or a dummy model if not configured (prevents 500 errors on UI load)."""
    try:
        return await get_llm_for_user(model_id)
    except Exception:
        from typing import Any

        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import BaseMessage
        from langchain_core.outputs import ChatResult

        class DummyChatModel(BaseChatModel):
            def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any | None = None, **kwargs: Any) -> ChatResult:
                raise NotImplementedError("LLM is not configured")
            @property
            def _llm_type(self) -> str:
                return "dummy"

        return DummyChatModel()


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


__all__ = [
    "get_deploy_identity",
    "get_db",
    "get_db_session",
    "get_llm_for_user",
    "get_optional_llm_for_user",
    "get_workspace_root",
    "require_internal_service_key",
    "verify_voice_enabled",
]
