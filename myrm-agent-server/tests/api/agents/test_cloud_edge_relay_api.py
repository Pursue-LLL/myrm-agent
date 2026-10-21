"""API integration tests for Hybrid Cloud-Edge Sandbox Relay & Artifact Sync (Item 58).

[INPUT]
- app.api.agents.cloud_edge_relay_router.router
- app.services.agent.cloud_edge_relay_service.get_cloud_edge_relay_service

[OUTPUT]
- Pytest test cases validating bidirectional artifact chunk append,
  optimistic CAS concurrency guard, aggregated content reconstruction,
  and SSRF-protected local egress relay execution.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_cloud_edge_relay_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.cloud_edge_relay_router import router as cloud_edge_relay_router
from app.services.agent.cloud_edge_relay_service import (
    CloudEdgeRelayService,
    get_cloud_edge_relay_service,
)


@pytest.fixture
def service() -> CloudEdgeRelayService:
    """Isolated CloudEdgeRelayService fixture for test execution."""
    srv = CloudEdgeRelayService()
    srv.reset()
    return srv


@pytest.fixture
def client(service: CloudEdgeRelayService) -> Generator[TestClient, None, None]:
    """TestClient fixture with injected CloudEdgeRelayService dependency."""
    app = FastAPI()
    app.include_router(cloud_edge_relay_router)
    app.dependency_overrides[get_cloud_edge_relay_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_register_and_get_artifact_api(client: TestClient) -> None:
    session_id = "test-relay-session-01"
    artifact_id = "sales_q3.csv"

    # 1. Register artifact
    reg_payload = {
        "session_id": session_id,
        "artifact_id": artifact_id,
        "name": "Q3 Sales Dataset",
        "initial_content": "id,product,revenue\n1,Widget,100",
        "initial_rows": 2,
        "author_role": "local_sandbox",
    }
    resp = client.post("/agents/cloud-edge-relay/artifacts/register", json=reg_payload)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["success"] is True
    assert data["state"]["artifact_id"] == artifact_id
    assert data["state"]["current_version"] == 1
    assert data["state"]["total_rows"] == 2

    # 2. Get artifact snapshot
    get_resp = client.get(f"/agents/cloud-edge-relay/artifacts/{artifact_id}")
    assert get_resp.status_code == 200
    state = get_resp.json()["data"]
    assert state["name"] == "Q3 Sales Dataset"
    assert len(state["chunks"]) == 1
    assert state["chunks"][0]["author_role"] == "local_sandbox"


def test_append_artifact_chunk_and_aggregate_content_api(client: TestClient) -> None:
    session_id = "test-relay-session-02"
    artifact_id = "metrics.log"

    # Register initial
    client.post(
        "/agents/cloud-edge-relay/artifacts/register",
        json={
            "session_id": session_id,
            "artifact_id": artifact_id,
            "name": "System Metrics Log",
            "initial_content": "START 10:00:00",
            "author_role": "local_sandbox",
        },
    )

    # Cloud sandbox appends overnight batch
    append_payload = {
        "session_id": session_id,
        "artifact_id": artifact_id,
        "content_delta": "BATCH_01 SUCCESS\nBATCH_02 SUCCESS",
        "author_role": "cloud_sandbox",
        "expected_version": 1,
        "row_count": 2,
    }
    append_resp = client.post(
        "/agents/cloud-edge-relay/artifacts/append", json=append_payload
    )
    assert append_resp.status_code == 200
    res_data = append_resp.json()["data"]
    assert res_data["success"] is True
    assert res_data["state"]["current_version"] == 2
    assert res_data["state"]["total_rows"] == 3

    # Reconstruct aggregated content
    content_resp = client.get(
        f"/agents/cloud-edge-relay/artifacts/{artifact_id}/content"
    )
    assert content_resp.status_code == 200
    content_data = content_resp.json()["data"]
    assert "START 10:00:00" in content_data["aggregated_content"]
    assert "BATCH_01 SUCCESS" in content_data["aggregated_content"]


def test_cas_version_conflict_handling_api(client: TestClient) -> None:
    session_id = "test-relay-session-03"
    artifact_id = "conflict_target.txt"

    client.post(
        "/agents/cloud-edge-relay/artifacts/register",
        json={
            "session_id": session_id,
            "artifact_id": artifact_id,
            "name": "Conflict Target",
            "initial_content": "Initial Line",
        },
    )

    # Attempt append with outdated expected_version 999
    bad_append = {
        "session_id": session_id,
        "artifact_id": artifact_id,
        "content_delta": "Divergent Line",
        "author_role": "cloud_sandbox",
        "expected_version": 999,
    }
    conflict_resp = client.post(
        "/agents/cloud-edge-relay/artifacts/append", json=bad_append
    )
    assert conflict_resp.status_code == 409
    assert "CAS version conflict" in conflict_resp.json()["detail"]


def test_dispatch_local_egress_relay_ok_and_complete_api(client: TestClient) -> None:
    session_id = "test-relay-session-04"

    # 1. Dispatch valid public outbound request
    dispatch_payload = {
        "session_id": session_id,
        "target_url": "https://api.github.com/repos/myrm/releases",
        "intent": "Crawl latest release tag from restricted cloud sandbox",
        "source_node": "cloud_sandbox",
    }
    disp_resp = client.post(
        "/agents/cloud-edge-relay/relay/dispatch", json=dispatch_payload
    )
    assert disp_resp.status_code == 200
    disp_data = disp_resp.json()["data"]
    relay_id = disp_data["relay_id"]
    assert disp_data["status"] == "relay_requested"
    assert disp_data["status_code"] == 202

    # 2. Complete relay fetch from local node
    comp_payload = {
        "session_id": session_id,
        "relay_id": relay_id,
        "status_code": 200,
        "extracted_data": '{"tag": "v1.2.0"}',
        "latency_ms": 120.5,
    }
    comp_resp = client.post(
        "/agents/cloud-edge-relay/relay/complete", json=comp_payload
    )
    assert comp_resp.status_code == 200
    comp_data = comp_resp.json()["data"]
    assert comp_data["status"] == "relay_completed"
    assert comp_data["success"] is True


def test_dispatch_local_egress_relay_ssrf_blocked_api(client: TestClient) -> None:
    session_id = "test-relay-session-05"

    # Attempt fetching metadata endpoint (SSRF attack simulation)
    forbidden_payload = {
        "session_id": session_id,
        "target_url": "http://169.254.169.254/latest/meta-data/",
        "intent": "Exfiltrate AWS instance metadata",
        "source_node": "cloud_sandbox",
    }
    resp = client.post(
        "/agents/cloud-edge-relay/relay/dispatch", json=forbidden_payload
    )
    assert resp.status_code == 400
    assert "SSRF policy violation" in resp.json()["detail"]


def test_list_artifacts_and_provenance_api(client: TestClient) -> None:
    session_id = "test-relay-session-06"
    art_a = "art_a.json"

    client.post(
        "/agents/cloud-edge-relay/artifacts/register",
        json={
            "session_id": session_id,
            "artifact_id": art_a,
            "name": "Audit Log A",
            "initial_content": '{"event": "init"}',
            "author_role": "local_sandbox",
        },
    )

    client.post(
        "/agents/cloud-edge-relay/artifacts/append",
        json={
            "session_id": session_id,
            "artifact_id": art_a,
            "content_delta": '{"event": "append_1"}',
            "author_role": "cloud_sandbox",
        },
    )

    # 1. List artifacts
    list_resp = client.get("/agents/cloud-edge-relay/artifacts")
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total_count"] >= 1

    # 2. Check provenance chain
    prov_resp = client.get(
        f"/agents/cloud-edge-relay/artifacts/{art_a}/provenance"
    )
    assert prov_resp.status_code == 200
    prov_data = prov_resp.json()["data"]
    assert prov_data["artifact_id"] == art_a
    timeline = prov_data["timeline"]
    assert len(timeline) == 2
    assert timeline[0]["author_role"] == "local_sandbox"
    assert timeline[1]["author_role"] == "cloud_sandbox"
