"""Optional agent router registry.

[INPUT]
- app.api._optional_routers (POS: 可选路由延迟加载原语)
- app.api.agents.* (POS: 可选 Agent 功能路由模块)

[OUTPUT]
- AGENT_ROUTER_SPECS: Agent 可选路由挂载表
- register_agent_routers: 把可导入的 Agent 可选路由挂到目标路由器

[POS]
可选 Agent 功能（自治循环、多 Bot、团队编组等）依赖 harness 侧同名模块。harness 尚未提供时，
该功能整体跳过并记录告警；绝不让单个可选功能缺失导致整个 server import 失败。
"""

from __future__ import annotations

from app.api._optional_routers import OptionalRouterSpec, register_optional_routers

AGENT_ROUTER_SPECS: tuple[OptionalRouterSpec, ...] = (

)


def register_agent_routers(
    api_router: object,
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Mount every optional agent router that imports successfully."""
    report = register_optional_routers(api_router, AGENT_ROUTER_SPECS)
    return report.registered, report.skipped
