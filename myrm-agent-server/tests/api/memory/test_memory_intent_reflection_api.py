"""
[POS] tests/api/memory/test_memory_intent_reflection_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.intent_reflection_router, app.services.memory.memory_intent_reflection_service
[OUTPUT] test_classify_intent_tier_0_fast_path_api, test_classify_intent_tier_1_code_execution_api, test_evaluate_activation_tier_0_bypasses_retrieval_api, test_evaluate_activation_tier_1_filters_unrelated_facets_api

Unit test suite for Lightweight Reflection Intent Filter and Playbook Activation Probe API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.intent_reflection_router import (
    router as memory_intent_reflection_router,
)
from app.services.memory.memory_intent_reflection_service import (
    MemoryIntentReflectionService,
    get_memory_intent_reflection_service,
)


@pytest.fixture
def intent_reflection_test_client() -> Generator[
    tuple[TestClient, MemoryIntentReflectionService], None, None
]:
    """Provide isolated TestClient mounting intent reflection router with a clean service instance."""
    service = MemoryIntentReflectionService()

    test_app = FastAPI()
    test_app.include_router(
        memory_intent_reflection_router, prefix="/api/memory"
    )
    test_app.dependency_overrides[get_memory_intent_reflection_service] = (
        lambda: service
    )

    with TestClient(test_app) as client:
        yield client, service


def test_classify_intent_tier_0_fast_path_api(
    intent_reflection_test_client: tuple[
        TestClient, MemoryIntentReflectionService
    ],
) -> None:
    """Verify POST /api/memory/intent-reflection/classify categorizes flow controls to Tier 0 Fast Path."""
    client, _ = intent_reflection_test_client

    for phrase in ["好的", "继续", "ok", "got it", "status", "help"]:
        res = client.post(
            "/api/memory/intent-reflection/classify",
            json={"query": phrase},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["tier"] == "tier_0_fast_path"
        assert data["confidence"] >= 0.95
        assert data["source"] == "heuristic"
        assert len(data["suggested_facets"]) == 0


def test_classify_intent_tier_1_code_execution_api(
    intent_reflection_test_client: tuple[
        TestClient, MemoryIntentReflectionService
    ],
) -> None:
    """Verify POST /api/memory/intent-reflection/classify recognizes code and CLI execution commands."""
    client, _ = intent_reflection_test_client

    code_payload = {
        "query": "请帮我运行 docker compose up -d 并调试 python 脚本报错"
    }
    res = client.post(
        "/api/memory/intent-reflection/classify", json=code_payload
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tier"] == "tier_1_code_execution"
    assert data["confidence"] >= 0.90
    assert "coding" in data["suggested_facets"]
    assert "devops" in data["suggested_facets"]


def test_evaluate_activation_tier_0_bypasses_retrieval_api(
    intent_reflection_test_client: tuple[
        TestClient, MemoryIntentReflectionService
    ],
) -> None:
    """Verify POST /api/memory/intent-reflection/evaluate-activation bypasses retrieval for fast path."""
    client, _ = intent_reflection_test_client

    req = {
        "query": "好的",
        "candidates": [
            {
                "id": "rule_devops",
                "trigger": "deploy",
                "action": "run script",
                "facets": ["devops"],
            },
            {
                "id": "rule_global",
                "trigger": "always",
                "action": "log",
                "facets": ["global"],
            },
        ],
    }
    res = client.post(
        "/api/memory/intent-reflection/evaluate-activation", json=req
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tier"] == "tier_0_fast_path"
    assert data["bypass_retrieval"] is True
    assert data["activated_rule_ids"] == []
    assert data["suppressed_rules_count"] == 2
    assert "bypassed" in data["decision_reason"].lower()


def test_evaluate_activation_tier_1_filters_unrelated_facets_api(
    intent_reflection_test_client: tuple[
        TestClient, MemoryIntentReflectionService
    ],
) -> None:
    """Verify POST /api/memory/intent-reflection/evaluate-activation filters out unrelated writing rules."""
    client, _ = intent_reflection_test_client

    req = {
        "query": "调试这个 pytest 运行失败的单元测试用例",
        "candidates": [
            {
                "id": "rule_devops",
                "trigger": "pytest",
                "action": "check flags",
                "facets": ["devops"],
                "lifecycle_state": "active",
            },
            {
                "id": "rule_writing",
                "trigger": "doc",
                "action": "format markdown",
                "facets": ["writing"],
                "lifecycle_state": "active",
            },
            {
                "id": "rule_global",
                "trigger": "always",
                "action": "confirm safety",
                "facets": ["global"],
                "lifecycle_state": "active",
            },
            {
                "id": "rule_retired_devops",
                "trigger": "pytest",
                "action": "old flag",
                "facets": ["devops"],
                "lifecycle_state": "retired",
            },
        ],
    }
    res = client.post(
        "/api/memory/intent-reflection/evaluate-activation", json=req
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tier"] == "tier_1_code_execution"
    assert data["bypass_retrieval"] is False
    assert "rule_devops" in data["activated_rule_ids"]
    assert "rule_global" in data["activated_rule_ids"]
    assert "rule_writing" not in data["activated_rule_ids"]
    assert "rule_retired_devops" not in data["activated_rule_ids"]
    assert data["suppressed_rules_count"] == 2
