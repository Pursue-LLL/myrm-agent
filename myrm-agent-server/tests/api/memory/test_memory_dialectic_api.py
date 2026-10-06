"""
[POS] tests/api/memory/test_memory_dialectic_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.dialectic, app.services.memory.memory_dialectic_service
[OUTPUT] test_process_turn_cold_boot_api, test_process_turn_cadence_throttling_api, test_get_cadence_status_api, test_get_ephemeral_mind_api, test_reset_cadence_session_api

Unit test suite for Dialectic Profile Reasoning and Adaptive Context Cadence API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.dialectic import router as memory_dialectic_router
from app.services.memory.memory_dialectic_service import (
    MemoryDialecticService,
    get_memory_dialectic_service,
)


@pytest.fixture
def dialectic_test_client() -> Generator[
    tuple[TestClient, MemoryDialecticService], None, None
]:
    """Provide isolated TestClient mounting dialectic router with clean service instance."""
    service = MemoryDialecticService()

    test_app = FastAPI()
    test_app.include_router(memory_dialectic_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_dialectic_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_process_turn_cold_boot_api(
    dialectic_test_client: tuple[TestClient, MemoryDialecticService],
) -> None:
    """Verify processing cold-boot interaction turn extracts implicit goals and resistance points."""
    client, _ = dialectic_test_client

    payload: dict[str, object] = {
        "conversation_id": "conv-dialectic-1",
        "user_prompt": "严禁引入外部重型守护进程，重点在于保障本地单机极致响应",
        "assistant_response": "收到，将保持单机纯轻量化架构",
    }

    response = client.post("/api/memory/dialectic/turns/process", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["conversation_id"] == "conv-dialectic-1"
    assert data["turn_index"] == 1
    assert data["is_throttled"] is False
    assert data["heat_state"] == "cold_boot"
    assert data["ephemeral_mind_updated"] is True
    assert data["ephemeral_mind"] is not None
    assert "外部重型守护进程" in data["ephemeral_mind"]["resistance_points"][0]
    assert "保障本地单机极致响应" in data["ephemeral_mind"]["implicit_goals"][0]
    assert "<!-- [USER DIALECTIC MIND]" in data["prompt_volatile_slice"]


def test_process_turn_cadence_throttling_api(
    dialectic_test_client: tuple[TestClient, MemoryDialecticService],
) -> None:
    """Verify cadence throttling kicks in on subsequent turn to preserve tokens and prefix cache."""
    client, _ = dialectic_test_client

    conv_id = "conv-cadence-throttle"
    # Turn 1
    client.post(
        "/api/memory/dialectic/turns/process",
        json={"conversation_id": conv_id, "user_prompt": "第一轮探索"},
    )

    # Turn 2: should be throttled under default cadence of 2
    resp_turn_2 = client.post(
        "/api/memory/dialectic/turns/process",
        json={"conversation_id": conv_id, "user_prompt": "第二轮继续跟进"},
    )
    assert resp_turn_2.status_code == 200
    data_2 = resp_turn_2.json()
    assert data_2["turn_index"] == 2
    assert data_2["is_throttled"] is True
    assert data_2["ephemeral_mind_updated"] is False
    assert "throttled by cadence governor" in data_2["reasoning_summary"]


def test_get_cadence_status_api(
    dialectic_test_client: tuple[TestClient, MemoryDialecticService],
) -> None:
    """Verify querying cadence telemetry and state machine transitions."""
    client, _ = dialectic_test_client

    conv_id = "conv-status-check"
    # Initial status
    resp_init = client.get(f"/api/memory/dialectic/cadence/status/{conv_id}")
    assert resp_init.status_code == 200
    data_init = resp_init.json()
    assert data_init["current_turn"] == 0
    assert data_init["heat_state"] == "cold_boot"

    # Step through 3 turns
    for idx in range(1, 4):
        client.post(
            "/api/memory/dialectic/turns/process",
            json={"conversation_id": conv_id, "user_prompt": f"对话轮次 {idx}"},
        )

    resp_after = client.get(f"/api/memory/dialectic/cadence/status/{conv_id}")
    assert resp_after.status_code == 200
    data_after = resp_after.json()
    assert data_after["current_turn"] == 3
    assert data_after["heat_state"] == "warm"


def test_get_ephemeral_mind_api(
    dialectic_test_client: tuple[TestClient, MemoryDialecticService],
) -> None:
    """Verify fetching latest ephemeral mind snapshot and 404 behavior."""
    client, _ = dialectic_test_client

    # 404 before any turn
    resp_404 = client.get("/api/memory/dialectic/mind/conv-nonexistent")
    assert resp_404.status_code == 404

    # Process turn
    client.post(
        "/api/memory/dialectic/turns/process",
        json={
            "conversation_id": "conv-mind-lookup",
            "user_prompt": "核心目标是降低内存占用",
        },
    )

    resp_found = client.get("/api/memory/dialectic/mind/conv-mind-lookup")
    assert resp_found.status_code == 200
    mind = resp_found.json()
    assert mind["conversation_id"] == "conv-mind-lookup"
    assert "降低内存占用" in mind["implicit_goals"][0]


def test_reset_cadence_session_api(
    dialectic_test_client: tuple[TestClient, MemoryDialecticService],
) -> None:
    """Verify resetting session cadence returns governor to initial blank state."""
    client, _ = dialectic_test_client

    conv_id = "conv-reset-target"
    client.post(
        "/api/memory/dialectic/turns/process",
        json={"conversation_id": conv_id, "user_prompt": "启动执行"},
    )

    resp_delete = client.delete(f"/api/memory/dialectic/cadence/{conv_id}")
    assert resp_delete.status_code == 204

    resp_status = client.get(f"/api/memory/dialectic/cadence/status/{conv_id}")
    assert resp_status.status_code == 200
    assert resp_status.json()["current_turn"] == 0
