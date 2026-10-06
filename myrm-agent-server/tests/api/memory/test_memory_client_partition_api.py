"""
[POS] tests/api/memory/test_memory_client_partition_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.client_partition, app.services.memory.memory_client_partition_service
[OUTPUT] test_resolve_client_workspace_api, test_screen_client_memories_api, test_screen_client_memories_strict_isolation_api, test_resolve_client_workspace_invalid_slug_rejection

Unit test suite for Client-Isolated Workspace and Memory Namespace Partition Suite API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.client_partition import router as memory_client_partition_router
from app.services.memory.memory_client_partition_service import (
    MemoryClientPartitionService,
    get_memory_client_partition_service,
)


@pytest.fixture
def client_partition_test_client(
    tmp_path: Path,
) -> Generator[tuple[TestClient, MemoryClientPartitionService], None, None]:
    """Provide isolated TestClient mounting client partition router with a clean service instance."""
    service = MemoryClientPartitionService(base_dir=tmp_path)

    test_app = FastAPI()
    test_app.include_router(memory_client_partition_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_client_partition_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_resolve_client_workspace_api(
    client_partition_test_client: tuple[TestClient, MemoryClientPartitionService],
) -> None:
    """Verify workspace path resolution endpoint properly quarantines target client."""
    client, _ = client_partition_test_client

    payload: dict[str, object] = {
        "client_id": "acme-corp",
        "client_name": "Acme Corporation",
        "workspace_root": "workspaces/clients",
        "allow_global_read": True,
        "strict_leak_check": True,
    }

    resp = client.post(
        "/api/memory/client-partition/workspace/resolve?auto_create=true",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_id"] == "acme-corp"
    assert data["relative_path"] == "workspaces/clients/acme-corp"
    assert data["is_isolated"] is True
    assert Path(data["absolute_path"]).exists()


def test_screen_client_memories_api(
    client_partition_test_client: tuple[TestClient, MemoryClientPartitionService],
) -> None:
    """Verify memory screening purges foreign client memories and retains valid ones."""
    client, _ = client_partition_test_client

    payload: dict[str, object] = {
        "target_client_id": "client-1",
        "allow_global": True,
        "candidates": [
            {
                "memory_id": "mem-own",
                "content": "Client 1 specific database password",
                "primary_namespace": "client:client-1",
                "namespaces": ["client:client-1"],
                "client_id": "client-1",
                "score": 0.96,
            },
            {
                "memory_id": "mem-foreign",
                "content": "Client 2 confidential merger documents",
                "primary_namespace": "client:client-2",
                "namespaces": ["client:client-2"],
                "client_id": "client-2",
                "score": 0.94,
            },
            {
                "memory_id": "mem-global",
                "content": "Universal coding conventions",
                "primary_namespace": "global",
                "namespaces": ["global"],
                "client_id": None,
                "score": 0.85,
            },
        ],
    }

    resp = client.post("/api/memory/client-partition/screen", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_client_id"] == "client-1"
    assert data["total_evaluated"] == 3
    assert data["allowed_count"] == 2
    assert data["filtered_count"] == 1
    assert data["safe_memory_ids"] == ["mem-own", "mem-global"]
    assert len(data["violations"]) == 1
    assert data["violations"][0]["offending_client_id"] == "client-2"


def test_screen_client_memories_strict_isolation_api(
    client_partition_test_client: tuple[TestClient, MemoryClientPartitionService],
) -> None:
    """Verify strict isolation drops global memories when allow_global is False."""
    client, _ = client_partition_test_client

    payload: dict[str, object] = {
        "target_client_id": "client-alpha",
        "allow_global": False,
        "candidates": [
            {
                "memory_id": "mem-alpha",
                "content": "Client Alpha proprietary patent draft",
                "primary_namespace": "client:client-alpha",
                "namespaces": ["client:client-alpha"],
                "client_id": "client-alpha",
                "score": 0.98,
            },
            {
                "memory_id": "mem-global",
                "content": "Global documentation",
                "primary_namespace": "global",
                "namespaces": ["global"],
                "client_id": None,
                "score": 0.82,
            },
        ],
    }

    resp = client.post("/api/memory/client-partition/screen", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed_count"] == 1
    assert data["filtered_count"] == 1
    assert data["safe_memory_ids"] == ["mem-alpha"]


def test_resolve_client_workspace_invalid_slug_rejection(
    client_partition_test_client: tuple[TestClient, MemoryClientPartitionService],
) -> None:
    """Verify malicious client_id values trigger validation errors."""
    client, _ = client_partition_test_client

    payload: dict[str, object] = {
        "client_id": "../../etc/shadow",
        "workspace_root": "workspaces/clients",
    }

    # ValueError is raised by service and mapped to 500 in FastAPI default handler without custom exception mapping
    with pytest.raises(ValueError):
        client.post("/api/memory/client-partition/workspace/resolve", json=payload)
