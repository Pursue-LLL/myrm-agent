"""
[POS] tests/api/memory/test_memory_budget_curator_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.budget_curator, app.services.memory.memory_budget_curator_service
[OUTPUT] test_evaluate_memory_budget_api, test_apply_atomic_batch_successful_swap_api, test_apply_atomic_batch_overflow_rollback_api, test_apply_atomic_batch_substring_collision_guard_api, test_scroll_session_around_anchor_api

Unit test suite for Memory Budget Meter, Atomic Operations Curator, and Session Scroll Navigator API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.budget_curator import router as memory_budget_curator_router
from app.services.memory.memory_budget_curator_service import (
    MemoryBudgetCuratorService,
    get_memory_budget_curator_service,
)


@pytest.fixture
def budget_curator_test_client() -> Generator[
    tuple[TestClient, MemoryBudgetCuratorService], None, None
]:
    """Provide isolated TestClient mounting budget_curator router with clean service instance."""
    service = MemoryBudgetCuratorService()

    test_app = FastAPI()
    test_app.include_router(memory_budget_curator_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_budget_curator_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_evaluate_memory_budget_api(
    budget_curator_test_client: tuple[TestClient, MemoryBudgetCuratorService],
) -> None:
    """Verify evaluating memory items budget and rendering visual header."""
    client, _ = budget_curator_test_client

    payload: dict[str, object] = {
        "items": [
            {"item_id": "item-1", "content": "用户倾向于使用严格类型提示", "token_count": 20},
            {"item_id": "item-2", "content": "架构风格采用单一职责原则", "token_count": 30},
        ],
        "spec": {
            "max_tokens": 100,
            "max_slots": 10,
            "warning_threshold_pct": 75.0,
        },
    }

    response = client.post("/api/memory/budget/evaluate", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["used_tokens"] == 50
    assert data["max_tokens"] == 100
    assert data["token_usage_pct"] == 50.0
    assert data["used_slots"] == 2
    assert data["is_warning"] is False
    assert data["is_overflow"] is False
    assert "# USER PROFILE & MEMORIES [Budget: 50%, 50/100 tokens | Slots: 2/10]" in data["budget_header_slice"]


def test_apply_atomic_batch_successful_swap_api(
    budget_curator_test_client: tuple[TestClient, MemoryBudgetCuratorService],
) -> None:
    """Verify atomic removal and addition swap commits successfully in one round."""
    client, _ = budget_curator_test_client

    payload: dict[str, object] = {
        "current_items": [
            {"item_id": "old_pref", "content": "废弃旧配置项", "token_count": 25},
            {"item_id": "keep_pref", "content": "保留的核心架构规则", "token_count": 20},
        ],
        "operations": [
            {
                "operation_type": "remove",
                "target_id": "old_pref",
            },
            {
                "operation_type": "add",
                "new_id": "new_pref",
                "new_content": "新采纳的优化实践",
                "estimated_tokens": 30,
            },
        ],
        "budget_spec": {
            "max_tokens": 100,
            "max_slots": 5,
        },
    }

    response = client.post("/api/memory/budget/atomic-batch", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["is_success"] is True
    assert data["applied_count"] == 2
    assert data["rolled_back"] is False
    assert len(data["retained_items"]) == 2
    assert data["current_budget"]["used_tokens"] == 50


def test_apply_atomic_batch_overflow_rollback_api(
    budget_curator_test_client: tuple[TestClient, MemoryBudgetCuratorService],
) -> None:
    """Verify atomic operations completely rollback when budget is exceeded."""
    client, _ = budget_curator_test_client

    payload: dict[str, object] = {
        "current_items": [
            {"item_id": "it-1", "content": "重要事实 1", "token_count": 30},
            {"item_id": "it-2", "content": "重要事实 2", "token_count": 30},
        ],
        "operations": [
            {
                "operation_type": "add",
                "new_id": "it-huge",
                "new_content": "超量事实将撑爆上限",
                "estimated_tokens": 30,
            },
        ],
        "budget_spec": {
            "max_tokens": 70,  # 30+30+30 = 90 > 70
            "max_slots": 5,
        },
    }

    response = client.post("/api/memory/budget/atomic-batch", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["is_success"] is False
    assert data["rolled_back"] is True
    assert "memory budget overflowed" in data["error_message"]
    # 原始项毫发无损
    assert len(data["retained_items"]) == 2
    assert data["retained_items"][0]["item_id"] == "it-1"


def test_apply_atomic_batch_substring_collision_guard_api(
    budget_curator_test_client: tuple[TestClient, MemoryBudgetCuratorService],
) -> None:
    """Verify ambiguous substring matching aborts entire batch to protect data integrity."""
    client, _ = budget_curator_test_client

    payload: dict[str, object] = {
        "current_items": [
            {"item_id": "cfg_a", "content": "环境参数: 最大重试次数为 3", "token_count": 15},
            {"item_id": "cfg_b", "content": "环境参数: 超时时间为 30 秒", "token_count": 15},
        ],
        "operations": [
            {
                "operation_type": "remove",
                "target_substring": "环境参数",
            },
        ],
    }

    response = client.post("/api/memory/budget/atomic-batch", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["is_success"] is False
    assert data["rolled_back"] is True
    assert "matched multiple candidates" in data["error_message"]
    assert "cfg_a" in data["error_message"] and "cfg_b" in data["error_message"]


def test_scroll_session_around_anchor_api(
    budget_curator_test_client: tuple[TestClient, MemoryBudgetCuratorService],
) -> None:
    """Verify bidirectional continuous message sliding window around anchor ID."""
    client, _ = budget_curator_test_client

    messages: list[dict[str, str]] = [
        {"message_id": f"m_{idx}", "role": "user" if idx % 2 == 0 else "assistant", "content": f"msg text {idx}", "created_at": f"2026-10-07T0{idx}:00:00Z"}
        for idx in range(8)
    ]

    payload: dict[str, object] = {
        "messages": messages,
        "request": {
            "conversation_id": "conv-window-test",
            "around_message_id": "m_4",
            "before_limit": 2,
            "after_limit": 2,
        },
    }

    response = client.post("/api/memory/sessions/scroll", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["conversation_id"] == "conv-window-test"
    assert data["around_message_id"] == "m_4"
    assert len(data["messages"]) == 5
    assert data["messages"][0]["message_id"] == "m_2"
    assert data["messages"][2]["message_id"] == "m_4"
    assert data["messages"][4]["message_id"] == "m_6"
    assert data["has_more_before"] is True
    assert data["has_more_after"] is True
