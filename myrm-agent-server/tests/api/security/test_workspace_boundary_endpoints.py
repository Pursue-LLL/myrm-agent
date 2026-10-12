"""Integration tests for Workspace File Access Boundary Guard API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.workspace_boundary_router import (
    router as workspace_boundary_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting workspace_boundary_router."""
    test_app = FastAPI(title="Workspace Boundary Test App")
    test_app.include_router(workspace_boundary_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_resolve_and_evaluate_endpoints(client: TestClient, tmp_path: Path) -> None:
    ws_dir = tmp_path / "ws_demo"
    ws_dir.mkdir()
    sample_file = ws_dir / "index.ts"
    sample_file.write_text("console.log('hi');", encoding="utf-8")

    # 1. Resolve endpoint
    resolve_payload = {
        "target": "index.ts",
        "custom_root": str(ws_dir),
    }
    resp = client.post("/api/v1/security/workspace-boundary/resolve", json=resolve_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "ALLOWED"
    assert data["is_inside_workspace"] is True
    assert data["can_launch"] is True
    assert data["can_read"] is True

    # 2. Evaluate endpoint
    evaluate_payload = {
        "target": "index.ts",
        "action": "LAUNCH_DEFAULT_APP",
        "custom_root": str(ws_dir),
    }
    eval_resp = client.post("/api/v1/security/workspace-boundary/evaluate", json=evaluate_payload)
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["verdict"] == "ALLOWED"
    assert eval_data["can_launch"] is True


def test_parse_markdown_and_desktop_reveal_endpoints(client: TestClient, tmp_path: Path) -> None:
    ws_dir = tmp_path / "ws_demo"
    ws_dir.mkdir()
    readme_file = ws_dir / "README.md"
    readme_file.write_text("# Readme", encoding="utf-8")

    # 1. Parse markdown links
    md_payload = {
        "markdown_text": f"Read the guide at [README]({readme_file.resolve()}) and [web](https://example.com)",
        "custom_root": str(ws_dir),
    }
    parse_resp = client.post("/api/v1/security/workspace-boundary/parse-markdown", json=md_payload)
    assert parse_resp.status_code == 200
    parse_data = parse_resp.json()
    assert parse_data["total_links"] == 1
    assert parse_data["links"][0]["verdict"] == "ALLOWED"

    # 2. Desktop reveal verify safe path
    reveal_payload = {
        "target": "README.md",
        "custom_root": str(ws_dir),
    }
    reveal_resp = client.post("/api/v1/security/workspace-boundary/desktop-reveal-verify", json=reveal_payload)
    assert reveal_resp.status_code == 200
    reveal_data = reveal_resp.json()
    assert reveal_data["allowed"] is True
    assert str(readme_file.resolve()) in reveal_data["sanitized_path"]

    # 3. Desktop reveal verify missing path
    reveal_fail_payload = {
        "target": "missing.txt",
        "custom_root": str(ws_dir),
    }
    reveal_fail_resp = client.post(
        "/api/v1/security/workspace-boundary/desktop-reveal-verify", json=reveal_fail_payload
    )
    assert reveal_fail_resp.status_code == 200
    assert reveal_fail_resp.json()["allowed"] is False
