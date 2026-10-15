from __future__ import annotations

from typing import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.graph_triage_router import router as graph_triage_router
from app.services.agent.graph_triage_service import GraphTriageService


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with isolated GraphTriageService and graph_triage_router attached."""
    GraphTriageService.reset_instance()
    app = FastAPI()
    app.include_router(graph_triage_router)
    with TestClient(app) as test_client:
        yield test_client
    GraphTriageService.reset_instance()


def test_assess_task_applicability_api(client: TestClient) -> None:
    # 1. Simple single step task (typo fix)
    res_simple = client.post(
        "/agents/graph-triage/assess",
        json={"prompt": "修复一下错别字"},
    )
    assert res_simple.status_code == 200
    data_simple = res_simple.json()
    assert data_simple["verdict"] == "reject_to_single_agent"
    assert data_simple["category"] == "simple_single_step"
    assert data_simple["estimated_tokens_saved"] > 0
    assert "单 Agent" in data_simple["reason"]

    # 2. Exploratory conversation
    res_exp = client.post(
        "/agents/graph-triage/assess",
        json={"prompt": "我们来探讨一下多智能体未来的架构演进，你有什么建议？"},
    )
    assert res_exp.status_code == 200
    data_exp = res_exp.json()
    assert data_exp["verdict"] == "reject_to_conversational"
    assert data_exp["category"] == "exploratory_chat"
    assert "保持单 Agent 交互模式" in data_exp["reason"]

    # 3. Strictly sequential pipeline
    res_seq = client.post(
        "/agents/graph-triage/assess",
        json={
            "prompt": "数据分析四部曲",
            "subtasks": [
                {"id": "fetch", "deps": []},
                {"id": "clean", "deps": ["fetch"]},
                {"id": "aggregate", "deps": ["clean"]},
                {"id": "report", "deps": ["aggregate"]},
            ],
        },
    )
    assert res_seq.status_code == 200
    data_seq = res_seq.json()
    assert data_seq["verdict"] == "reject_to_linear_pipeline"
    assert data_seq["category"] == "strictly_sequential"
    assert "轻量线性流水线" in data_seq["reason"]

    # 4. Parallel heavyweight admission
    res_parallel = client.post(
        "/agents/graph-triage/assess",
        json={
            "prompt": "多模块微服务并发安全审计",
            "subtasks": [
                {"id": "auth_service", "deps": [], "heavy": True},
                {"id": "billing_service", "deps": [], "heavy": True},
                {"id": "inventory_service", "deps": [], "heavy": True},
                {"id": "synthesis_node", "deps": ["auth_service", "billing_service", "inventory_service"]},
            ],
        },
    )
    assert res_parallel.status_code == 200
    data_parallel = res_parallel.json()
    assert data_parallel["verdict"] == "admit_graph"
    assert data_parallel["category"] == "parallel_heavyweight"
    assert "准许激活多智能体图并发编排" in data_parallel["reason"]


def test_estimate_fanout_budget_api(client: TestClient) -> None:
    # 1. Within budget
    res_ok = client.post(
        "/agents/graph-triage/estimate-budget",
        json={
            "node_count": 3,
            "fanout_concurrency": 3,
            "prompt_tokens": 1000,
            "estimated_tokens_per_node": 10000,
            "max_tokens_cap": 100000,
            "max_cost_usd_cap": 2.0,
        },
    )
    assert res_ok.status_code == 200
    data_ok = res_ok.json()
    assert not data_ok["is_circuit_broken"]
    assert data_ok["recommendation"] == "ALLOW"
    assert data_ok["total_estimated_tokens"] > 0

    # 2. Exceeding hard cap
    res_exceed = client.post(
        "/agents/graph-triage/estimate-budget",
        json={
            "node_count": 20,
            "fanout_concurrency": 8,
            "prompt_tokens": 2000,
            "estimated_tokens_per_node": 20000,
            "max_tokens_cap": 100000,
            "max_cost_usd_cap": 0.5,
        },
    )
    assert res_exceed.status_code == 200
    data_exceed = res_exceed.json()
    assert data_exceed["is_circuit_broken"]
    assert "INTERCEPT" in data_exceed["recommendation"]


def test_configure_session_guard_api(client: TestClient) -> None:
    session_id = "sess-guard-test-001"
    res = client.post(
        f"/agents/graph-triage/sessions/{session_id}/configure",
        json={
            "max_tokens": 80000,
            "max_cost_usd": 1.5,
            "warning_threshold_pct": 0.25,
            "critical_threshold_pct": 0.08,
            "initial_concurrency": 6,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == session_id
    assert data["remaining_tokens"] == 80000
    assert data["budget_status"] == "healthy"
    assert data["active_concurrency"] == 6
    assert not data["is_throttled"]
    assert not data["is_circuit_broken"]


def test_update_session_spend_and_status_api(client: TestClient) -> None:
    session_id = "sess-spend-lifecycle-002"
    # 1. Initial configuration
    client.post(
        f"/agents/graph-triage/sessions/{session_id}/configure",
        json={
            "max_tokens": 100000,
            "max_cost_usd": 2.0,
            "warning_threshold_pct": 0.3,
            "critical_threshold_pct": 0.1,
            "initial_concurrency": 4,
        },
    )

    # 2. Spend 50k tokens (remaining 50% -> healthy)
    res_spend_1 = client.post(
        f"/agents/graph-triage/sessions/{session_id}/update-spend",
        json={"incremental_tokens": 50000},
    )
    assert res_spend_1.status_code == 200
    d1 = res_spend_1.json()
    assert d1["budget_status"] == "healthy"
    assert not d1["is_throttled"]
    assert d1["active_concurrency"] == 4

    # 3. Spend another 25k tokens (total 75k, remaining 25% <= 30% -> warning)
    res_spend_2 = client.post(
        f"/agents/graph-triage/sessions/{session_id}/update-spend",
        json={"incremental_tokens": 25000},
    )
    assert res_spend_2.status_code == 200
    d2 = res_spend_2.json()
    assert d2["budget_status"] == "warning"
    assert d2["is_throttled"]
    assert d2["active_concurrency"] == 2

    # 4. Check status endpoint
    res_status = client.get(f"/agents/graph-triage/sessions/{session_id}/status")
    assert res_status.status_code == 200
    d_status = res_status.json()
    assert d_status["current_tokens"] == 75000
    assert d_status["budget_status"] == "warning"

    # 5. Spend another 18k tokens (total 93k, remaining 7% <= 10% -> critical)
    res_spend_3 = client.post(
        f"/agents/graph-triage/sessions/{session_id}/update-spend",
        json={"incremental_tokens": 18000},
    )
    assert res_spend_3.status_code == 200
    d3 = res_spend_3.json()
    assert d3["budget_status"] == "critical"
    assert d3["is_throttled"]
    assert not d3["is_circuit_broken"]
    assert d3["active_concurrency"] == 1

    # 6. Spend another 10k tokens (total 103k -> exhausted)
    res_spend_4 = client.post(
        f"/agents/graph-triage/sessions/{session_id}/update-spend",
        json={"incremental_tokens": 10000},
    )
    assert res_spend_4.status_code == 200
    d4 = res_spend_4.json()
    assert d4["budget_status"] == "exhausted"
    assert d4["is_circuit_broken"]
    assert d4["active_concurrency"] == 0


def test_execute_early_reduce_api(client: TestClient) -> None:
    session_id = "sess-early-reduce-003"
    # Configure and spend up to critical
    client.post(
        f"/agents/graph-triage/sessions/{session_id}/configure",
        json={"max_tokens": 50000, "critical_threshold_pct": 0.15},
    )
    client.post(
        f"/agents/graph-triage/sessions/{session_id}/update-spend",
        json={"incremental_tokens": 45000},
    )

    # Perform early reduce
    res = client.post(
        f"/agents/graph-triage/sessions/{session_id}/early-reduce",
        json={
            "total_planned_tokens": 60000,
            "nodes": [
                {
                    "node_id": "service_scanner",
                    "status": "completed",
                    "result_summary": "Scanned 14 HTTP routes without CVEs.",
                    "tokens_used": 20000,
                },
                {
                    "node_id": "db_checker",
                    "status": "completed",
                    "result_summary": "Audited SQL migrations, 0 injection risks.",
                    "tokens_used": 25000,
                },
                {
                    "node_id": "load_tester",
                    "status": "pending",
                    "result_summary": "",
                    "tokens_used": 0,
                },
            ],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == session_id
    assert len(data["completed_nodes"]) == 2
    assert "service_scanner" in data["completed_nodes"]
    assert "db_checker" in data["completed_nodes"]
    assert data["unexecuted_nodes"] == ["load_tester"]
    assert data["tokens_spent"] == 45000
    assert data["tokens_saved"] == 15000
    assert data["delivery_confidence"] == 0.67
    assert "Graceful Early Reduce Triggered" in data["summary"]
