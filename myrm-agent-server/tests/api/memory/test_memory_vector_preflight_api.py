"""
[POS] tests/api/memory/test_memory_vector_preflight_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.vector_preflight_router, app.services.memory.memory_vector_preflight_service
[OUTPUT] test_sanitize_endpoint_api, test_verify_dimensions_matching_api, test_verify_dimensions_mismatch_api, test_inspect_composite_vector_store_api

Unit test suite for Vector Store Preflight Dimension Integrity and IPv4 Loopback Sanitizer API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.vector_preflight_router import (
    router as memory_vector_preflight_router,
)
from app.services.memory.memory_vector_preflight_service import (
    MemoryVectorPreflightService,
    get_memory_vector_preflight_service,
)


@pytest.fixture
def vector_preflight_test_client() -> Generator[tuple[TestClient, MemoryVectorPreflightService], None, None]:
    """Provide isolated TestClient mounting vector preflight router with a clean service instance."""
    service = MemoryVectorPreflightService()

    test_app = FastAPI()
    test_app.include_router(memory_vector_preflight_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_vector_preflight_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_sanitize_endpoint_api(
    vector_preflight_test_client: tuple[TestClient, MemoryVectorPreflightService],
) -> None:
    """Verify POST /api/memory/vector-preflight/sanitize-endpoint normalizes localhost to 127.0.0.1."""
    client, _ = vector_preflight_test_client

    # Localhost with HTTP
    res = client.post(
        "/api/memory/vector-preflight/sanitize-endpoint",
        json={"endpoint": "http://localhost:6333/dashboard"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["was_modified"] is True
    assert data["sanitized_endpoint"] == "http://127.0.0.1:6333/dashboard"
    assert "IPv6 ::1" in data["modification_reason"]

    # External IP unchanged
    res_ext = client.post(
        "/api/memory/vector-preflight/sanitize-endpoint",
        json={"endpoint": "http://192.168.1.50:6333"},
    )
    assert res_ext.status_code == 200
    data_ext = res_ext.json()
    assert data_ext["was_modified"] is False
    assert data_ext["sanitized_endpoint"] == "http://192.168.1.50:6333"


def test_verify_dimensions_matching_api(
    vector_preflight_test_client: tuple[TestClient, MemoryVectorPreflightService],
) -> None:
    """Verify POST /api/memory/vector-preflight/verify-dimensions validates compatible embedding sizes."""
    client, _ = vector_preflight_test_client

    payload = {
        "actual_dims": 1536,
        "expected_dims": 1536,
        "embedder_name": "text-embedding-3-small",
        "collection_name": "general_memories",
    }
    res = client.post("/api/memory/vector-preflight/verify-dimensions", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["is_valid"] is True
    assert data["status"] == "healthy"
    assert "perfectly matches" in data["diagnosis"]
    assert data["suggested_action"] == ""


def test_verify_dimensions_mismatch_api(
    vector_preflight_test_client: tuple[TestClient, MemoryVectorPreflightService],
) -> None:
    """Verify dimension mismatch triggers rigid blocking and returns actionable diagnosis guidance."""
    client, _ = vector_preflight_test_client

    payload = {
        "actual_dims": 2560,
        "expected_dims": 1536,
        "embedder_name": "Qwen3-Embedding-4B",
        "collection_name": "general_memories",
    }
    res = client.post("/api/memory/vector-preflight/verify-dimensions", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["is_valid"] is False
    assert data["status"] == "mismatch_blocked"
    assert "2560" in data["diagnosis"]
    assert "1536" in data["diagnosis"]
    assert "Recreate collection" in data["suggested_action"]


def test_inspect_composite_vector_store_api(
    vector_preflight_test_client: tuple[TestClient, MemoryVectorPreflightService],
) -> None:
    """Verify POST /api/memory/vector-preflight/inspect provides composite health assessment."""
    client, _ = vector_preflight_test_client

    # Sanitized loopback + matching dimensions
    req_pass = {
        "endpoint": "localhost:6333",
        "actual_dims": 1024,
        "expected_dims": 1024,
        "embedder_name": "bge-large",
        "collection_name": "code_memories",
    }
    res_pass = client.post("/api/memory/vector-preflight/inspect", json=req_pass)
    assert res_pass.status_code == 200
    data_pass = res_pass.json()
    assert data_pass["endpoint_result"]["sanitized_endpoint"] == "127.0.0.1:6333"
    assert data_pass["dimension_report"]["is_valid"] is True
    assert data_pass["overall_status"] == "action_required_or_sanitized"

    # Mismatched dimensions blocks overall flight
    req_block = {
        "endpoint": "http://127.0.0.1:6333",
        "actual_dims": 768,
        "expected_dims": 1536,
        "embedder_name": "bge-base",
        "collection_name": "code_memories",
    }
    res_block = client.post("/api/memory/vector-preflight/inspect", json=req_block)
    assert res_block.status_code == 200
    data_block = res_block.json()
    assert data_block["dimension_report"]["is_valid"] is False
    assert data_block["overall_status"] == "blocked"
