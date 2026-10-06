"""
[POS] tests/api/memory/test_memory_conflict_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.conflict_router
[OUTPUT] test_evaluate_conflict_api_and_auto_staging, test_list_pending_conflicts_api, test_arbitrate_conflict_and_freeze_lock_api, test_freeze_status_and_unlock_decision_api

Unit test suite for working memory conflict semantic arbitration, human arbitration card review, and user-confirmed decision freeze gate.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.conflict_router import router as memory_conflict_router
from app.services.memory.memory_conflict_service import (
    MemoryConflictService,
    get_memory_conflict_service,
)


@pytest.fixture
def conflict_test_client() -> Generator[tuple[TestClient, MemoryConflictService], None, None]:
    """Provide isolated TestClient mounting memory conflict router with a clean service instance."""
    service = MemoryConflictService()

    test_app = FastAPI()
    test_app.include_router(memory_conflict_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_conflict_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_evaluate_conflict_api_and_auto_staging(
    conflict_test_client: tuple[TestClient, MemoryConflictService],
) -> None:
    """Verify POST /api/memory/conflict/evaluate categorizes contradiction vs override and stages disputed facts."""
    client, _ = conflict_test_client

    # 1. Contradiction evaluation
    contra_payload = {
        "entity_key": "storage_architecture",
        "attribute_name": "primary_engine",
        "existing_memory_id": "mem-db-99",
        "existing_fact_text": "生产环境核心数据必须存储在单机PostgreSQL实例中",
        "candidate_fact_text": "采用分片分布式MongoDB集群支撑多租户",
        "source_context": "PRD讨论记录第3轮",
        "auto_stage_if_disputed": True,
    }
    resp_contra = client.post("/api/memory/conflict/evaluate", json=contra_payload)
    assert resp_contra.status_code == 200
    data_contra = resp_contra.json()
    assert data_contra["resolution_kind"] == "contradiction"
    assert data_contra["requires_human_confirmation"] is True
    assert data_contra["is_staged_in_pending"] is True
    assert data_contra["conflict_id"].startswith("conf-")

    # 2. Explicit override evaluation
    override_payload = {
        "entity_key": "release_schedule",
        "attribute_name": "target_quarter",
        "existing_memory_id": "mem-rel-1",
        "existing_fact_text": "发布目标定于2026年Q3",
        "candidate_fact_text": "管理层会议纪要：经审议更正为2026年Q4正式发布",
        "source_context": "周会决议",
        "auto_stage_if_disputed": True,
    }
    resp_override = client.post("/api/memory/conflict/evaluate", json=override_payload)
    assert resp_override.status_code == 200
    data_override = resp_override.json()
    assert data_override["resolution_kind"] == "override"
    assert data_override["requires_human_confirmation"] is False
    assert data_override["is_staged_in_pending"] is False


def test_list_pending_conflicts_api(
    conflict_test_client: tuple[TestClient, MemoryConflictService],
) -> None:
    """Verify GET /api/memory/conflict/pending returns all staged contradictions awaiting human review."""
    client, _ = conflict_test_client

    # Initially empty
    resp_init = client.get("/api/memory/conflict/pending")
    assert resp_init.status_code == 200
    assert resp_init.json()["total_count"] == 0

    # Stage a contradiction
    stage_payload = {
        "entity_key": "security_perimeter",
        "attribute_name": "network_egress",
        "existing_memory_id": "mem-sec-1",
        "existing_fact_text": "严禁一切外网访问，完全离线运行",
        "candidate_fact_text": "开启白名单外网直连访问",
        "source_context": "网络规划初稿",
        "auto_stage_if_disputed": True,
    }
    eval_resp = client.post("/api/memory/conflict/evaluate", json=stage_payload)
    conflict_id = eval_resp.json()["conflict_id"]

    # Verify pending endpoint
    resp_list = client.get("/api/memory/conflict/pending")
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert list_data["total_count"] == 1
    item = list_data["items"][0]
    assert item["conflict_id"] == conflict_id
    assert item["entity_key"] == "security_perimeter"
    assert item["existing_fact_text"] == "严禁一切外网访问，完全离线运行"


def test_arbitrate_conflict_and_freeze_lock_api(
    conflict_test_client: tuple[TestClient, MemoryConflictService],
) -> None:
    """Verify POST /api/memory/conflict/arbitrate finalizes decision and applies immutable freeze lock."""
    client, _ = conflict_test_client

    # Stage a conflict first
    stage_payload = {
        "entity_key": "cloud_provider",
        "attribute_name": "vendor",
        "existing_memory_id": "mem-cloud-1",
        "existing_fact_text": "基础设施首选AWS自建",
        "candidate_fact_text": "建议全面迁移至GCP托管",
        "source_context": "技术委员会备忘录",
        "auto_stage_if_disputed": True,
    }
    eval_resp = client.post("/api/memory/conflict/evaluate", json=stage_payload)
    conflict_id = eval_resp.json()["conflict_id"]

    # Human operator resolves the card and applies freeze lock
    arbitrate_payload = {
        "conflict_id": conflict_id,
        "chosen_resolution": "override",
        "final_fact_text": "技术委员会终审拍板：核心集群严格部署在AWS专有VPC，不得迁移。",
        "operator_id": "principal_architect_elena",
        "should_freeze_lock": True,
        "comment": "Finalized during Q4 architecture summit.",
    }
    arb_resp = client.post("/api/memory/conflict/arbitrate", json=arbitrate_payload)
    assert arb_resp.status_code == 200
    arb_data = arb_resp.json()
    assert arb_data["success"] is True
    assert arb_data["is_frozen"] is True
    assert arb_data["immutable_hash"] is not None
    assert "elena" in arb_data["message"]

    # Verify conflict is cleared from pending queue
    resp_pending = client.get("/api/memory/conflict/pending")
    assert resp_pending.json()["total_count"] == 0


def test_freeze_status_and_unlock_decision_api(
    conflict_test_client: tuple[TestClient, MemoryConflictService],
) -> None:
    """Verify GET /api/memory/conflict/freeze/{memory_id} and POST /api/memory/conflict/unlock lifecycle."""
    client, service = conflict_test_client

    # Directly lock a memory record via service
    service.freeze_gate.freeze(
        memory_id="mem-hardened-lock",
        content="Zero external credential exposure.",
        confirmed_by="sec_officer",
    )

    # 1. Query freeze status
    resp_status = client.get("/api/memory/conflict/freeze/mem-hardened-lock")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["is_frozen"] is True
    assert status_data["frozen_content"] == "Zero external credential exposure."
    assert status_data["confirmed_by"] == "sec_officer"
    assert status_data["integrity_valid"] is True

    # 2. Unlock the decision
    unlock_payload = {
        "memory_id": "mem-hardened-lock",
        "operator_id": "chief_security_officer",
        "reason": "Authorized security baseline revision for 2027.",
    }
    resp_unlock = client.post("/api/memory/conflict/unlock", json=unlock_payload)
    assert resp_unlock.status_code == 200
    assert resp_unlock.json()["success"] is True

    # 3. Query freeze status again -> should be inactive
    resp_unlocked_status = client.get("/api/memory/conflict/freeze/mem-hardened-lock")
    assert resp_unlocked_status.status_code == 200
    assert resp_unlocked_status.json()["is_frozen"] is False
