"""Trailing-slash alias middleware 行为与集合端点契约测试。

[INPUT]
- app.middleware.trailing_slash_alias（POS: 去斜杠别名中间件与路由树采集）
- app.main::app（POS: 真实路由表，用于契约对账）

[OUTPUT]
- 覆盖别名改写、非别名透传、以及「别名集合与真实路由表一致」的漂移门禁

[POS]
中间件层回归测试。锁定桌面经 Next 代理后 `/api/v1/chats` 一类请求不再 307 跨源跳转。
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.middleware.trailing_slash_alias import (
    TrailingSlashAliasMiddleware,
    collect_slashed_paths,
)


def _build_app(slashed_paths: set[str]) -> Starlette:
    async def collection(_request):  # type: ignore[no-untyped-def]
        return JSONResponse({"ok": "collection"})

    async def other(_request):  # type: ignore[no-untyped-def]
        return JSONResponse({"ok": "other"})

    app = Starlette(
        routes=[
            Route("/chats/", collection, methods=["GET", "POST", "DELETE"]),
            Route("/chats/{chat_id}", other, methods=["GET"]),
        ]
    )
    app.add_middleware(TrailingSlashAliasMiddleware, slashed_paths=slashed_paths)
    return app


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_slash_free_request_reaches_the_slashed_route_without_redirect(method: str) -> None:
    client = TestClient(_build_app({"/chats/"}))

    # follow_redirects=False：断言这里根本不产生 3xx（桌面跨源跟随会因缺少 ACAO 失败）
    response = client.request(method, "/chats", follow_redirects=False)

    assert response.status_code == 200, response.headers.get("location")


def test_unrelated_paths_keep_their_original_routing() -> None:
    client = TestClient(_build_app({"/chats/"}), follow_redirects=False)

    assert client.get("/chats/abc").json() == {"ok": "other"}


def test_real_route_tree_alias_set_matches_openapi_contract() -> None:
    """别名集合必须与真实路由表一致：新增 `/x/` 集合端点时自动获得去斜杠别名。"""
    from app.main import app

    slashed = collect_slashed_paths(app)

    assert "/api/v1/chats/" in slashed
    assert "/api/v1/projects/" in slashed

    openapi_paths = set(app.openapi().get("paths", {}))
    documented = {path for path in openapi_paths if len(path) > 1 and path.endswith("/")}
    assert documented <= slashed, f"slashed OpenAPI paths missing from alias set: {sorted(documented - slashed)}"
