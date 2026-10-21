from __future__ import annotations

from typing import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.fleet_router_router import router as fleet_router_router
from app.services.agent.fleet_router_service import FleetRouterService


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with isolated FleetRouterService and fleet_router_router attached."""
    FleetRouterService.reset_instance()
    app = FastAPI()
    app.include_router(fleet_router_router)
    with TestClient(app) as test_client:
        yield test_client
    FleetRouterService.reset_instance()


def test_gateway_crud_and_conflict_api(client: TestClient) -> None:
    # 1. List default gateways
    res = client.get("/fleet/gateways")
    assert res.status_code == 200
    gateways = res.json()
    assert len(gateways) >= 1
    assert any(g["gateway_id"] == "gw-local-host" for g in gateways)

    # 2. Register new linux gateway
    reg_res = client.post(
        "/fleet/gateways",
        json={
            "gateway_id": "gw-remote-linux",
            "label": "Ubuntu Remote Worker",
            "host": "192.168.1.100",
            "port": 9090,
            "protocol": "wss",
            "platform": "linux",
            "latency_ms": 15.2,
            "cpu_pct": 28.5,
            "mem_pct": 48.0,
            "active_agents": 3,
            "queue_depth": 0,
        },
    )
    assert reg_res.status_code == 201
    data = reg_res.json()
    assert data["gateway_id"] == "gw-remote-linux"
    assert data["status"] == "online"
    assert data["platform"] == "linux"

    # 3. Duplicate registration conflict (409)
    dup_res = client.post(
        "/fleet/gateways",
        json={
            "gateway_id": "gw-remote-linux",
            "label": "Duplicate Linux Gateway",
            "host": "192.168.1.100",
            "port": 9090,
            "platform": "linux",
        },
    )
    assert dup_res.status_code == 409

    # 4. Unregister gateway (200) and unregister non-existent (404)
    del_res = client.delete("/fleet/gateways/gw-remote-linux")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "unregistered"

    del_404 = client.delete("/fleet/gateways/gw-unknown")
    assert del_404.status_code == 404


def test_heartbeat_and_degraded_api(client: TestClient) -> None:
    # 1. Successful heartbeat on local gateway
    hb_res = client.post(
        "/fleet/gateways/gw-local-host/heartbeat",
        json={
            "cpu_pct": 18.0,
            "mem_pct": 40.0,
            "active_agents": 2,
            "queue_depth": 0,
            "latency_ms": 2.5,
        },
    )
    assert hb_res.status_code == 200
    assert hb_res.json()["status"] == "online"

    # 2. High latency degrades gateway status
    deg_res = client.post(
        "/fleet/gateways/gw-local-host/heartbeat",
        json={
            "cpu_pct": 90.0,
            "mem_pct": 85.0,
            "active_agents": 10,
            "queue_depth": 5,
            "latency_ms": 650.0,
        },
    )
    assert deg_res.status_code == 200
    assert deg_res.json()["status"] == "degraded"

    # 3. Heartbeat on non-existent gateway (404)
    hb_404 = client.post(
        "/fleet/gateways/gw-ghost/heartbeat",
        json={
            "cpu_pct": 0.0,
            "mem_pct": 0.0,
            "active_agents": 0,
            "queue_depth": 0,
            "latency_ms": 0.0,
        },
    )
    assert hb_404.status_code == 404


def test_profile_registration_and_host_context_injection_api(client: TestClient) -> None:
    # 1. Register a profile on gw-local-host
    prof_res = client.post(
        "/fleet/profiles",
        json={
            "profile_id": "prof-backend-lead",
            "gateway_id": "gw-local-host",
            "name": "Backend Architect",
            "avatar": "🏗️",
            "role": "System Architect",
            "system_context": "Design robust microservices.",
            "is_active": True,
        },
    )
    assert prof_res.status_code == 201
    assert prof_res.json()["profile_id"] == "prof-backend-lead"

    # 2. Get injected context with host topology
    ctx_res = client.get("/fleet/profiles/prof-backend-lead/context")
    assert ctx_res.status_code == 200
    ctx_data = ctx_res.json()
    assert "[DISTRIBUTED FLEET HOST TOPOLOGY]" in ctx_data["injected_context"]
    assert "Gateway ID: gw-local-host" in ctx_data["injected_context"]
    assert ctx_data["host_badge"] is not None
    assert ctx_data["host_badge"]["gateway_id"] == "gw-local-host"


def test_offline_buffering_and_auto_healing_flush_api(client: TestClient) -> None:
    # 1. Set gw-local-host to offline
    client.post(
        "/fleet/gateways/gw-local-host/heartbeat",
        json={
            "cpu_pct": 0.0,
            "mem_pct": 0.0,
            "active_agents": 0,
            "queue_depth": 0,
            "latency_ms": 0.0,
            "status": "offline",
        },
    )

    # 2. Buffer commands while offline
    buf_res1 = client.post(
        "/fleet/buffer",
        json={
            "gateway_id": "gw-local-host",
            "profile_id": "prof-primary-orchestrator",
            "command_type": "deploy_service",
            "payload": {"service": "auth-api"},
        },
    )
    assert buf_res1.status_code == 201
    assert buf_res1.json()["command_id"].startswith("cmd-buf-")

    # 3. Flushing while offline triggers 503
    flush_offline = client.post("/fleet/gateways/gw-local-host/flush")
    assert flush_offline.status_code == 503

    # 4. Bring gateway back online
    client.post(
        "/fleet/gateways/gw-local-host/heartbeat",
        json={
            "cpu_pct": 12.0,
            "mem_pct": 30.0,
            "active_agents": 1,
            "queue_depth": 0,
            "latency_ms": 1.2,
            "status": "online",
        },
    )

    # 5. Flush succeeds and returns queued commands
    flush_online = client.post("/fleet/gateways/gw-local-host/flush")
    assert flush_online.status_code == 200
    data = flush_online.json()
    assert data["flushed_count"] == 1
    assert data["commands"][0]["command_type"] == "deploy_service"


def test_cross_gateway_artifact_relay_and_topology_snapshot_api(client: TestClient) -> None:
    # 1. Register a second gateway
    client.post(
        "/fleet/gateways",
        json={
            "gateway_id": "gw-edge-pi",
            "label": "Raspberry Pi Edge",
            "host": "192.168.1.55",
            "port": 7070,
            "platform": "linux",
            "latency_ms": 45.0,
            "cpu_pct": 60.0,
            "mem_pct": 70.0,
            "active_agents": 1,
            "queue_depth": 0,
        },
    )

    # 2. Relay artifact between gateways
    relay_res = client.post(
        "/fleet/relay",
        json={
            "source_gateway": "gw-local-host",
            "target_gateway": "gw-edge-pi",
            "name": "firmware_patch.bin",
            "file_path": "dist/firmware.bin",
            "chunk_data": "BINARY_PAYLOAD_CHUNK_DATA_HEX_7F",
        },
    )
    assert relay_res.status_code == 201
    relay_data = relay_res.json()
    assert relay_data["artifact_id"].startswith("art-relay-")
    assert len(relay_data["sha256"]) == 64
    assert relay_data["is_verified"] is True

    # 3. Check topology snapshot
    topo_res = client.get("/fleet/topology")
    assert topo_res.status_code == 200
    topo_data = topo_res.json()
    assert topo_data["total_gateways"] == 2
    assert topo_data["online_gateways"] == 2
    assert len(topo_data["gateways"]) == 2
