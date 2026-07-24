"""User config loader for channel agent execution.

Loads user configs from UserConfig table, parses into typed objects,
caches with 30s TTL. Call invalidate_user_configs_cache() after
config updates so load_user_configs returns fresh data.

## 缓存策略

- **TTL**: 30秒（config_cache 模块）
- **失效触发**: `config_service.set()` / `delete()` 成功后调用 `invalidate_user_configs_cache()`
- **自动清理**: 每次加载时清理过期缓存
- **键格式**: `user_id` → `(timestamp, UserConfigs)`

## 搜索服务配置

前端可配置多个搜索服务，每个服务通过 role 字段指定为主服务或备用服务。
未在 WebUI 配置时 ``search_cfg`` 为 ``None``；主服务遇到不可重试错误时可切换到备用服务。

[INPUT]
- app.database.models::UserConfig
- app.core.types::ModelConfig, MCPServerConfig
- app.services.config_encryption_service (敏感配置解密)
- app.core.channel_bridge.config_parsers::extract_active_search_config, is_search_user_configured

[OUTPUT]
- UserConfigs: typed config bundle (model/search/retrieval/MCP/voice/security/external_agents + search_is_user_configured flag)
- load_user_configs: async loader with TTL cache (auto-registers custom pricing)
- load_voice_config_only: lightweight voice-only loader (no model/provider dependency)
- invalidate_user_configs_cache: 配置变更后调用以清除缓存
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    from app.core.types import ModelConfig

logger = logging.getLogger(__name__)


def _coerce_config_dict(raw: object) -> dict[str, object] | None:
    """Normalize WebUI config values that may remain JSON strings after decrypt."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


@dataclass
class UserConfigs:
    """All user configs needed by ChannelAgentExecutor, loaded in a single DB query."""

    model_cfg: "ModelConfig"
    search_cfg: "SearchServiceConfig | None"
    search_is_user_configured: bool
    retrieval_dict: dict[str, object] | None
    personal_settings_dict: dict[str, object] | None
    mcp_dict: dict[str, object] | None
    org_mcp_dict: dict[str, object] | None = None
    providers_dict: dict[str, object] | None = None
    voice_dict: dict[str, object] | None = None
    security_config_dict: dict[str, object] | None = None
    external_agents_dict: dict[str, object] | None = None
    oauth_credentials_dict: dict[str, object] | None = None


async def load_user_configs() -> UserConfigs:
    """Load all user configs needed for channel agent execution in a single query.

    Results are cached in-memory with a 30s TTL to avoid repeated DB queries
    for high-frequency channel messages.
    """
    from app.core.channel_bridge.config_cache import (
        _get_cached,
        _set_cached,
        invalidate_user_configs_cache,
    )
    from app.core.channel_bridge.config_parsers import (
        extract_active_search_config,
        is_search_user_configured,
    )
    from app.core.channel_bridge.model_resolver import (
        _fallback_model_from_providers,
        register_custom_model_pricing,
    )

    import os

    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1":
        invalidate_user_configs_cache()

    cached = _get_cached("sandbox")
    if cached:
        return cached

    from sqlalchemy import select

    from app.core.types import ModelConfig
    from app.database.connection import get_session
    from app.database.models import UserConfig

    config_map: dict[str, dict[str, object]] = {}

    async with get_session() as session:
        rows = (
            (
                await session.execute(
                    select(UserConfig).where(
                        UserConfig.config_key.in_(
                            [
                                "default_model",
                                "defaultModelConfig",
                                "searchServices",
                                "retrieval",
                                "personalSettings",
                                "mcpServers",
                                "orgMcpServers",
                                "providers",
                                "voice",
                                "securityConfig",
                                "externalAgents",
                                "oauthCredentials",
                            ]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )

        from app.services.config.encryption import get_encryption_service

        service = get_encryption_service()

        for row in rows:
            value = row.config_value
            if row.is_encrypted:
                try:
                    if isinstance(value, str):
                        value = service.decrypt(value)
                    elif isinstance(value, dict) and isinstance(value.get("_cipher"), str):
                        value = service.decrypt(value["_cipher"])

                    # Handle double encryption
                    if isinstance(value, dict) and "_cipher" in value and len(value) == 1:
                        inner = value["_cipher"]
                        if isinstance(inner, str):
                            logger.warning(
                                "config_loader: config '%s' was double-encrypted, performing second decryption",
                                row.config_key,
                            )
                            value = service.decrypt(inner)
                except Exception:
                    logger.warning(
                        "config_loader: failed to decrypt '%s' for sandbox, skipping",
                        row.config_key,
                    )
                    continue
            if isinstance(value, str):
                import json

                try:
                    value = json.loads(value)
                except Exception:
                    pass
            config_map[row.config_key] = value

    providers_dict = config_map.get("providers")
    if isinstance(providers_dict, str):
        import json

        try:
            providers_dict = json.loads(providers_dict)
        except Exception:
            providers_dict = {}
    if not isinstance(providers_dict, dict):
        providers_dict = {}

    model_cfg_dict = config_map.get("default_model")
    if model_cfg_dict:
        model_cfg = ModelConfig.model_validate(model_cfg_dict)
    else:
        default_model_cfg = config_map.get("defaultModelConfig")
        if isinstance(default_model_cfg, dict) and isinstance(providers_dict, dict):
            providers_dict["defaultModelConfig"] = default_model_cfg
        model_cfg = _fallback_model_from_providers(providers_dict, "sandbox")

    search_services_raw = _coerce_config_dict(config_map.get("searchServices"))
    search_cfg = extract_active_search_config(search_services_raw)
    search_configured = is_search_user_configured(search_services_raw)

    register_custom_model_pricing(providers_dict)

    from app.core.channel_bridge.model_resolver import enrich_model_context_window

    model_cfg = enrich_model_context_window(model_cfg, providers_dict)

    result = UserConfigs(
        model_cfg=model_cfg,
        search_cfg=search_cfg,
        search_is_user_configured=search_configured,
        retrieval_dict=_coerce_config_dict(config_map.get("retrieval")),
        personal_settings_dict=_coerce_config_dict(config_map.get("personalSettings")),
        mcp_dict=_coerce_config_dict(config_map.get("mcpServers")),
        org_mcp_dict=_coerce_config_dict(config_map.get("orgMcpServers")),
        providers_dict=providers_dict,
        voice_dict=config_map.get("voice"),
        security_config_dict=config_map.get("securityConfig"),
        external_agents_dict=config_map.get("externalAgents"),
        oauth_credentials_dict=config_map.get("oauthCredentials"),
    )
    _set_cached("sandbox", result)
    return result


async def load_voice_config_only() -> dict[str, object] | None:
    """Load only the voice config dict for a user, without requiring model/provider configs."""
    return await _load_single_config("voice")


async def load_user_config_entry(config_key: str) -> dict[str, object] | None:
    """Load a single decrypted UserConfig entry by key."""
    return await _load_single_config(config_key)


async def _load_single_config(config_key: str) -> dict[str, object] | None:
    """Load a single config entry from UserConfig table, with decryption if needed."""
    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models import UserConfig

    async with get_session() as session:
        row = (
            await session.execute(
                select(UserConfig).where(
                    UserConfig.config_key == config_key,
                )
            )
        ).scalar_one_or_none()

    if not row:
        return None

    value = row.config_value
    if row.is_encrypted:
        from app.services.config.encryption import get_encryption_service

        service = get_encryption_service()
        if isinstance(value, str):
            value = service.decrypt(value)
        elif isinstance(value, dict) and isinstance(value.get("_cipher"), str):
            value = service.decrypt(value["_cipher"])

        if isinstance(value, dict) and "_cipher" in value and len(value) == 1:
            inner = value["_cipher"]
            if isinstance(inner, str):
                value = service.decrypt(inner)

    return value if isinstance(value, dict) else None


__all__ = [
    "UserConfigs",
    "load_user_configs",
    "load_user_config_entry",
    "load_voice_config_only",
]
