"""
[POS] tests/api/memory/test_memory_shared_bus_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.shared_bus, app.services.memory.memory_shared_bus_service
[OUTPUT] test_record_negative_decision_api, test_check_negative_decision_conflict_api, test_check_negative_decision_clean_api, test_get_concurrency_pool_status_api, test_score_memory_decay_api

Unit test suite for Multi-Agent Shared Memory Bus, Concurrency Pool, Backpressure Guard, and Negative Decision Ledger API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.shared_bus import router as memory_shared_bus_router
from app.services.memory.memory_shared_bus_service import (
    MemorySharedBusService,
    get_memory_shared_bus_service,
)


@pytest.fixture
def shared_bus_test_client() -> Generator[
    tuple[TestClient, MemorySharedBusService], None, None
]:
    """Provide isolated TestClient mounting shared_bus router with clean service instance."""
    service = MemorySharedBusService()

    test_app = FastAPI()
    test_app.include_router(memory_shared_bus_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_shared_bus_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_record_negative_decision_api(
    shared_bus_test_client: tuple[TestClient, MemorySharedBusService],
) -> None:
    """Verify recording a negative decision into the ledger via POST."""
    client, _ = shared_bus_test_client

    payload: dict[str, object] = {
        "decision_id": "veto-arch-01",
        "decision_subject": "引入外部 RabbitMQ 消息队列",
        "veto_reason": "单机部署与沙箱架构中无需重型外部消息队列，增加依赖与运维隐患",
        "alternative_chosen": "使用 Harness 内部轻量级 asyncio 队列与内存总线",
        "context_summary": "2026 架构评审一致决议",
        "severity": "hard_block",
        "scope": "global",
    }

    response = client.post("/api/memory/shared-bus/veto", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["decision_id"] == "veto-arch-01"
    assert data["decision_subject"] == "引入外部 RabbitMQ 消息队列"
    assert data["alternative_chosen"] == "使用 Harness 内部轻量级 asyncio 队列与内存总线"
    assert data["severity"] == "hard_block"


def test_check_negative_decision_conflict_api(
    shared_bus_test_client: tuple[TestClient, MemorySharedBusService],
) -> None:
    """Verify screening a conflicting proposal triggers guard prompt and hard blocking."""
    client, service = shared_bus_test_client

    # 预置否决记录
    service.bus.record_veto(
        service.bus.ledger.get_veto("veto-arch-01")
        or type(
            "FakeEntry",
            (),
            {
                "decision_id": "veto-arch-01",
                "decision_subject": "引入外部 RabbitMQ 消息队列",
                "veto_reason": "增加运维开销",
                "alternative_chosen": "使用进程内异步队列",
                "context_summary": "评审决议",
                "severity": type("FakeSev", (), {"value": "hard_block"})(),
                "scope": "global",
                "created_at": "2026-10-07T00:00:00Z",
            },
        )()  # type: ignore[arg-type]
    )

    # 插入有效记录
    client.post(
        "/api/memory/shared-bus/veto",
        json={
            "decision_id": "veto-arch-02",
            "decision_subject": "使用 Redis 作为分布式缓存",
            "veto_reason": "纯单机沙箱设计避免引入额外服务",
            "alternative_chosen": "内置 SQLite WAL 缓存",
            "context_summary": "架构红线",
            "severity": "hard_block",
            "scope": "global",
        },
    )

    check_payload: dict[str, object] = {
        "candidate_proposal": "我们提议使用 Redis 作为分布式缓存来加速数据读写",
        "scope": "global",
    }
    response = client.post("/api/memory/shared-bus/check-veto", json=check_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["is_blocked"] is True
    assert len(data["matched_entries"]) == 1
    assert "NEGATIVE DECISION GUARD" in data["guard_prompt_slice"]
    assert "使用 Redis 作为分布式缓存" in data["rejection_summary"]


def test_check_negative_decision_clean_api(
    shared_bus_test_client: tuple[TestClient, MemorySharedBusService],
) -> None:
    """Verify screening an un-conflicted proposal passes freely."""
    client, _ = shared_bus_test_client

    check_payload: dict[str, object] = {
        "candidate_proposal": "我们编写一个高效的 Python 本地生成器",
        "scope": "global",
    }
    response = client.post("/api/memory/shared-bus/check-veto", json=check_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["is_blocked"] is False
    assert len(data["matched_entries"]) == 0
    assert data["guard_prompt_slice"] == ""


def test_get_concurrency_pool_status_api(
    shared_bus_test_client: tuple[TestClient, MemorySharedBusService],
) -> None:
    """Verify live concurrency pool and memory backpressure guard metrics endpoint."""
    client, _ = shared_bus_test_client

    response = client.get("/api/memory/shared-bus/pool-status")
    assert response.status_code == 200

    data = response.json()
    assert data["active_readers"] == 0
    assert data["active_writers"] == 0
    assert data["queued_tasks"] == 0
    assert isinstance(data["current_rss_mb"], float)
    assert isinstance(data["is_throttled"], bool)
    assert isinstance(data["status_message"], str)


def test_score_memory_decay_api(
    shared_bus_test_client: tuple[TestClient, MemorySharedBusService],
) -> None:
    """Verify access frequency reinforcement and temporal decay scoring endpoint."""
    client, _ = shared_bus_test_client

    payload: dict[str, object] = {
        "memory_id": "mem-scoring-01",
        "content": "系统默认仅支持单机沙箱隔离",
        "base_weight": 1.0,
        "hit_count": 8,
        "last_accessed_at": "2026-10-07T00:00:00Z",
    }

    response = client.post("/api/memory/shared-bus/score", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["memory_id"] == "mem-scoring-01"
    assert data["hit_count"] == 8
    assert data["reinforcement_factor"] > 1.0
    assert data["composite_score"] > 1.0
