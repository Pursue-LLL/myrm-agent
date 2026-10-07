"""
[POS] tests/api/memory/test_memory_subagent_isolation_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.subagent_isolation, app.services.memory.memory_subagent_isolation_service
[OUTPUT] test_register_pending_items_and_execute_flush_api, test_create_subagent_overlay_and_view_api, test_subagent_selective_merge_api, test_purge_subagent_overlay_api, test_sanitize_stateless_cron_prompt_api

Unit test suite for subagent memory isolation, pre-compression flush hook, and stateless cron guard API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.subagent_isolation import router as memory_subagent_isolation_router
from app.services.memory.memory_subagent_isolation_service import (
    MemorySubagentIsolationService,
    get_memory_subagent_isolation_service,
)


@pytest.fixture
def subagent_isolation_test_client() -> Generator[
    tuple[TestClient, MemorySubagentIsolationService], None, None
]:
    """Provide isolated TestClient mounting subagent_isolation router with clean service instance."""
    service = MemorySubagentIsolationService()

    test_app = FastAPI()
    test_app.include_router(memory_subagent_isolation_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_subagent_isolation_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_register_pending_items_and_execute_flush_api(
    subagent_isolation_test_client: tuple[TestClient, MemorySubagentIsolationService],
) -> None:
    """Verify buffering items and executing pre-compression flush commits to storage."""
    client, _ = subagent_isolation_test_client

    sess_id = "session-flush-api-test"
    register_payload: dict[str, object] = {
        "session_id": sess_id,
        "items": [
            {
                "item_id": "pref-api-1",
                "category": "user_preference",
                "content": "严格执行 PEP8 与 Ruff 代码门禁",
                "source_turn": 3,
                "importance_score": 0.9,
                "tags": ["lint", "code_quality"],
            },
            {
                "item_id": "arch-api-1",
                "category": "architectural_constraint",
                "content": "单文件严格不超过 400 行",
                "source_turn": 3,
                "importance_score": 1.0,
                "tags": ["architecture"],
            },
        ],
    }

    # 1. Register pending items
    resp_reg = client.post("/api/memory/isolation/flush/pending", json=register_payload)
    assert resp_reg.status_code == 200
    assert resp_reg.json()["pending_count"] == 2

    # 2. Execute flush
    flush_payload: dict[str, object] = {
        "session_id": sess_id,
        "reason": "compression",
    }
    resp_flush = client.post("/api/memory/isolation/flush/execute", json=flush_payload)
    assert resp_flush.status_code == 200

    data = resp_flush.json()
    assert data["session_id"] == sess_id
    assert data["is_success"] is True
    assert data["flushed_items_count"] == 2
    assert "user_preference" in data["flushed_categories"]
    assert "architectural_constraint" in data["flushed_categories"]


def test_create_subagent_overlay_and_view_api(
    subagent_isolation_test_client: tuple[TestClient, MemorySubagentIsolationService],
) -> None:
    """Verify subagent memory isolation mounts parent snapshot and allows private scratchpad writes."""
    client, _ = subagent_isolation_test_client

    overlay_id = "sub-overlay-api-01"
    create_payload: dict[str, object] = {
        "spec": {
            "overlay_id": overlay_id,
            "parent_session_id": "parent-sess-01",
            "allow_selective_merge": True,
            "auto_purge_on_finish": True,
            "max_overlay_items": 20,
        },
        "parent_items": [
            {
                "item_id": "parent-fact-1",
                "category": "system_env",
                "content": "当前运行环境为 macOS Darwin",
                "source_turn": 1,
            }
        ],
        "policy": {
            "isolation_scope": "subagent_overlay",
            "allow_profile_read": True,
            "allow_ephemeral_write": True,
            "auto_purge": True,
        },
    }

    # 1. Create overlay
    resp_create = client.post("/api/memory/isolation/subagent/overlay", json=create_payload)
    assert resp_create.status_code == 201
    assert resp_create.json()["is_success"] is True

    # 2. Append scratch item
    append_payload: dict[str, object] = {
        "overlay_id": overlay_id,
        "item": {
            "item_id": "sub-temp-fact",
            "category": "subagent_trial",
            "content": "临时探索尝试: 尝试方案 A",
            "source_turn": 1,
        },
    }
    resp_append = client.post("/api/memory/isolation/subagent/append", json=append_payload)
    assert resp_append.status_code == 200
    assert resp_append.json()["is_success"] is True

    # 3. Get view
    resp_view = client.get(f"/api/memory/isolation/subagent/view/{overlay_id}")
    assert resp_view.status_code == 200
    items = resp_view.json()
    assert len(items) == 2
    ids = {it["item_id"] for it in items}
    assert "parent-fact-1" in ids
    assert "sub-temp-fact" in ids


def test_subagent_selective_merge_api(
    subagent_isolation_test_client: tuple[TestClient, MemorySubagentIsolationService],
) -> None:
    """Verify selective merge extracts target findings and auto-purges residual scratch items."""
    client, _ = subagent_isolation_test_client

    overlay_id = "sub-merge-api-02"
    client.post(
        "/api/memory/isolation/subagent/overlay",
        json={
            "spec": {
                "overlay_id": overlay_id,
                "parent_session_id": "parent-sess-02",
                "allow_selective_merge": True,
                "auto_purge_on_finish": True,
                "max_overlay_items": 10,
            },
            "parent_items": [],
        },
    )

    # Append noise and valuable item
    client.post(
        "/api/memory/isolation/subagent/append",
        json={
            "overlay_id": overlay_id,
            "item": {"item_id": "noise-item", "category": "noise", "content": "无关试错日志"},
        },
    )
    client.post(
        "/api/memory/isolation/subagent/append",
        json={
            "overlay_id": overlay_id,
            "item": {"item_id": "gold-item", "category": "solution", "content": "最终有效解决方案"},
        },
    )

    # Merge selective
    merge_payload: dict[str, object] = {
        "overlay_id": overlay_id,
        "selected_item_ids": ["gold-item"],
    }
    resp_merge = client.post("/api/memory/isolation/subagent/merge", json=merge_payload)
    assert resp_merge.status_code == 200
    harvested = resp_merge.json()
    assert len(harvested) == 1
    assert harvested[0]["item_id"] == "gold-item"
    assert harvested[0]["content"] == "最终有效解决方案"

    # Overlay should be purged
    resp_view = client.get(f"/api/memory/isolation/subagent/view/{overlay_id}")
    assert resp_view.status_code == 200
    assert resp_view.json() == []


def test_purge_subagent_overlay_api(
    subagent_isolation_test_client: tuple[TestClient, MemorySubagentIsolationService],
) -> None:
    """Verify manual destruction of a subagent memory overlay."""
    client, _ = subagent_isolation_test_client

    overlay_id = "sub-purge-api-03"
    client.post(
        "/api/memory/isolation/subagent/overlay",
        json={
            "spec": {
                "overlay_id": overlay_id,
                "parent_session_id": "parent-sess-03",
            },
            "parent_items": [],
        },
    )

    resp_delete = client.delete(f"/api/memory/isolation/subagent/overlay/{overlay_id}")
    assert resp_delete.status_code == 204

    resp_view = client.get(f"/api/memory/isolation/subagent/view/{overlay_id}")
    assert resp_view.status_code == 200
    assert resp_view.json() == []


def test_sanitize_stateless_cron_prompt_api(
    subagent_isolation_test_client: tuple[TestClient, MemorySubagentIsolationService],
) -> None:
    """Verify cleansing prompt removes volatile user profiles for stateless automated tasks."""
    client, _ = subagent_isolation_test_client

    prompt_with_pollution = (
        "<!-- [USER PROFILE] 用户喜好 Python，禁止向后兼容 -->\n\n"
        "<!-- [USER DIALECTIC MIND] 焦点: 数据库死锁排除 -->\n\n"
        "每天凌晨两点定期巡检 Qdrant 与 SQLite 健康状态并输出报告。"
    )

    payload: dict[str, object] = {
        "task_id": "cron-health-check",
        "task_name": "系统健康巡检",
        "raw_prompt": prompt_with_pollution,
        "strip_user_profile": True,
        "require_self_contained": True,
    }

    resp = client.post("/api/memory/isolation/cron/sanitize", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert data["task_id"] == "cron-health-check"
    assert data["was_modified"] is True
    assert data["is_self_contained"] is True
    assert "<!-- [USER PROFILE]" not in data["sanitized_prompt"]
    assert "<!-- [USER DIALECTIC MIND]" not in data["sanitized_prompt"]
    assert "每天凌晨两点定期巡检 Qdrant 与 SQLite 健康状态并输出报告。" in data["sanitized_prompt"]
