"""
[POS] tests/api/memory/test_memory_self_verification_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.self_verification_router, app.services.memory.memory_self_verification_service
[OUTPUT] test_run_diagnostic_suite_api, test_run_fact_mutation_probe_api, test_run_zero_lexical_probe_api, test_run_procedural_anti_drop_probe_api

Unit test suite for Memory Self-Verification Diagnostic Suite & Fact Update Benchmark API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.self_verification_router import (
    router as memory_self_verification_router,
)
from app.services.memory.memory_self_verification_service import (
    MemorySelfVerificationService,
    get_memory_self_verification_service,
)


@pytest.fixture
def self_verification_test_client() -> Generator[tuple[TestClient, MemorySelfVerificationService], None, None]:
    """Provide isolated TestClient mounting self-verification router with a clean service instance."""
    service = MemorySelfVerificationService()

    test_app = FastAPI()
    test_app.include_router(memory_self_verification_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_self_verification_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_run_diagnostic_suite_api(
    self_verification_test_client: tuple[TestClient, MemorySelfVerificationService],
) -> None:
    """Verify POST /api/memory/self-verification/run executes full benchmark suite inside sandbox."""
    client, _ = self_verification_test_client

    payload = {"custom_namespace": "_test_bench_sandbox_api_01"}
    res = client.post("/api/memory/self-verification/run", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["grade"] == "EXCELLENT"
    assert data["score"] == 100.0
    assert data["total_probes"] == 3
    assert data["passed_probes"] == 3
    assert data["sandbox_cleaned"] is True
    assert data["fact_mutation_result"]["success"] is True
    assert data["zero_lexical_result"]["recalled"] is True
    assert data["procedural_anti_drop_result"]["is_preserved"] is True
    assert "HEALTH GRADE: EXCELLENT" in data["summary"].upper()


def test_run_fact_mutation_probe_api(
    self_verification_test_client: tuple[TestClient, MemorySelfVerificationService],
) -> None:
    """Verify POST /api/memory/self-verification/fact-mutation asserts in-place fact replacement."""
    client, _ = self_verification_test_client

    payload = {
        "entity_key": "monthly_revenue_target",
        "initial_fact": "目标是月入1万",
        "updated_fact": "目标改成月入3万",
    }
    res = client.post("/api/memory/self-verification/fact-mutation", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["retained_fact_count"] == 1
    assert data["is_latest_retained"] is True
    assert data["residual_conflict_count"] == 0
    assert data["latency_ms"] >= 0.0


def test_run_zero_lexical_probe_api(
    self_verification_test_client: tuple[TestClient, MemorySelfVerificationService],
) -> None:
    """Verify POST /api/memory/self-verification/zero-lexical asserts zero word overlap semantic recall."""
    client, _ = self_verification_test_client

    payload = {
        "query": "靠什么赚钱",
        "memory_text": "在做 AI 教学、AI 工具、SEO",
        "min_similarity_threshold": 0.65,
    }
    res = client.post("/api/memory/self-verification/zero-lexical", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["is_zero_overlap"] is True
    assert data["lexical_overlap_ratio"] == 0.0
    assert data["cosine_similarity"] >= 0.70
    assert data["recalled"] is True


def test_run_procedural_anti_drop_probe_api(
    self_verification_test_client: tuple[TestClient, MemorySelfVerificationService],
) -> None:
    """Verify POST /api/memory/self-verification/procedural-anti-drop asserts rule routing and preservation."""
    client, _ = self_verification_test_client

    payload = {
        "rule_content": "排查容器 503 报错时，必须优先检查端口映射与 IPv4 回环绑定，禁止直接重启服务",
    }
    res = client.post("/api/memory/self-verification/procedural-anti-drop", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["routed_track"] == "procedural"
    assert data["was_dropped"] is False
    assert data["is_preserved"] is True
    assert data["drop_reason"] is None
