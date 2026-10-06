"""
[POS] tests/api/memory/test_memory_provenance_batch_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.provenance_batch, app.services.memory.memory_provenance_batch_service
[OUTPUT] test_create_provenance_link_api, test_isolate_batch_learning_api, test_batch_learn_idempotent_formatting_api, test_create_provenance_link_empty_prompt_rejected_api

Unit test suite for Skill Memory Extraction Provenance and Batch Learn Namespace Isolation API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.provenance_batch import router as memory_provenance_batch_router
from app.services.memory.memory_provenance_batch_service import (
    MemoryProvenanceBatchService,
    get_memory_provenance_batch_service,
)


@pytest.fixture
def provenance_batch_test_client() -> Generator[
    tuple[TestClient, MemoryProvenanceBatchService], None, None
]:
    """Provide isolated TestClient mounting provenance_batch router with clean service instance."""
    service = MemoryProvenanceBatchService()

    test_app = FastAPI()
    test_app.include_router(memory_provenance_batch_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_provenance_batch_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_create_provenance_link_api(
    provenance_batch_test_client: tuple[TestClient, MemoryProvenanceBatchService],
) -> None:
    """Verify provenance link creation endpoint binds tool traces and prompt evidence."""
    client, _ = provenance_batch_test_client

    payload: dict[str, object] = {
        "conversation_id": "conv-audit-01",
        "trigger_prompt": "优化 FastAPI 启动时热重载性能",
        "turn_index": 4,
        "tool_traces": [
            {
                "tool_name": "bash",
                "tool_call_id": "call_1",
                "input_args_summary": "uvicorn app.main:app --reload",
                "output_evidence_snippet": "Application startup complete in 0.4s",
                "status": "success",
                "duration_ms": 400.0,
            }
        ],
        "counterexample": "直接重载整个虚拟环境会导致 5 秒冷启动阻塞",
        "confidence_score": 0.98,
    }

    resp = client.post("/api/memory/provenance/link", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["conversation_id"] == "conv-audit-01"
    assert data["turn_index"] == 4
    assert data["trigger_prompt_snippet"] == "优化 FastAPI 启动时热重载性能"
    assert len(data["tool_traces"]) == 1
    assert data["tool_traces"][0]["tool_name"] == "bash"
    assert data["link_id"].startswith("prov_")


def test_isolate_batch_learning_api(
    provenance_batch_test_client: tuple[TestClient, MemoryProvenanceBatchService],
) -> None:
    """Verify batch learn isolator endpoint partitions private and shared namespaces."""
    client, _ = provenance_batch_test_client

    payload: dict[str, object] = {
        "items": [
            {
                "raw_id": "rule-fastapi-perf",
                "content": "使用 uvicorn --reload-dir 指定目录提速",
                "namespace": "agent:developer",
                "scope_level": "agent",
                "provenance_link": {
                    "link_id": "prov_sample_123",
                    "conversation_id": "conv-dev-01",
                    "turn_index": 2,
                    "trigger_prompt_snippet": "如何提速重载？",
                    "tool_traces": [],
                    "counterexample_snippet": None,
                    "confidence_score": 0.95,
                },
            },
            {
                "raw_id": "rule-company-git-flow",
                "content": "提交前强制通过 pre-push 门禁",
                "namespace": "global",
                "scope_level": "shared",
                "provenance_link": None,
            },
        ]
    }

    resp = client.post("/api/memory/batch-learn/isolate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 2
    assert data["has_provenance_count"] == 1
    assert len(data["namespaced_items"]) == 2
    assert (
        data["namespaced_items"][0]["namespaced_id"]
        == "agent:developer::agent::rule-fastapi-perf"
    )
    assert (
        data["namespaced_items"][1]["namespaced_id"]
        == "global::shared::rule-company-git-flow"
    )


def test_batch_learn_idempotent_formatting_api(
    provenance_batch_test_client: tuple[TestClient, MemoryProvenanceBatchService],
) -> None:
    """Verify already-namespaced IDs remain idempotent without repeated prefixes."""
    client, _ = provenance_batch_test_client

    payload: dict[str, object] = {
        "items": [
            {
                "raw_id": "global::shared::rule-company-git-flow",
                "content": "提交前强制通过 pre-push 门禁",
                "namespace": "global",
                "scope_level": "shared",
                "provenance_link": None,
            }
        ]
    }

    resp = client.post("/api/memory/batch-learn/isolate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert (
        data["namespaced_items"][0]["namespaced_id"]
        == "global::shared::rule-company-git-flow"
    )


def test_create_provenance_link_empty_prompt_rejected_api(
    provenance_batch_test_client: tuple[TestClient, MemoryProvenanceBatchService],
) -> None:
    """Verify empty trigger prompt triggers validation error."""
    client, _ = provenance_batch_test_client

    payload: dict[str, object] = {
        "conversation_id": "conv-bad",
        "trigger_prompt": "   ",
    }

    with pytest.raises(ValueError):
        client.post("/api/memory/provenance/link", json=payload)
