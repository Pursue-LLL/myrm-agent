"""
[INPUT]
- FastAPI test client
- Dev ports router under /api/v1/dev-ports

[OUTPUT]
- Unit test suite verifying dev ports listing, registration, closing, and tunnel URL generation

[POS]
Unit tests for DevPortsListeningBarAndServicePreviewHub API.
"""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.dev_ports.routes import router as dev_ports_router


@pytest.fixture
def ports_client() -> TestClient:
    app = FastAPI()
    app.include_router(dev_ports_router, prefix="/api/v1/dev-ports")
    return TestClient(app)


def test_list_dev_ports(ports_client: TestClient):
    response = ports_client.get("/api/v1/dev-ports")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    ports = [p["port"] for p in data]
    assert 3000 in ports or 5173 in ports


def test_register_dev_port(ports_client: TestClient):
    payload = {
        "port": 8080,
        "process_name": "uvicorn",
        "pid": 9812,
        "protocol": "http",
    }
    response = ports_client.post("/api/v1/dev-ports", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["port"] == 8080
    assert data["process_name"] == "uvicorn"
    assert data["url"] == "http://localhost:8080"
    assert data["status"] == "listening"


def test_create_dev_port_tunnel(ports_client: TestClient):
    response = ports_client.post("/api/v1/dev-ports/3000/tunnel")
    assert response.status_code == 200
    data = response.json()

    assert data["port"] == 3000
    assert "tunnel_url" in data
    assert data["tunnel_url"].startswith("https://")
    assert data["expires_in_seconds"] == 3600


def test_close_dev_port_and_404_on_subsequent(ports_client: TestClient):
    # First register temporary port 8888
    register_res = ports_client.post(
        "/api/v1/dev-ports",
        json={"port": 8888, "process_name": "temp-server"},
    )
    assert register_res.status_code == 201

    # Close port
    del_res = ports_client.delete("/api/v1/dev-ports/8888")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Closing again should raise 404
    not_found_res = ports_client.delete("/api/v1/dev-ports/8888")
    assert not_found_res.status_code == 404


def test_sniff_and_register_dev_ports(ports_client: TestClient):
    log_text = """
    > my-astro-site@1.0.0 dev
    > astro dev

     astro  v4.0.0 ready in 150 ms

     Local: http://localhost:4321/
    """
    response = ports_client.post("/api/v1/dev-ports/sniff", json={"log_text": log_text})
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    ports = [p["port"] for p in data]
    assert 4321 in ports

    # Verify it is now in the active ports listing
    list_res = ports_client.get("/api/v1/dev-ports")
    assert list_res.status_code == 200
    all_ports = [p["port"] for p in list_res.json()]
    assert 4321 in all_ports

