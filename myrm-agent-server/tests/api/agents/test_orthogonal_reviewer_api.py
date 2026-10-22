from __future__ import annotations

from typing import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.orthogonal_reviewer_router import router as orthogonal_reviewer_router
from app.services.agent.orthogonal_reviewer_service import OrthogonalReviewerService


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with isolated OrthogonalReviewerService attached."""
    OrthogonalReviewerService.reset_instance()
    app = FastAPI()
    app.include_router(orthogonal_reviewer_router)
    with TestClient(app) as test_client:
        yield test_client
    OrthogonalReviewerService.reset_instance()


def test_review_intent_api(client: TestClient) -> None:
    # 1. Intent drift: prompt requires hash check, but diff lacks it
    res = client.post(
        "/agents/orthogonal-reviewer/review-intent",
        json={
            "task_prompt": "必须实现跨机工件哈希校验完整性",
            "architecture_plan": "工件流式传输与 SHA-256 校验",
            "code_diff": "+def stream_artifact(data: str) -> None:\n+    pass",
            "files_touched": ["artifact_service.py"],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["perspective"] == "intent_alignment"
    assert not data["passed"]
    assert len(data["findings"]) >= 1
    assert any(f["category"] == "intent_drift" for f in data["findings"])
    assert any(f["severity"] == "critical" for f in data["findings"])


def test_review_blind_api(client: TestClient) -> None:
    # 2. Blind review: strictly detect prohibited Any type
    res = client.post(
        "/agents/orthogonal-reviewer/review-blind",
        json={
            "code_diff": "+def handle_request(payload: Any) -> Any:\n+    return payload",
            "files_touched": ["handler.py"],
            "public_signatures": None,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["perspective"] == "blind_clean_context"
    assert not data["passed"]
    assert any(f["category"] == "type_safety" for f in data["findings"])
    assert any("Any" in f["title"] for f in data["findings"])


def test_arbitrate_api(client: TestClient) -> None:
    session_id = "sess-arbiter-api-001"
    # Create two mock reports and send to arbitrate
    report_a = {
        "perspective": "intent_alignment",
        "findings": [
            {
                "finding_id": "f-a1",
                "reviewer": "intent_alignment",
                "severity": "warning",
                "category": "logic_flaw",
                "title": "缺乏重试机制",
                "description": "网络请求未配置幂等重试",
                "file_path": "net.py",
                "line_range": "L10-L20",
                "suggestion": "增加 retry 参数",
            }
        ],
        "passed": True,
        "summary": "通过但有警告",
        "execution_time_ms": 12.5,
    }
    report_b = {
        "perspective": "blind_clean_context",
        "findings": [
            {
                "finding_id": "f-b1",
                "reviewer": "blind_clean_context",
                "severity": "critical",
                "category": "boundary_edge_case",
                "title": "缺少空值检查",
                "description": "payload 索引可能越界",
                "file_path": "net.py",
                "line_range": "L15",
                "suggestion": "添加判空 guard",
            }
        ],
        "passed": False,
        "summary": "存在阻塞级缺陷",
        "execution_time_ms": 10.2,
    }

    res = client.post(
        "/agents/orthogonal-reviewer/arbitrate",
        json={
            "session_id": session_id,
            "report_a": report_a,
            "report_b": report_b,
        },
    )
    assert res.status_code == 200
    verdict = res.json()
    assert verdict["session_id"] == session_id
    assert not verdict["is_approved"]
    assert verdict["status"] == "blocked_auto_fix"
    assert verdict["max_severity"] == "critical"
    assert len(verdict["merged_findings"]) == 2
    assert len(verdict["auto_fix_prompts"]) >= 1


def test_full_review_flow_api(client: TestClient) -> None:
    session_id = "sess-full-review-002"
    res = client.post(
        "/agents/orthogonal-reviewer/full-review",
        json={
            "session_id": session_id,
            "task_prompt": "实现安全的整数计算模块",
            "architecture_plan": "计算加减乘除",
            "code_diff": "+def divide(a: int, b: int) -> float:\n+    return a / max(1, b)",
            "files_touched": ["calc.py"],
            "public_signatures": None,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == session_id
    assert data["report_a"]["passed"]
    assert data["report_b"]["passed"]
    assert data["verdict"]["is_approved"]
    assert data["verdict"]["status"] == "approved"


def test_get_verdict_and_auto_fix_api(client: TestClient) -> None:
    session_id = "sess-auto-fix-003"
    # 1. Trigger full review that fails on prohibited Any type
    client.post(
        "/agents/orthogonal-reviewer/full-review",
        json={
            "session_id": session_id,
            "task_prompt": "解析配置数据",
            "architecture_plan": "",
            "code_diff": "+def parse(data: Any) -> Any:\n+    return data",
            "files_touched": ["parser.py"],
        },
    )

    # 2. Get verdict
    res_get = client.get(f"/agents/orthogonal-reviewer/sessions/{session_id}/verdict")
    assert res_get.status_code == 200
    v1 = res_get.json()
    assert not v1["is_approved"]
    assert len(v1["merged_findings"]) >= 1
    finding_id = v1["merged_findings"][0]["finding_id"]

    # 3. Apply auto fix for that finding
    res_fix = client.post(
        f"/agents/orthogonal-reviewer/sessions/{session_id}/auto-fix",
        json={"finding_ids": [finding_id]},
    )
    assert res_fix.status_code == 200
    fix_data = res_fix.json()
    assert fix_data["applied_count"] == 1
    assert fix_data["remaining_critical_count"] == 0

    # 4. Check updated verdict is now approved
    res_get2 = client.get(f"/agents/orthogonal-reviewer/sessions/{session_id}/verdict")
    assert res_get2.status_code == 200
    v2 = res_get2.json()
    assert v2["is_approved"]
    assert v2["status"] == "approved"
