"""The memory routes the default WebUI calls are served even when Memory Labs is off.

[INPUT]
- app.api.memory.router (POS: 按 `MYRM_MEMORY_LABS` 开关决定挂载哪些路由，导入时求值)

[OUTPUT]
- Labs 关闭时，成长页知识图谱标签页与记忆证据抽屉依赖的两个接口仍可用；Labs 专属接口仍不挂载

[POS]
后端测试默认把 `MYRM_MEMORY_LABS` 设为 1（tests/conftest.py），挂在开关后面的接口因此永远测得到，
默认用户却会收到 404/405。本文件在开关关闭的路由上请求这两个接口，防止它们被重新收进开关。
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.api.memory.utils import get_crud_memory_manager
from app.config.settings import settings
from app.schemas.memory.command_center import MemoryEvidencePlaybackResponse

_ROUTER_MODULE = "app.api.memory.router"


@pytest.fixture
def labs_off_app() -> Iterator[FastAPI]:
    """The memory router as mounted for a user who never set MYRM_MEMORY_LABS."""
    original = settings.memory_labs_enabled
    settings.memory_labs_enabled = False
    try:
        labs_off_router = importlib.reload(importlib.import_module(_ROUTER_MODULE)).router
        app = FastAPI()
        app.include_router(labs_off_router, prefix="/api/memory")
        manager = MagicMock()
        manager.has_graph = False
        manager._graph = None
        app.dependency_overrides[get_db_session] = lambda: AsyncMock()
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager
        yield app
    finally:
        settings.memory_labs_enabled = original
        importlib.reload(importlib.import_module(_ROUTER_MODULE))


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


def test_lab_only_command_center_routes_stay_unmounted_without_labs(labs_off_app: FastAPI) -> None:
    paths = set(labs_off_app.openapi()["paths"])

    assert "/api/memory/command-center/economics" not in paths
    assert "/api/memory/command-center/actions" not in paths
