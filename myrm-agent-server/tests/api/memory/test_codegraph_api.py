# [INPUT] TestClient and mock workspace files with Python function and class definitions.
# [OUTPUT] Unit tests validating /api/memory/codegraph/ endpoints (scan, impact, symbols, asset).
# [POS] tests.api.memory.test_codegraph_api

"""Unit tests for CodeGraph memory asset and impact analysis REST APIs."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.codegraph_router import router as codegraph_router


@pytest.fixture
def client() -> TestClient:
    test_app = FastAPI()
    test_app.include_router(codegraph_router, prefix="/api/memory")
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def temp_code_workspace(tmp_path: Path) -> Path:
    """Create a temporary Python workspace with interconnected modules."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    utils_file = workspace / "utils.py"
    utils_file.write_text(
        '''
def format_payload(data: str) -> str:
    return data.strip().upper()

def calculate_checksum(val: int) -> int:
    return val * 42
''',
        encoding="utf-8",
    )

    core_file = workspace / "core.py"
    core_file.write_text(
        '''
from utils import format_payload, calculate_checksum

class CoreHandler:
    def handle_request(self, message: str) -> str:
        formatted = format_payload(message)
        return formatted

def run_service() -> None:
    handler = CoreHandler()
    handler.handle_request("ping")
''',
        encoding="utf-8",
    )

    return workspace


def test_scan_workspace_api(client: TestClient, temp_code_workspace: Path) -> None:
    """Verify POST /api/memory/codegraph/scan indexes source files."""
    response = client.post(
        "/api/memory/codegraph/scan",
        json={
            "workspace_dir": str(temp_code_workspace),
            "incremental": False,
            "max_files": 100,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["scanned_files_count"] == 2
    assert data["total_symbols"] >= 4
    assert "version_hash" in data


def test_analyze_impact_api(client: TestClient, temp_code_workspace: Path) -> None:
    """Verify POST /api/memory/codegraph/impact computes ripple effect and blast radius."""
    # First ensure workspace is scanned
    client.post(
        "/api/memory/codegraph/scan",
        json={"workspace_dir": str(temp_code_workspace), "incremental": False},
    )

    # Analyze impact of format_payload
    response = client.post(
        "/api/memory/codegraph/impact",
        json={"symbol_name": "format_payload", "file_path": "utils.py"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["target_symbol_name"] == "format_payload"
    assert data["blast_radius"] >= 1
    assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert len(data["safety_recommendations"]) > 0


def test_query_symbols_and_asset_api(client: TestClient, temp_code_workspace: Path) -> None:
    """Verify GET /api/memory/codegraph/symbols and GET /api/memory/codegraph/asset."""
    client.post(
        "/api/memory/codegraph/scan",
        json={"workspace_dir": str(temp_code_workspace), "incremental": False},
    )

    # Query symbols
    sym_resp = client.get("/api/memory/codegraph/symbols?query=payload")
    assert sym_resp.status_code == 200
    sym_data = sym_resp.json()
    assert sym_data["total"] >= 1
    assert any("format_payload" in s["name"] for s in sym_data["symbols"])

    # Query asset metadata
    asset_resp = client.get("/api/memory/codegraph/asset")
    assert asset_resp.status_code == 200
    asset_data = asset_resp.json()
    assert asset_data["total_symbols"] >= 4
    assert len(asset_data["version_hash"]) > 0
