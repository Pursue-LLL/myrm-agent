# [POS]: tests/api/memory/test_mem_cube_api.py
# [INPUT]: app.api.memory.mem_cube_router, app.services.memory.mem_cube_service, FastAPI app
# [OUTPUT]: Integration API tests for Memory Cube Scoped Isolation & Dynamic Mounting Suite (Item 124)

"""Integration API tests for Memory Cube Scoped Isolation & Dynamic Mounting Suite (Item 124)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.mem_cube_router import (
    router as mem_cube_router,
)
from app.services.memory.mem_cube_service import (
    MemCubeService,
    get_mem_cube_service,
)


@pytest.fixture
def isolated_service() -> MemCubeService:
    """Provides an isolated MemCubeService instance."""
    return MemCubeService()


@pytest.fixture
def test_app(isolated_service: MemCubeService) -> FastAPI:
    """Creates a test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(mem_cube_router, prefix="/api/memory")
    app.dependency_overrides[get_mem_cube_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_create_and_get_cube_api(test_app: FastAPI) -> None:
    """Validate Memory Cube lifecycle: creation, retrieval, listing, and deletion."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create Cube
        payload = {
            "name": "Architecture Guidelines",
            "scope_type": "project_workspace",
            "owner_id": "/workspace/open-perplexity",
            "description": "Core architecture standards and clean code policies.",
            "is_read_only": False,
        }
        res_create = await client.post("/api/memory/cubes", json=payload)
        assert res_create.status_code == 201
        data = res_create.json()
        cube_id = data["cube_id"]
        assert data["name"] == "Architecture Guidelines"
        assert data["scope_type"] == "project_workspace"

        # 2. Get Cube by ID
        res_get = await client.get(f"/api/memory/cubes/{cube_id}")
        assert res_get.status_code == 200
        assert res_get.json()["cube_id"] == cube_id

        # 3. List Cubes
        res_list = await client.get("/api/memory/cubes?scope_type=project_workspace")
        assert res_list.status_code == 200
        cubes = res_list.json()
        assert any(c["cube_id"] == cube_id for c in cubes)

        # 4. Delete Cube
        res_del = await client.delete(f"/api/memory/cubes/{cube_id}")
        assert res_del.status_code == 204

        # 5. Verify 404 after deletion
        res_get_del = await client.get(f"/api/memory/cubes/{cube_id}")
        assert res_get_del.status_code == 404


@pytest.mark.asyncio
async def test_mount_policy_and_scoped_write_api(test_app: FastAPI) -> None:
    """Validate dynamic read/write mount policies and write enforcement."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a read-only shared cube and an agent private cube
        res_shared = await client.post(
            "/api/memory/cubes",
            json={
                "name": "Global Rules",
                "scope_type": "global_shared",
                "is_read_only": True,
            },
        )
        assert res_shared.status_code == 201
        shared_cube_id = res_shared.json()["cube_id"]

        res_private = await client.post(
            "/api/memory/cubes",
            json={
                "name": "Agent Private Memory",
                "scope_type": "agent_private",
                "owner_id": "agent-lead",
                "is_read_only": False,
            },
        )
        assert res_private.status_code == 201
        private_cube_id = res_private.json()["cube_id"]

        # 2. Configure mount policy: read from shared + private, write ONLY to private
        policy_payload = {
            "readable_cube_ids": [shared_cube_id, private_cube_id],
            "writable_cube_ids": [private_cube_id],
            "default_write_cube_id": private_cube_id,
            "strict_isolation": True,
        }
        res_policy = await client.post(
            "/api/memory/cubes/mount/agent-lead",
            json=policy_payload,
        )
        assert res_policy.status_code == 200
        policy_data = res_policy.json()
        assert policy_data["agent_id"] == "agent-lead"
        assert shared_cube_id in policy_data["readable_cube_ids"]
        assert policy_data["writable_cube_ids"] == [private_cube_id]

        # 3. Unauthorized write to read-only shared cube -> must fail
        illegal_write = await client.post(
            "/api/memory/cubes/write",
            json={
                "agent_id": "agent-lead",
                "content": "Malicious override of shared standards.",
                "target_cube_id": shared_cube_id,
            },
        )
        assert illegal_write.status_code == 200
        illegal_res = illegal_write.json()
        assert not illegal_res["success"]
        assert "not authorized" in (illegal_res["rejection_reason"] or "").lower()

        # 4. Authorized write to private cube -> succeeds
        legal_write = await client.post(
            "/api/memory/cubes/write",
            json={
                "agent_id": "agent-lead",
                "content": "Agent task notes: finished phase 1.",
            },
        )
        assert legal_write.status_code == 200
        legal_res = legal_write.json()
        assert legal_res["success"]
        assert legal_res["destination_cube_id"] == private_cube_id


@pytest.mark.asyncio
async def test_federated_multi_cube_query_api(test_app: FastAPI) -> None:
    """Validate federated search across multiple mounted readable cubes."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create two cubes
        res1 = await client.post(
            "/api/memory/cubes",
            json={"name": "Frontend Standards", "scope_type": "project_workspace"},
        )
        res2 = await client.post(
            "/api/memory/cubes",
            json={"name": "Backend Standards", "scope_type": "project_workspace"},
        )
        c1 = res1.json()["cube_id"]
        c2 = res2.json()["cube_id"]

        # Mount both to agent-fullstack
        await client.post(
            "/api/memory/cubes/mount/agent-fullstack",
            json={
                "readable_cube_ids": [c1, c2],
                "writable_cube_ids": [c1],
                "default_write_cube_id": c1,
            },
        )

        # Write to both
        await client.post(
            "/api/memory/cubes/write",
            json={"agent_id": "agent-fullstack", "content": "Vue and React frontend architecture.", "target_cube_id": c1},
        )
        # Authorize write to c2 temporarily for setup
        await client.post(
            "/api/memory/cubes/mount/agent-fullstack",
            json={
                "readable_cube_ids": [c1, c2],
                "writable_cube_ids": [c1, c2],
                "default_write_cube_id": c2,
            },
        )
        await client.post(
            "/api/memory/cubes/write",
            json={"agent_id": "agent-fullstack", "content": "FastAPI and Python backend architecture.", "target_cube_id": c2},
        )

        # Federated query for "architecture"
        query_res = await client.post(
            "/api/memory/cubes/query",
            json={
                "agent_id": "agent-fullstack",
                "query": "architecture",
                "limit": 5,
            },
        )
        assert query_res.status_code == 200
        q_data = query_res.json()
        assert q_data["total_found"] == 2
        assert len(q_data["items"]) == 2

        # Verify overview
        overview_res = await client.get("/api/memory/cubes/matrix/overview")
        assert overview_res.status_code == 200
        ov = overview_res.json()
        assert ov["total_cubes"] >= 2
        assert ov["system_healthy"] is True
