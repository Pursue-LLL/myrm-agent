"""
[POS] tests/api/projects/test_dependency_expansion_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.projects.dependency_expansion, app.services.project.architecture_dependency_service
[OUTPUT] test_register_nodes_and_edges_api, test_cascade_dependency_expansion_api, test_complexity_classification_dual_track_api, test_isolated_node_expansion_api

Unit test suite for Architectural Dependency Graph Expansion and Adaptive Complexity Dual-Track API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.projects.dependency_expansion import (
    router as dependency_expansion_router,
)
from app.services.project.architecture_dependency_service import (
    ArchitectureDependencyService,
    get_architecture_dependency_service,
)


@pytest.fixture
def dependency_expansion_test_client() -> Generator[
    tuple[TestClient, ArchitectureDependencyService], None, None
]:
    """Provide isolated TestClient mounting dependency_expansion router with clean service instance."""
    service = ArchitectureDependencyService()

    test_app = FastAPI()
    test_app.include_router(dependency_expansion_router, prefix="/api")
    test_app.dependency_overrides[get_architecture_dependency_service] = (
        lambda: service
    )

    with TestClient(test_app) as client:
        yield client, service


def test_register_nodes_and_edges_api(
    dependency_expansion_test_client: tuple[
        TestClient, ArchitectureDependencyService
    ],
) -> None:
    """Verify registering cross-stack nodes and typed dependency edges via API."""
    client, _ = dependency_expansion_test_client
    project_id = "test-proj-topo"

    # 1. 注册前端组件节点
    node_payload: dict[str, object] = {
        "node_id": "comp-dashboard",
        "node_type": "component",
        "name": "MetricsDashboard",
        "file_path": "src/components/MetricsDashboard.tsx",
        "description": "监控大屏核心看板",
    }
    resp = client.post(
        f"/api/projects/{project_id}/dependencies/nodes", json=node_payload
    )
    assert resp.status_code == 201
    created_node = resp.json()
    assert created_node["node_id"] == "comp-dashboard"
    assert created_node["node_type"] == "component"

    # 2. 注册后端 API 节点
    api_payload: dict[str, object] = {
        "node_id": "api-metrics",
        "node_type": "api",
        "name": "GET /api/v1/metrics",
        "file_path": "app/api/metrics.py",
        "description": "实时指标查询接口",
    }
    resp_api = client.post(
        f"/api/projects/{project_id}/dependencies/nodes", json=api_payload
    )
    assert resp_api.status_code == 201

    # 3. 注册关联边
    edge_payload: dict[str, object] = {
        "source_id": "comp-dashboard",
        "target_id": "api-metrics",
        "edge_type": "calls",
        "description": "前端按需发起数据获取",
    }
    resp_edge = client.post(
        f"/api/projects/{project_id}/dependencies/edges", json=edge_payload
    )
    assert resp_edge.status_code == 201
    created_edge = resp_edge.json()
    assert created_edge["source_id"] == "comp-dashboard"
    assert created_edge["edge_type"] == "calls"


def test_cascade_dependency_expansion_api(
    dependency_expansion_test_client: tuple[
        TestClient, ArchitectureDependencyService
    ],
) -> None:
    """Verify cascading dependency expansion extracts constraints, rejected alternatives, and calculates blast radius."""
    client, _ = dependency_expansion_test_client
    project_id = "test-proj-cascade"

    # 构建链路: UI组件 ➔ API ➔ 数据模型 ➔ 约束 + 否决项
    nodes = [
        {
            "node_id": "ui-kpi",
            "node_type": "component",
            "name": "KpiWidget",
            "description": "关键指标卡片",
        },
        {
            "node_id": "api-kpi",
            "node_type": "api",
            "name": "GET /api/kpi",
            "description": "KPI聚合服务",
        },
        {
            "node_id": "model-kpi",
            "node_type": "data_model",
            "name": "KpiRecord",
            "description": "KPI物理表",
        },
        {
            "node_id": "const-atomic",
            "node_type": "architectural_decision",
            "name": "原子事务保证",
            "description": "读写操作必须持有写锁",
        },
        {
            "node_id": "rej-mem-cache",
            "node_type": "architectural_decision",
            "name": "否决纯本地无锁内存缓存",
            "description": "多实例下出现脏读，已明确否决",
        },
    ]
    for n in nodes:
        client.post(f"/api/projects/{project_id}/dependencies/nodes", json=n)

    edges = [
        {
            "source_id": "ui-kpi",
            "target_id": "api-kpi",
            "edge_type": "calls",
        },
        {
            "source_id": "api-kpi",
            "target_id": "model-kpi",
            "edge_type": "binds_model",
        },
        {
            "source_id": "model-kpi",
            "target_id": "const-atomic",
            "edge_type": "constrained_by",
        },
        {
            "source_id": "ui-kpi",
            "target_id": "rej-mem-cache",
            "edge_type": "rejected_alternative",
        },
    ]
    for e in edges:
        client.post(f"/api/projects/{project_id}/dependencies/edges", json=e)

    # 发起展开
    expand_req = {"target_node_id": "ui-kpi", "max_depth": 3}
    resp = client.post(
        f"/api/projects/{project_id}/dependencies/expand", json=expand_req
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["target_node_id"] == "ui-kpi"
    assert len(res_data["visited_nodes"]) == 5
    assert res_data["blast_radius_score"] > 0.0
    assert len(res_data["critical_constraints"]) >= 1
    assert "原子事务保证" in res_data["critical_constraints"][0]
    assert len(res_data["rejected_alternatives"]) >= 1
    assert "否决纯本地无锁内存缓存" in res_data["rejected_alternatives"][0]
    assert (
        "<architectural_dependency_graph>"
        in res_data["formatted_expansion_block"]
    )


def test_complexity_classification_dual_track_api(
    dependency_expansion_test_client: tuple[
        TestClient, ArchitectureDependencyService
    ],
) -> None:
    """Verify adaptive dual-track classification routes light tasks to fast_lean and complex to full_workbench."""
    client, _ = dependency_expansion_test_client

    # 1. 轻量任务 (修改单个按钮) -> fast_lean
    light_req = {
        "task_prompt": "修改确认按钮的背景颜色为蓝色",
        "target_components_or_files": ["SubmitButton.tsx"],
        "is_multi_turn_project_session": False,
    }
    resp_light = client.post("/api/projects/complexity/classify", json=light_req)
    assert resp_light.status_code == 200
    data_light = resp_light.json()
    assert data_light["track"] == "fast_lean"
    assert data_light["bypass_state_sync"] is True
    assert data_light["estimated_token_overhead"] == 0

    # 2. 复杂重构跨栈任务 -> full_workbench
    complex_req = {
        "task_prompt": "全链路跨栈重构订单结算与库存扣减服务",
        "target_components_or_files": ["OrderService.ts", "Inventory.py"],
        "is_multi_turn_project_session": False,
    }
    resp_complex = client.post(
        "/api/projects/complexity/classify", json=complex_req
    )
    assert resp_complex.status_code == 200
    data_complex = resp_complex.json()
    assert data_complex["track"] == "full_workbench"
    assert data_complex["bypass_state_sync"] is False
    assert data_complex["estimated_token_overhead"] > 0


def test_isolated_node_expansion_api(
    dependency_expansion_test_client: tuple[
        TestClient, ArchitectureDependencyService
    ],
) -> None:
    """Verify expanding an isolated node returns zero blast radius without crashing."""
    client, _ = dependency_expansion_test_client
    project_id = "test-proj-isolated"

    client.post(
        f"/api/projects/{project_id}/dependencies/nodes",
        json={
            "node_id": "isolated-helper",
            "node_type": "component",
            "name": "IsolatedHelper",
        },
    )

    resp = client.post(
        f"/api/projects/{project_id}/dependencies/expand",
        json={"target_node_id": "isolated-helper"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["visited_nodes"]) == 1
    assert data["blast_radius_score"] == 0.0
    assert data["critical_constraints"] == []
