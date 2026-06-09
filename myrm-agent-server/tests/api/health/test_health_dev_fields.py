"""Health endpoint exposes dev_mode and listen port for frontend diagnostics."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="health")
from app.server.runtime_dev_info import set_runtime_listen


def test_health_includes_runtime_dev_fields() -> None:
    set_runtime_listen(port=8080, host="127.0.0.1", dev_mode="split_dev")
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["dev_mode"] == "split_dev"
    assert body["listen_port"] == 8080
    assert body["frontend_proxy_port"] == 8080


def test_health_standalone_proxy_port() -> None:
    set_runtime_listen(port=25808, host="127.0.0.1", dev_mode="standalone_webui")
    client = TestClient(app)
    body = client.get("/api/v1/health").json()
    assert body["dev_mode"] == "standalone_webui"
    assert body["listen_port"] == 25808
    assert body["frontend_proxy_port"] == 25808
