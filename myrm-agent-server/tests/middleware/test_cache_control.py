"""CacheControlMiddleware 路径级缓存策略测试。

[INPUT]
- app.middleware.cache（POS: 路径前缀 -> Cache-Control 的策略表与中间件）

[OUTPUT]
- 锁定「智能体读接口不得被浏览器缓存」：写操作（删除密钥、实例化模板）落在不同 URL 上，
  浏览器不会淘汰已缓存的列表，缓存会让回读拿到旧值
- 锁定其余策略行与「仅 GET、不覆盖已有缓存头」的中间件语义

[POS]
中间件层回归测试。
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.middleware.cache import CacheControlMiddleware, get_cache_max_age

NO_CACHE = "no-cache, no-store, must-revalidate"

AGENT_READ_PATHS = (
    "/api/v1/user-agents",
    "/api/v1/user-agents/builtin-automation",
    "/api/v1/user-agents/builtin-automation/secrets",
    "/api/v1/user-agents/builtin-automation/history",
    "/api/v1/user-agents/builtin-automation/snapshots",
)


async def _ok(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def _with_own_cache_header(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"}, headers={"Cache-Control": "public, max-age=5"})


def _client() -> TestClient:
    app = Starlette(
        routes=[
            *(Route(path, _ok, methods=["GET", "DELETE"]) for path in AGENT_READ_PATHS),
            Route("/api/v1/storage/skills/catalog", _ok, methods=["GET"]),
            Route("/api/v1/storage/users/skills", _ok, methods=["GET"]),
            Route("/api/v1/chats/c1", _ok, methods=["GET"]),
            Route("/api/v1/unlisted", _ok, methods=["GET"]),
            Route("/api/v1/user-agents/own-header", _with_own_cache_header, methods=["GET"]),
        ]
    )
    app.add_middleware(CacheControlMiddleware)
    return TestClient(app)


@pytest.mark.parametrize("path", AGENT_READ_PATHS)
def test_agent_reads_are_never_cached(path: str) -> None:
    assert get_cache_max_age(path) == 0
    assert _client().get(path).headers["Cache-Control"] == NO_CACHE


def test_other_policy_rows_keep_their_max_age() -> None:
    client = _client()
    assert client.get("/api/v1/storage/skills/catalog").headers["Cache-Control"] == "private, max-age=300"
    assert client.get("/api/v1/storage/users/skills").headers["Cache-Control"] == "private, max-age=60"
    assert client.get("/api/v1/chats/c1").headers["Cache-Control"] == NO_CACHE


def test_unlisted_paths_get_no_cache_header() -> None:
    assert get_cache_max_age("/api/v1/unlisted") is None
    assert "Cache-Control" not in _client().get("/api/v1/unlisted").headers


def test_only_get_requests_are_annotated() -> None:
    response = _client().delete("/api/v1/user-agents/builtin-automation/secrets")
    assert "Cache-Control" not in response.headers


def test_existing_cache_header_is_preserved() -> None:
    response = _client().get("/api/v1/user-agents/own-header")
    assert response.headers["Cache-Control"] == "public, max-age=5"
