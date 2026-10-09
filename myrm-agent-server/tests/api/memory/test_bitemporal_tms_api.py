"""Integration and unit tests for bitemporal truth maintenance API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.bitemporal_tms_router import router as bitemporal_tms_router


@pytest.fixture
def test_app() -> FastAPI:
    """Create lightweight test FastAPI application hosting the bitemporal TMS router."""
    api_app = FastAPI()
    api_app.include_router(bitemporal_tms_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_bitemporal_tms_health(test_app: FastAPI) -> None:
    """Test health check probe endpoint for bitemporal TMS subsystem."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.get("/api/memory/bitemporal-tms/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["module"] == "bitemporal_truth_maintenance"
        assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_record_fact_and_temporal_query(test_app: FastAPI) -> None:
    """Test recording ground fact and querying across bitemporal coordinates."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. Record fact valid from 1000.0 onwards
        fact_payload = {
            "evidence_id": "fact-server-role",
            "content": "Server primary region is us-east-1",
            "valid_start": 1000.0,
            "valid_end": 2000.0,
            "known_start": 1050.0,
            "confidence": 0.95,
            "metadata": {"source": "config_sync"},
        }
        res_create = await client.post(
            "/api/memory/bitemporal-tms/facts",
            json=fact_payload,
        )
        assert res_create.status_code == 201
        data_create = res_create.json()
        assert data_create["evidence_id"] == "fact-server-role"
        assert data_create["evidence_type"] == "fact"
        assert data_create["confidence"] == 0.95
        assert data_create["bitemporal"]["valid_interval"]["start"] == 1000.0
        assert data_create["bitemporal"]["valid_interval"]["end"] == 2000.0

        # 2. Query at valid=1500, known=1500 (Active)
        query_payload = {
            "as_of_valid_time": 1500.0,
            "as_of_known_time": 1500.0,
            "require_active_support": True,
        }
        res_q = await client.post(
            "/api/memory/bitemporal-tms/query",
            json=query_payload,
        )
        assert res_q.status_code == 200
        data_q = res_q.json()
        assert data_q["total"] >= 1
        ids = [r["evidence_id"] for r in data_q["records"]]
        assert "fact-server-role" in ids

        # 3. Query at valid=500 (Before valid start: Inactive)
        res_past = await client.post(
            "/api/memory/bitemporal-tms/query",
            json={"as_of_valid_time": 500.0, "as_of_known_time": 1500.0},
        )
        assert res_past.status_code == 200
        ids_past = [r["evidence_id"] for r in res_past.json()["records"]]
        assert "fact-server-role" not in ids_past


@pytest.mark.asyncio
async def test_derive_inference_and_retraction_cascade(test_app: FastAPI) -> None:
    """Test inference derivation and cascading active support invalidation upon retraction."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. Record two premise facts
        await client.post(
            "/api/memory/bitemporal-tms/facts",
            json={
                "evidence_id": "f-perm-1",
                "content": "User has identity card",
                "valid_start": 0.0,
                "known_start": 0.0,
            },
        )
        await client.post(
            "/api/memory/bitemporal-tms/facts",
            json={
                "evidence_id": "f-badge-2",
                "content": "User has security badge",
                "valid_start": 0.0,
                "known_start": 0.0,
            },
        )

        # 2. Derive inference supported by both
        inf_payload = {
            "inference_id": "inf-entry-access",
            "content": "User is authorized to enter server room",
            "premise_ids": ["f-perm-1", "f-badge-2"],
            "justification": "Requires identity card and security badge",
            "valid_start": 0.0,
            "known_start": 0.0,
            "causal_distance": 1,
        }
        res_inf = await client.post(
            "/api/memory/bitemporal-tms/inferences",
            json=inf_payload,
        )
        assert res_inf.status_code == 201
        assert res_inf.json()["evidence_id"] == "inf-entry-access"

        # 3. Verify inference is active at t=50
        res_check_1 = await client.post(
            "/api/memory/bitemporal-tms/query",
            json={"as_of_valid_time": 50.0, "as_of_known_time": 50.0},
        )
        ids_1 = [r["evidence_id"] for r in res_check_1.json()["records"]]
        assert "inf-entry-access" in ids_1

        # 4. Retract badge premise at t=100
        res_retract = await client.post(
            "/api/memory/bitemporal-tms/retract",
            json={"evidence_id": "f-badge-2", "retracted_at": 100.0},
        )
        assert res_retract.status_code == 200
        assert res_retract.json()["success"] is True

        # 5. Query at t=150: inference must lose active support and disappear from active query
        res_check_2 = await client.post(
            "/api/memory/bitemporal-tms/query",
            json={"as_of_valid_time": 150.0, "as_of_known_time": 150.0},
        )
        ids_2 = [r["evidence_id"] for r in res_check_2.json()["records"]]
        assert "f-badge-2" not in ids_2
        assert "inf-entry-access" not in ids_2


@pytest.mark.asyncio
async def test_project_snapshot(test_app: FastAPI) -> None:
    """Test projecting partitioned truth maintenance snapshot."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # Create fact, then retract it
        await client.post(
            "/api/memory/bitemporal-tms/facts",
            json={
                "evidence_id": "f-snap-temp",
                "content": "Temporary observation",
                "valid_start": 0.0,
                "known_start": 0.0,
            },
        )
        await client.post(
            "/api/memory/bitemporal-tms/retract",
            json={"evidence_id": "f-snap-temp", "retracted_at": 30.0},
        )

        res_snap = await client.post(
            "/api/memory/bitemporal-tms/snapshot",
            json={"as_of_valid_time": 50.0, "as_of_known_time": 50.0},
        )
        assert res_snap.status_code == 200
        snap_data = res_snap.json()
        retracted_ids = [r["evidence_id"] for r in snap_data["retracted_evidences"]]
        assert "f-snap-temp" in retracted_ids
        assert snap_data["total_count"] >= 1
