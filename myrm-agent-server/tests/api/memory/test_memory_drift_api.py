"""
[POS] tests/api/memory/test_memory_drift_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, app.api.memory.drift_router
[OUTPUT] test_check_memory_drift_pristine_api, test_check_memory_drift_missing_file_api, test_check_memory_drift_missing_symbol_api, test_check_batch_memory_drift_api

Unit test suite for memory drift defense and ground truth verification API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from myrm_agent_harness.toolkits.memory.drift_defense import (
    DriftDefenseConfig,
    GroundTruthDriftDetector,
    StaleMemoryDecorator,
)
from starlette.testclient import TestClient

from app.api.memory.drift_router import router as memory_drift_router
from app.services.memory.memory_drift_service import (
    MemoryDriftService,
    get_memory_drift_service,
)


@pytest.fixture
def drift_test_client() -> Generator[tuple[TestClient, Path], None, None]:
    """Provide isolated TestClient mounting memory drift router with a mock workspace."""
    with tempfile.TemporaryDirectory() as td:
        ws_path = Path(td)
        # Create mock project files
        src_dir = ws_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        py_file = src_dir / "calculator.py"
        py_file.write_text(
            "class Calculator:\n"
            "    def add(self, a: int, b: int) -> int:\n"
            "        return a + b\n",
            encoding="utf-8",
        )

        detector = GroundTruthDriftDetector(config=DriftDefenseConfig(stale_confidence_penalty=0.5))
        decorator = StaleMemoryDecorator()
        service = MemoryDriftService(
            detector=detector,
            decorator=decorator,
            default_workspace_root=ws_path,
        )

        test_app = FastAPI()
        test_app.include_router(memory_drift_router, prefix="/api/memory")
        test_app.dependency_overrides[get_memory_drift_service] = lambda: service

        with TestClient(test_app) as client:
            yield client, ws_path


def test_check_memory_drift_pristine_api(drift_test_client: tuple[TestClient, Path]) -> None:
    """Verify memory statement matching real workspace remains pristine without warning."""
    client, ws_path = drift_test_client
    resp = client.post(
        "/api/memory/drift/check",
        json={
            "memory_id": "mem-valid",
            "content": "Use src/calculator.py class Calculator to perform mathematical calculations.",
            "workspace_root": str(ws_path),
            "recorded_path": "src/calculator.py",
            "recorded_symbol": "Calculator",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["memory_id"] == "mem-valid"
    assert data["is_drifted"] is False
    assert data["confidence_penalty"] == 0.0
    assert len(data["findings"]) == 0
    assert "[⚠️ 过时警告" not in data["decorated_content"]


def test_check_memory_drift_missing_file_api(drift_test_client: tuple[TestClient, Path]) -> None:
    """Verify referencing nonexistent or deleted files triggers drift warning."""
    client, ws_path = drift_test_client
    resp = client.post(
        "/api/memory/drift/check",
        json={
            "memory_id": "mem-missing-file",
            "content": "Old config stored in config/deleted_settings.json",
            "workspace_root": str(ws_path),
            "recorded_path": "config/deleted_settings.json",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["is_drifted"] is True
    assert data["confidence_penalty"] == 0.5
    assert len(data["findings"]) >= 1
    assert any(f["drift_type"] == "file_not_found" for f in data["findings"])
    assert "[⚠️ 过时警告" in data["decorated_content"]


def test_check_memory_drift_missing_symbol_api(drift_test_client: tuple[TestClient, Path]) -> None:
    """Verify deleted or renamed symbols trigger symbol_not_found drift warning."""
    client, ws_path = drift_test_client
    resp = client.post(
        "/api/memory/drift/check",
        json={
            "memory_id": "mem-missing-sym",
            "content": "Invoke NonExistentMethod on calculator class.",
            "workspace_root": str(ws_path),
            "recorded_path": "src/calculator.py",
            "recorded_symbol": "NonExistentMethod",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["is_drifted"] is True
    assert data["confidence_penalty"] == 0.5
    assert any(f["drift_type"] == "symbol_not_found" for f in data["findings"])
    assert "[⚠️ 过时警告" in data["decorated_content"]


def test_check_batch_memory_drift_api(drift_test_client: tuple[TestClient, Path]) -> None:
    """Verify batch evaluation properly aggregates clean and drifted memories."""
    client, ws_path = drift_test_client
    resp = client.post(
        "/api/memory/drift/check-batch",
        json={
            "items": [
                {
                    "memory_id": "item-1",
                    "content": "Call src/calculator.py class Calculator",
                    "recorded_path": "src/calculator.py",
                    "recorded_symbol": "Calculator",
                },
                {
                    "memory_id": "item-2",
                    "content": "Look at docs/missing_guide.md for deployment steps",
                    "recorded_path": "docs/missing_guide.md",
                },
            ],
            "workspace_root": str(ws_path),
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_checked"] == 2
    assert data["drifted_count"] == 1
    assert len(data["results"]) == 2
    assert data["results"][0]["is_drifted"] is False
    assert data["results"][1]["is_drifted"] is True
