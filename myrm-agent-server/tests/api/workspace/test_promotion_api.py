"""Integration tests for Workspace Scratchpad Promotion API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.workspace.promotion_router import router as promotion_router


@pytest.fixture(scope="function")
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MYRM_WORKSPACE_ROOT", str(tmp_path))
    test_app = FastAPI(title="Workspace Promotion Test App")
    test_app.include_router(promotion_router, prefix="/api/v1/workspace")
    return TestClient(test_app, raise_server_exceptions=False)


def test_promote_scratchpad_success(client: TestClient, tmp_path: Path) -> None:
    payload = {
        "title": "Quantum Algorithm Sandbox",
        "content": "# Quantum Phase Estimation\nImplementation details and simulation drafts.",
        "temporary_tags": ["physics", "simulation"],
        "init_readme": True,
    }

    response = client.post("/api/v1/workspace/promote", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["project_name"] == "quantum-algorithm-sandbox"
    assert "docs/scratchpad_origin.md" in data["created_files"]
    assert "README.md" in data["created_files"]
    assert "<!-- PROJECT_PROMOTED_FROM_SCRATCHPAD -->" in data["initial_context_prompt"]
    assert data["provenance_metadata"]["original_title"] == "Quantum Algorithm Sandbox"

    # Verify physical file persistence on disk
    target_dir = Path(data["target_directory"])
    assert target_dir.exists()
    assert (target_dir / "docs/scratchpad_origin.md").exists()
    assert (target_dir / "README.md").exists()
    assert "Quantum Phase Estimation" in (target_dir / "docs/scratchpad_origin.md").read_text(encoding="utf-8")


def test_promote_scratchpad_custom_project_name(client: TestClient, tmp_path: Path) -> None:
    payload = {
        "title": "Quick Draft",
        "content": "Short idea description.",
        "target_project_name": "custom-myrm-subsystem",
        "init_readme": False,
    }

    response = client.post("/api/v1/workspace/promote", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["project_name"] == "custom-myrm-subsystem"
    assert "docs/scratchpad_origin.md" in data["created_files"]
    assert "README.md" not in data["created_files"]


def test_promote_scratchpad_validation_error(client: TestClient) -> None:
    payload = {
        "title": "",  # Empty title violates min_length=1
        "content": "Some content",
    }

    response = client.post("/api/v1/workspace/promote", json=payload)
    assert response.status_code == 422
