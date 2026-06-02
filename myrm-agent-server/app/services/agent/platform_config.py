"""Platform-wide model/retrieval config from WebUI (UserConfig DB).

[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs (POS: UserConfig 加载与缓存)

[OUTPUT]
- load_platform_model_config: WebUI 默认 LLM ModelConfig
- build_platform_litellm_kwargs: LiteLLM 调用参数（无 env fallback）
- webui_model_preflight_warning: local/tauri 启动前 WebUI 模型缺失 warning（不阻塞）
- resolve_xai_search_config: 从 providers 解析 xAI 凭据

[POS]
业务级模型/检索配置入口。禁止从进程环境读取 LLM/Embedding 密钥。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from pathlib import Path

from myrm_agent_harness.agent.config import ConfigIncompleteError

from app.core.types import ModelConfig

logger = logging.getLogger(__name__)


def _user_config_table_exists() -> bool:
    """True when SQLite file exists and user_config table is present."""
    from app.config.settings import settings

    db_path = Path(settings.database.sqlite_path).expanduser()
    if not db_path.is_file():
        return False
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_config' LIMIT 1"
            ).fetchone()
            return row is not None
    except sqlite3.Error:
        return False


async def load_platform_model_config() -> ModelConfig:
    """Default model from WebUI providers / defaultModelConfig."""
    from app.core.channel_bridge.config_loader import load_user_configs

    configs = await load_user_configs()
    return configs.model_cfg


def webui_model_preflight_warning() -> str | None:
    """Return a warning if WebUI default model is missing (local/tauri only).

    Skipped under pytest and in sandbox deploy mode. Never blocks startup.
    """
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None

    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    if get_deployment_capabilities().skips_webui_model_preflight:
        return None

    if not _user_config_table_exists():
        return (
            "WebUI model configuration is not available yet (database not initialized). "
            "Configure Settings > Model Service before using agents."
        )

    try:
        cfg = asyncio.run(load_platform_model_config())
    except ConfigIncompleteError as exc:
        message = exc.user_friendly_message
        if isinstance(message, dict):
            detail = message.get("en") or message.get("zh") or str(exc)
        else:
            detail = str(exc)
        return (
            f"WebUI default model is not configured: {detail} "
            "(Settings > Model Service)"
        )
    except Exception as exc:
        logger.debug("WebUI model preflight check failed: %s", exc)
        return (
            "Could not verify WebUI model configuration. "
            "Configure Settings > Model Service before using agents."
        )

    api_key = str(cfg.api_key or "").strip()
    model = str(cfg.model or "").strip()
    if not api_key or not model:
        return (
            "WebUI default model is incomplete (missing API key or model name). "
            "Configure Settings > Model Service."
        )
    return None


async def build_platform_litellm_kwargs() -> dict[str, object]:
    """LiteLLM kwargs from WebUI default model (no env fallback)."""
    cfg = await load_platform_model_config()
    kwargs: dict[str, object] = {
        "model": cfg.model,
        "api_key": cfg.api_key,
    }
    if cfg.base_url:
        kwargs["api_base"] = cfg.base_url
    return kwargs


async def load_platform_retrieval_configs() -> tuple[object | None, object | None]:
    """Embedding and reranker configs from WebUI retrieval settings."""
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import extract_retrieval_models

    configs = await load_user_configs()
    retrieval = configs.retrieval_dict if isinstance(configs.retrieval_dict, dict) else None
    return extract_retrieval_models(retrieval)


async def require_platform_embedding_config() -> object:
    """Embedding config from WebUI; raises if not configured."""
    from myrm_agent_harness.agent.config import ConfigIncompleteError

    embedding_cfg, _ = await load_platform_retrieval_configs()
    if embedding_cfg is None:
        raise ConfigIncompleteError(
            user_friendly_message={
                "en": "Embedding model is not configured. Set it in Settings > Retrieval.",
                "zh": "未配置 Embedding 模型，请在设置 > 检索 中配置。",
            },
            technical_details="retrieval settings missing embedding config in WebUI UserConfig",
            resolution_steps=[
                "Go to Settings > Retrieval / Memory",
                "Configure an embedding provider and model",
            ],
            error_code="embedding_not_configured",
        )
    return embedding_cfg


def resolve_xai_search_config(
    providers_dict: dict[str, object] | None,
) -> tuple[str, str] | None:
    """Resolve xAI credentials from WebUI providers (no env fallback)."""
    if not isinstance(providers_dict, dict):
        return None

    rows = providers_dict.get("providers")
    if not isinstance(rows, list):
        return None

    for row in rows:
        if not isinstance(row, dict):
            continue
        api_url = str(row.get("apiUrl") or row.get("baseUrl") or "").strip()
        provider_id = str(row.get("id") or row.get("routingProfile") or "").lower()
        api_key = str(row.get("apiKey") or "").strip()
        if not api_key:
            continue
        if "x.ai" in api_url.lower() or provider_id.startswith("xai"):
            base = api_url.rstrip("/") if api_url else "https://api.x.ai/v1"
            return api_key, base

    return None
