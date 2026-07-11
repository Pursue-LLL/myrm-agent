"""Public Ingress Resolver Core.

[INPUT]
- app.config.settings::settings (POS: 应用配置与环境变量)
- app.core.channel_bridge.config_loader::load_user_config_entry (POS: 用户配置加载)

[OUTPUT]
- get_public_ingress_base_url: 解析公网 Ingress 基础 URL
- invalidate_public_ingress_cache: 配置变更后失效缓存

[POS]
公网 Ingress 单一解析入口。供 Middleware、Webhook、Connect API 与前端 resolver 复用。
Users configure publicIngressBaseUrl manually (cpolar, NATAPP, frp, cloud hosting, etc.).
"""

from __future__ import annotations

import time

from app.config.settings import settings
from app.core.channel_bridge.config_loader import load_user_config_entry

_CACHE_TTL_SECONDS = 30.0
_cached_url: str | None = None
_cached_at: float = 0.0
_cached_cp_env: str = ""


def invalidate_public_ingress_cache() -> None:
    """Drop cached ingress URL after personalSettings or CP env changes."""
    global _cached_url, _cached_at, _cached_cp_env
    _cached_url = None
    _cached_at = 0.0
    _cached_cp_env = ""


async def get_public_ingress_base_url() -> str:
    """Get the computed public ingress base URL.

    Priority:
    1. CP_PUBLIC_INGRESS_URL (from SaaS Control Plane env injection)
    2. UserConfig.personalSettings.publicIngressBaseUrl (from user configuration)
    3. Empty string (fallback to local generation in frontend or standard proxy headers)

    Uses ``load_user_config_entry`` instead of ``load_user_configs`` so ingress
    resolution never requires a configured LLM provider (onboarding/readiness paths).

    Results are cached briefly so AuthMiddleware does not open a DB connection on
    every API request during SPA init bursts.

    Returns:
        The resolved URL without trailing slashes, or an empty string.
    """
    global _cached_url, _cached_at, _cached_cp_env

    cp_env = settings.cp_public_ingress_url or ""
    now = time.monotonic()
    if (
        _cached_url is not None
        and _cached_cp_env == cp_env
        and (now - _cached_at) < _CACHE_TTL_SECONDS
    ):
        return _cached_url

    url = cp_env
    if not url:
        personal = await load_user_config_entry("personalSettings")
        url = personal.get("publicIngressBaseUrl", "") if personal else ""

    url = url.strip()
    if url.endswith("/"):
        url = url[:-1]

    _cached_url = url
    _cached_at = now
    _cached_cp_env = cp_env
    return url


__all__ = ["get_public_ingress_base_url", "invalidate_public_ingress_cache"]
