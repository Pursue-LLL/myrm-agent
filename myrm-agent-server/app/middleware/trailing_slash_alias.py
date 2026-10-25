"""Trailing-slash alias middleware.

[INPUT]
- ASGI scope（``http`` 请求的 ``path`` / ``raw_path``）
- ``register_trailing_slash_aliases`` 从 FastAPI 路由树采集的后缀斜杠路由全集

[OUTPUT]
- ``TrailingSlashAliasMiddleware``：把命中「同一路由的去斜杠形式」的请求在路由前改写为斜杠形式
- ``register_trailing_slash_aliases``：构建别名集合并挂载中间件，返回别名端点数量

[POS]
传输层路径规范化中间件。桌面与 WebUI 经 Next ``rewrites`` 代理转发到后端时，``/api/v1/:path*``
会吃掉尾斜杠，令 FastAPI 的 ``redirect_slashes`` 对 ``/api/v1/chats`` 发出
``307 Location: http://127.0.0.1:8080/api/v1/chats/``：浏览器跟随该跨源跳转后因缺少
``Access-Control-Allow-Origin`` 直接失败，会话列表与项目列表因此加载失败（发送框随之锁死）。
这里在路由匹配前原地补齐尾斜杠，保持同源、零重定向、零请求体重复消费风险。
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable, Iterator
from typing import Any

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


def _compile_templated_pattern(path: str) -> "re.Pattern[str]":
    """Turn ``/x/{param}/`` into a regex that matches one concrete segment in place of ``{param}``."""
    escaped = re.escape(path)
    return re.compile(r"^" + re.sub(r"\\\{[^}]*\\\}", "[^/]+", escaped) + r"$")


class TrailingSlashAliasMiddleware:
    """Rewrite ``/x`` to ``/x/`` before routing when only ``/x/`` is registered."""

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]], slashed_paths: Iterable[str]) -> None:
        self.app = app
        paths = frozenset(slashed_paths)
        # 静态集合根（/api/v1/chats/）走 O(1) 精确匹配；带路径参数的集合根
        # （/api/v1/public/artifact-share/{token}/、/mem0/v1/memories/{memory_id}/）
        # 必须按一段通配匹配，否则真实请求 /…/abc123 永远命中不了模板字符串。
        self._static_paths = frozenset(path for path in paths if "{" not in path)
        self._templated_patterns = tuple(_compile_templated_pattern(path) for path in paths if "{" in path)

    def _has_slashed_alias(self, candidate: str) -> bool:
        return candidate in self._static_paths or any(p.match(candidate) for p in self._templated_patterns)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http":
            path = scope.get("path") or ""
            if path and not path.endswith("/") and self._has_slashed_alias(f"{path}/"):
                scope = dict(scope)
                scope["path"] = f"{path}/"
                raw_path = scope.get("raw_path")
                if isinstance(raw_path, bytes):
                    scope["raw_path"] = raw_path + b"/"
        await self.app(scope, receive, send)


def _iter_route_paths(routes: Iterable[Any], prefix: str = "") -> Iterator[str]:
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
        yield from _iter_route_paths(getattr(inner_router, "routes", ()), f"{prefix}{inner_prefix}")


def collect_slashed_paths(app: Any) -> frozenset[str]:
    """Full paths of routes whose canonical form ends with ``/`` (the collection roots)."""
    return frozenset(path for path in _iter_route_paths(getattr(app, "routes", ())) if len(path) > 1 and path.endswith("/"))


def register_trailing_slash_aliases(app: Any) -> int:
    """Mount the alias middleware from the registered route tree; returns the alias count.

    Must run after every ``include_router`` call: the route tree is the single source of truth, so an
    endpoint only gains a no-slash alias by declaring its canonical slashed path.
    """
    slashed_paths = collect_slashed_paths(app)
    app.add_middleware(TrailingSlashAliasMiddleware, slashed_paths=slashed_paths)
    return len(slashed_paths)
