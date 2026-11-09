"""The memory routes the default WebUI calls are served even when Memory Labs is off, and the Labs-only ones are not.

[INPUT]
- app.api.memory.router (POS: 按 `MYRM_MEMORY_LABS` 开关决定挂载哪些路由，导入时求值)

[OUTPUT]
- Labs 关闭时，成长页知识图谱标签页与记忆证据抽屉依赖的两个接口仍可用；指挥中心的 Labs 专属接口、归档恢复、工具指引、画像笔记、首次见面、临时增量、认知时钟控制台、导入回滚预演与 6 组引擎控制台接口不挂载；与它们相邻的默认接口（活跃上报、导入回滚）仍挂载

[POS]
后端测试默认把 `MYRM_MEMORY_LABS` 设为 1（tests/conftest.py），挂在开关后面的接口因此永远测得到，
默认用户却会收到 404/405。本文件在开关关闭的路由上请求这两个接口，防止它们被重新收进开关；
同时断言只有 Labs 面板调用的接口不会对默认用户暴露。
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.api.memory.utils import get_crud_memory_manager
from app.config.settings import settings
from app.schemas.memory.command_center import MemoryEvidencePlaybackResponse

_ROUTER_MODULE = "app.api.memory.router"
_LAB_ONLY_PREFIXES = (
    "/api/memory/command-center/economics",
    "/api/memory/command-center/actions",
    "/api/memory/archive/restore",
    "/api/memory/tool-guidance",
    "/api/memory/profile-notes",
    "/api/memory/onboarding",
    "/api/memory/ephemeral-delta",
    "/api/memory/guardian/cognitive-clock/status",
    "/api/memory/guardian/cognitive-clock/trigger-t1",
    "/api/memory/import/rollback/dry-run",
    "/api/memory/score-honesty",
    "/api/memory/notebook",
    "/api/memory/two-layer-dialectic",
)


@contextmanager
def _memory_app(*, labs_enabled: bool) -> Iterator[FastAPI]:
    """The memory router as mounted for a given MYRM_MEMORY_LABS value; the module is reloaded because it reads the flag at import."""
    original = settings.memory_labs_enabled
    settings.memory_labs_enabled = labs_enabled
    try:
        memory_router = importlib.reload(importlib.import_module(_ROUTER_MODULE)).router
        app = FastAPI()
        app.include_router(memory_router, prefix="/api/memory")
        manager = MagicMock()
        manager.has_graph = False
        manager._graph = None
        app.dependency_overrides[get_db_session] = lambda: AsyncMock()
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager
        yield app
    finally:
        settings.memory_labs_enabled = original
        importlib.reload(importlib.import_module(_ROUTER_MODULE))


@pytest.fixture
def labs_off_app() -> Iterator[FastAPI]:
    """A user who never set MYRM_MEMORY_LABS."""
    with _memory_app(labs_enabled=False) as app:
        yield app


@pytest.fixture
def labs_on_app() -> Iterator[FastAPI]:
    with _memory_app(labs_enabled=True) as app:
        yield app


def test_journey_graph_tab_endpoint_is_served_without_labs(labs_off_app: FastAPI) -> None:
    response = TestClient(labs_off_app).get("/api/memory/command-center/graph")

    assert response.status_code == 200
    assert response.json()["graph_state"] == "storage_disabled"


def test_evidence_drawer_endpoint_is_served_without_labs(labs_off_app: FastAPI) -> None:
    playback = MemoryEvidencePlaybackResponse(status="not_found", source_id="chat-1")

    with patch(
        "app.api.memory.operations.evidence_playback.EvidencePlaybackService.get_playback",
        new=AsyncMock(return_value=playback),
    ):
        response = TestClient(labs_off_app).get("/api/memory/command-center/evidence/playback", params={"source_id": "chat-1"})

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"


def test_lab_only_routes_stay_unmounted_without_labs(labs_off_app: FastAPI) -> None:
    exposed = sorted(path for path in labs_off_app.openapi()["paths"] if path.startswith(_LAB_ONLY_PREFIXES))

    assert exposed == []


def test_default_routes_beside_lab_only_ones_stay_mounted_without_labs(labs_off_app: FastAPI) -> None:
    """The chat input reports activity and the migration wizard rolls back an import, both for every user."""
    paths = labs_off_app.openapi()["paths"]

    assert "post" in paths["/api/memory/guardian/cognitive-clock/activity"]
    assert "post" in paths["/api/memory/import/rollback"]


def test_every_lab_only_prefix_is_mounted_with_labs(labs_on_app: FastAPI) -> None:
    """Guards the test above against passing vacuously on a prefix that matches no route."""
    paths = list(labs_on_app.openapi()["paths"])

    unmatched = [prefix for prefix in _LAB_ONLY_PREFIXES if not any(path.startswith(prefix) for path in paths)]

    assert unmatched == []
