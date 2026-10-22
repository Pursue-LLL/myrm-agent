"""Optional router loading primitives.

[INPUT]
- importlib (POS: 按模块路径延迟导入可选路由)
- fastapi.APIRouter (POS: 目标 API 路由器)

[OUTPUT]
- OptionalRouterSpec: 可选路由的挂载元数据
- OptionalRouterReport: 注册结果（已注册 / 因依赖缺失跳过）
- load_optional_router: 延迟导入单个可选路由
- register_optional_routers: 批量挂载可选路由

[POS]
可选功能的依赖可能尚未就位（harness 侧模块未落地、工作区未提交等）。
单个可选功能缺失时只跳过该功能并记录告警，绝不让它导致整个 server import 失败。
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OptionalRouterSpec:
    """One optional router: import path plus how it is mounted."""

    alias: str
    module: str
    prefix: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OptionalRouterReport:
    """Outcome of an optional router registration pass."""

    registered: tuple[str, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()


def load_optional_router(spec: OptionalRouterSpec) -> tuple[Any | None, str | None]:
    """Import one optional router.

    Returns ``(router, None)`` on success and ``(None, reason)`` when the
    feature is not available in this checkout.
    """
    try:
        module = importlib.import_module(spec.module)
    except ModuleNotFoundError as exc:
        return None, f"{spec.module}: {exc}"
    router = getattr(module, "router", None)
    if router is None:
        return None, f"{spec.module}: module exposes no router"
    return router, None


def register_optional_routers(api_router: Any, specs: tuple[OptionalRouterSpec, ...]) -> OptionalRouterReport:
    """Mount every optional router that is importable in this checkout."""
    registered: list[str] = []
    skipped: list[tuple[str, str]] = []
    for spec in specs:
        router, reason = load_optional_router(spec)
        if router is None:
            logger.warning("Optional router %s disabled: %s", spec.alias, reason)
            skipped.append((spec.alias, reason or "unavailable"))
            continue
        api_router.include_router(router, prefix=spec.prefix, tags=list(spec.tags) or None)
        registered.append(spec.alias)
    return OptionalRouterReport(registered=tuple(registered), skipped=tuple(skipped))
