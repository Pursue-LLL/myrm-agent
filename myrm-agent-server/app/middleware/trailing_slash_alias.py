"""Trailing-slash alias middleware.

[INPUT]
- ASGI scope（``http`` 请求的 ``path`` / ``raw_path``）
- ``register_trailing_slash_aliases`` 从 FastAPI 路由树采集的后缀斜杠路由全集；延迟挂载的路由组挂载后经 ``SlashedPathIndex.add`` 增补

[OUTPUT]
- ``SlashedPathIndex``：后缀斜杠路由全集（静态路径 O(1) 精确匹配 + 带路径参数的模板匹配），可随路由组加载增补
- ``TrailingSlashAliasMiddleware``：把命中「同一路由的去斜杠形式」的请求在路由前改写为斜杠形式
- ``iter_route_paths``：把路由树（含 ``include_router`` 嵌套）展开为完整路径
- ``collect_slashed_router_paths`` / ``collect_slashed_paths``：从单个路由器 / 整个应用的路由树采集后缀斜杠路径
- ``register_trailing_slash_aliases``：构建别名索引并挂载中间件，返回该索引

[POS]
传输层路径规范化中间件。桌面与 WebUI 经 Next ``rewrites`` 代理转发到后端时，``/api/v1/:path*``
会吃掉尾斜杠，令 FastAPI 的 ``redirect_slashes`` 对 ``/api/v1/chats`` 发出
``307 Location: http://127.0.0.1:8080/api/v1/chats/``：浏览器跟随该跨源跳转后因缺少
``Access-Control-Allow-Origin`` 直接失败，会话列表与项目列表因此加载失败（发送框随之锁死）。
这里在路由匹配前原地补齐尾斜杠，保持同源、零重定向、零请求体重复消费风险。
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable, Iterator

from fastapi import APIRouter, FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send


def _compile_templated_pattern(path: str) -> "re.Pattern[str]":
    """Turn ``/x/{param}/`` into a regex that matches one concrete segment in place of ``{param}``."""
    escaped = re.escape(path)
    return re.compile(r"^" + re.sub(r"\\\{[^}]*\\\}", "[^/]+", escaped) + r"$")


class SlashedPathIndex:
    """Canonical slashed route paths, queried per request and extended as route groups are mounted."""

    def __init__(self, paths: Iterable[str] = ()) -> None:
        self._lock = threading.Lock()
        self._paths: frozenset[str] = frozenset()
        # 静态集合根（/api/v1/chats/）走 O(1) 精确匹配；带路径参数的集合根
        # （/api/v1/public/artifact-share/{token}/、/mem0/v1/memories/{memory_id}/）
        # 必须按一段通配匹配，否则真实请求 /…/abc123 永远命中不了模板字符串。
        # 两者作为一个快照整体替换，读取方始终看到同一版本。
        self._snapshot: tuple[frozenset[str], tuple[re.Pattern[str], ...]] = (frozenset(), ())
        self.add(paths)

    def add(self, paths: Iterable[str]) -> None:
        with self._lock:
            self._paths = self._paths | frozenset(paths)
            static_paths = frozenset(path for path in self._paths if "{" not in path)
            templated_patterns = tuple(_compile_templated_pattern(path) for path in self._paths if "{" in path)
            self._snapshot = (static_paths, templated_patterns)

    def has_alias(self, candidate: str) -> bool:
        static_paths, templated_patterns = self._snapshot
        return candidate in static_paths or any(pattern.match(candidate) for pattern in templated_patterns)


class TrailingSlashAliasMiddleware:
    """Rewrite ``/x`` to ``/x/`` before routing when only ``/x/`` is registered."""

    def __init__(self, app: ASGIApp, index: SlashedPathIndex) -> None:
        self.app = app
        self._index = index

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http":
            path = scope.get("path") or ""
            if path and not path.endswith("/") and self._index.has_alias(f"{path}/"):
                scope = dict(scope)
                scope["path"] = f"{path}/"
                raw_path = scope.get("raw_path")
                if isinstance(raw_path, bytes):
                    scope["raw_path"] = raw_path + b"/"
        await self.app(scope, receive, send)


def iter_route_paths(routes: Iterable[object], prefix: str = "") -> Iterator[str]:
    """Yield full route paths across both flattened and lazily-included FastAPI routers."""
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            yield f"{prefix}{path}"
            continue
        inner_router = getattr(route, "original_router", None)
        if inner_router is None:
            continue
        include_context = getattr(route, "include_context", None)
        inner_prefix = getattr(include_context, "prefix", "") or ""
        yield from iter_route_paths(getattr(inner_router, "routes", ()), f"{prefix}{inner_prefix}")


def _slashed(paths: Iterable[str]) -> frozenset[str]:
    return frozenset(path for path in paths if len(path) > 1 and path.endswith("/"))


def collect_slashed_router_paths(router: APIRouter, prefix: str = "") -> frozenset[str]:
    """Full paths of ``router``'s collection roots when the router is mounted under ``prefix``."""
    return _slashed(iter_route_paths(router.routes, prefix))


def collect_slashed_paths(app: FastAPI) -> frozenset[str]:
    """Full paths of routes whose canonical form ends with ``/`` (the collection roots)."""
    return _slashed(iter_route_paths(app.routes))


def register_trailing_slash_aliases(app: FastAPI) -> SlashedPathIndex:
    """Mount the alias middleware from the registered route tree; returns the index it consults.

    Must run after every ``include_router`` call: the route tree is the single source of truth, so an
    endpoint only gains a no-slash alias by declaring its canonical slashed path. Routes mounted later
    (lazily loaded route groups) are added to the returned index.
    """
    index = SlashedPathIndex(collect_slashed_paths(app))
    app.add_middleware(TrailingSlashAliasMiddleware, index=index)
    return index
