"""Public Ingress Resolver Core.

[INPUT]
- app.config.settings::settings (POS: 应用配置与环境变量)
- app.core.channel_bridge.config_loader::load_user_config_entry (POS: 用户配置加载)

[OUTPUT]
- get_public_ingress_base_url: 解析公网 Ingress 基础 URL
- set_runtime_tunnel_ingress: 设置或清除 Quick Tunnel 运行时 URL

[POS]
公网 Ingress 单一解析入口。供 Middleware、Webhook、Connect API 与前端 resolver 复用。
"""

from app.config.settings import settings
from app.core.channel_bridge.config_loader import load_user_config_entry

_runtime_tunnel_ingress: str | None = None


def set_runtime_tunnel_ingress(url: str | None) -> None:
    """Set or clear the active Quick Tunnel URL (local deployments only)."""
    global _runtime_tunnel_ingress
    if url is None:
        _runtime_tunnel_ingress = None
        return
    normalized = url.strip().rstrip("/")
    _runtime_tunnel_ingress = normalized or None


async def get_public_ingress_base_url() -> str:
    """Get the computed public ingress base URL.

    Priority:
    1. CP_PUBLIC_INGRESS_URL (from SaaS Control Plane env injection)
    2. Active Quick Tunnel runtime URL (when tunnel is running)
    3. UserConfig.personalSettings.publicIngressBaseUrl (from user configuration)
    4. Empty string (fallback to local generation in frontend or standard proxy headers)

    Uses ``load_user_config_entry`` instead of ``load_user_configs`` so ingress
    resolution never requires a configured LLM provider (onboarding/readiness paths).

    Returns:
        The resolved URL without trailing slashes, or an empty string.
    """
    url = settings.cp_public_ingress_url
    if not url and _runtime_tunnel_ingress:
        url = _runtime_tunnel_ingress
    if not url:
        personal = await load_user_config_entry("personalSettings")
        url = personal.get("publicIngressBaseUrl", "") if personal else ""

    url = url.strip()
    if url.endswith("/"):
        url = url[:-1]

    return url
