"""Integration tests for Four-Layer Memory Tri-Channel Promotion API endpoints.

[INPUT]
- fastapi::FastAPI
- starlette.testclient::TestClient
- app.api.memory.four_layer_promotion_router::router

[OUTPUT]
- Pytest cases verifying Map extraction, Reduce tri-channel promotion, compliance, and rollback

[POS]
Server-side integration testing for Hermes-grade two-step consolidation and anti-poisoning audit.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.four_layer_promotion_router import (
    router as four_layer_promotion_router,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(four_layer_promotion_router, prefix="/api/memory")
    with TestClient(app) as test_client:
        yield test_client


def test_four_layer_promotion_map_endpoint(client: TestClient) -> None:
    map_payload = {
        "session_id": "sess-beijing-trip",
        "events": [
            {
                "id": "evt-101",
                "content": "故宫与环球影城规划在同一天导致时间严重冲突",
                "failed": True,
                "explicit_instruction": False,
            }
        ],
        "exposure_source": "internal_chat",
    }
    resp = client.post("/api/memory/four-layer-promotion/map", json=map_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-beijing-trip"
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["has_tool_failure"] is True
    assert "evt-101" in data["candidates"][0]["supported_event_ids"]


def test_four_layer_promotion_reduce_and_promote(client: TestClient) -> None:
    reduce_payload = {
        "candidates": [
            {
                "statement": "核心大景区必须单独占用一整天",
                "supported_event_ids": ["evt-101"],
                "session_id": "sess-beijing-trip",
                "exposure_source": "internal_chat",
                "has_tool_failure": True,
                "is_explicit_user_instruction": False,
            }
        ]
    }
    resp = client.post("/api/memory/four-layer-promotion/reduce", json=reduce_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["batch_id"].startswith("batch-")
    assert len(data["promoted_methods"]) == 1
    assert data["promoted_methods"][0]["promotion_channel"] == "tool_failure_evidence"
    assert len(data["decisions"]) == 1
    assert data["decisions"][0]["promoted"] is True


def test_four_layer_promotion_verify_compliance_and_rollback(client: TestClient) -> None:
    # 1. Promote a method first
    reduce_payload = {
        "candidates": [
            {
                "statement": "兵马俑和回民街不能塞在同一天",
                "supported_event_ids": ["evt-202"],
                "session_id": "sess-xian-trip",
                "exposure_source": "internal_chat",
                "has_tool_failure": True,
                "is_explicit_user_instruction": False,
            }
        ]
    }
    reduce_resp = client.post("/api/memory/four-layer-promotion/reduce", json=reduce_payload)
    assert reduce_resp.status_code == 200
    reduce_data = reduce_resp.json()
    batch_id = reduce_data["batch_id"]
    method_id = reduce_data["promoted_methods"][0]["method_id"]

    # 2. Check compliance on text
    verify_resp = client.post(
        "/api/memory/four-layer-promotion/verify-compliance",
        json={"response_text": "建议行程安排合理，没有任何错误"},
    )
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["all_compliant"] is True

    # 3. Rollback the batch
    rollback_resp = client.post(
        "/api/memory/four-layer-promotion/rollback",
        json={"batch_id": batch_id},
    )
    assert rollback_resp.status_code == 200
    rollback_data = rollback_resp.json()
    assert rollback_data["success"] is True
    assert method_id in rollback_data["reverted_method_ids"]
