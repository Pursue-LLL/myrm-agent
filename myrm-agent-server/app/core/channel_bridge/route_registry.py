"""Runtime holder for dynamically registered channel HTTP route registry.

[INPUT]
- app.channels.implementations.fastapi::ChannelRouteRegistry (POS: 渠道 HTTP 路由注册器)

[OUTPUT]
- set_route_registry, get_route_registry

[POS]
channel_bridge 路由注册表持有者。startup 写入、routes management API 读取。
"""

from __future__ import annotations

_registry_instance: object | None = None


def set_route_registry(registry: object) -> None:
    """Store the ChannelRouteRegistry instance after FastAPI registration."""
    global _registry_instance
    _registry_instance = registry


def get_route_registry() -> object | None:
    """Return the registered ChannelRouteRegistry, if startup completed."""
    return _registry_instance
