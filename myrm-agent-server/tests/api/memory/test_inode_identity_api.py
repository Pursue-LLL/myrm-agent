"""Integration and unit tests for directory inode identity API endpoints."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.inode_identity_router import router as inode_identity_router


@pytest.fixture
def test_app() -> FastAPI:
    """Create lightweight test FastAPI application hosting the inode identity router."""
    api_app = FastAPI()
    api_app.include_router(inode_identity_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_inode_identity_health(test_app: FastAPI) -> None:
    """Test health check probe endpoint for inode identity subsystem."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.get("/api/memory/inode-identity/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["module"] == "inode_identity"
        assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_resolve_directory_identity_endpoint(
    test_app: FastAPI, tmp_path: Path
) -> None:
    """Test resolving physical device and inode metadata for a local directory."""
    sample_dir = tmp_path / "test_workspace"
    sample_dir.mkdir()

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/memory/inode-identity/resolve",
            json={"target_path": str(sample_dir)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_accessible"] is True
        assert data["is_directory"] is True
        assert data["is_symlink"] is False
        assert data["real_path"] == os.path.realpath(str(sample_dir))

        ident = data["identity"]
        assert ident is not None
        assert ident["canonical_path"] == os.path.realpath(str(sample_dir))
        assert ident["physical_key"] == f"{ident['device_id']}:{ident['inode_id']}"


@pytest.mark.asyncio
async def test_verify_sync_brand_new_directory(
    test_app: FastAPI, tmp_path: Path
) -> None:
    """Test verifying an unrecorded directory returns register_new directive."""
    new_dir = tmp_path / "brand_new_repo"
    new_dir.mkdir()

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/memory/inode-identity/verify-sync",
            json={
                "target_path": str(new_dir),
                "known_identities": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "register_new"
        assert data["match_kind"] == "brand_new"
        assert data["needs_database_relocation"] is False
        assert data["identity"] is not None


@pytest.mark.asyncio
async def test_verify_sync_directory_move_detection(
    test_app: FastAPI, tmp_path: Path
) -> None:
    """Test moved or renamed directory is detected and relocation directive issued."""
    orig_dir = tmp_path / "repo_original"
    orig_dir.mkdir()
    real_orig = os.path.realpath(str(orig_dir))
    stat_res = os.stat(real_orig)

    known_item = {
        "canonical_path": real_orig,
        "device_id": int(stat_res.st_dev),
        "inode_id": int(stat_res.st_ino),
        "birth_time_ns": 123456789,
        "root_signature": "auto:test_sig",
        "fs_kind": "posix",
    }

    # Physically move directory
    moved_dir = tmp_path / "repo_renamed"
    orig_dir.rename(moved_dir)

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/memory/inode-identity/verify-sync",
            json={
                "target_path": str(moved_dir),
                "known_identities": [known_item],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "relocate_and_proceed"
        assert data["match_kind"] == "moved_or_renamed"
        assert data["needs_database_relocation"] is True
        assert data["old_path"] == real_orig
        assert data["new_path"] == os.path.realpath(str(moved_dir))


@pytest.mark.asyncio
async def test_verify_sync_inode_reused_warning(
    test_app: FastAPI, tmp_path: Path
) -> None:
    """Test same path with mismatched inode emits rebuild_warning."""
    active_dir = tmp_path / "rebuilt_workspace"
    active_dir.mkdir()
    real_active = os.path.realpath(str(active_dir))
    stat_res = os.stat(real_active)

    # Recorded item has same path but different inode
    known_item = {
        "canonical_path": real_active,
        "device_id": int(stat_res.st_dev),
        "inode_id": int(stat_res.st_ino) + 999999,
        "birth_time_ns": 1000000,
        "root_signature": "auto:old_sig",
        "fs_kind": "posix",
    }

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/memory/inode-identity/verify-sync",
            json={
                "target_path": str(active_dir),
                "known_identities": [known_item],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "rebuild_warning"
        assert data["match_kind"] == "inode_reused"
        assert data["needs_database_relocation"] is False
