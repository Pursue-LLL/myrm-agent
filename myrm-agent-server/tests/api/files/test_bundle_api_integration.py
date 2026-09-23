"""Integration tests for the Deliverable Bundles REST API.

Covers the three generic bundle routes end to end: manifest registration,
manifest retrieval, and streaming ZIP export with real archive contents.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.core.artifacts.manifest import (
    DeliverableCategory,
    DeliverableItem,
    DeliverableStatus,
)

from app.api.files.bundle_api import _get_vault
from app.api.files.bundle_api import router as bundle_router


def _make_vault_items(vault: ArtifactVault) -> list[DeliverableItem]:
    """Persist two real vault objects and describe them as deliverable items."""
    strategy_md = "# 发布会全案策略\n\n渠道投放节奏与预算分配。".encode()
    strategy_uri = vault.put(
        content=strategy_md,
        filename="launch_strategy.md",
        content_type="text/markdown",
        description="发布会策略方案",
    )
    schedule_csv = "stage,owner,due\n预热,市场部,D-14\n首发,运营部,D-day\n".encode()
    schedule_uri = vault.put(
        content=schedule_csv,
        filename="launch_schedule.csv",
        content_type="text/csv",
        description="发布会排期表",
    )

    return [
        DeliverableItem(
            id="dlv_strategy_01",
            filename="launch_strategy.md",
            relative_path="01_strategy/launch_strategy.md",
            title="发布会策略方案",
            category=DeliverableCategory.STRATEGY,
            status=DeliverableStatus.VERIFIED,
            vault_uri=strategy_uri,
            size_bytes=len(strategy_md),
            mime_type="text/markdown",
        ),
        DeliverableItem(
            id="dlv_schedule_01",
            filename="launch_schedule.csv",
            relative_path="06_schedule/launch_schedule.csv",
            title="发布会排期表",
            category=DeliverableCategory.SCHEDULE,
            status=DeliverableStatus.VERIFIED,
            vault_uri=schedule_uri,
            size_bytes=len(schedule_csv),
            mime_type="text/csv",
        ),
    ]


def test_bundle_api_manifest_crud_and_zip_export(tmp_path: Path) -> None:
    vault = ArtifactVault(str(tmp_path))
    items = _make_vault_items(vault)

    test_app = FastAPI()
    test_app.include_router(bundle_router, prefix="/api/v1/files/artifacts")
    test_app.dependency_overrides[_get_vault] = lambda: vault

    with TestClient(test_app) as client:
        # 1. POST /bundles — register the manifest
        create_resp = client.post(
            "/api/v1/files/artifacts/bundles",
            json={
                "bundle_id": "bundle_launch_001",
                "session_id": "session_alpha_01",
                "title": "发布会全套交付物清单",
                "task_prompt": "产出发布会全案并打包交付",
                "items": [item.model_dump() for item in items],
            },
        )
        assert create_resp.status_code == 200
        manifest_data = create_resp.json()
        assert manifest_data["bundle_id"] == "bundle_launch_001"
        assert manifest_data["title"] == "发布会全套交付物清单"
        assert len(manifest_data["items"]) == 2

        # 2. GET /bundles/{bundle_id} — read the persisted manifest back
        get_resp = client.get("/api/v1/files/artifacts/bundles/bundle_launch_001")
        assert get_resp.status_code == 200
        retrieved_manifest = get_resp.json()
        assert retrieved_manifest["title"] == "发布会全套交付物清单"
        assert retrieved_manifest["session_id"] == "session_alpha_01"

        # 3. GET /bundles/{bundle_id}/zip — stream and unpack the archive
        zip_resp = client.get("/api/v1/files/artifacts/bundles/bundle_launch_001/zip")
        assert zip_resp.status_code == 200
        assert zip_resp.headers["content-type"] == "application/zip"
        assert zip_resp.headers["X-Deliverable-Bundle-Id"] == "bundle_launch_001"

        with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
            namelist = zf.namelist()
            assert any("launch_strategy.md" in name for name in namelist)
            assert any("launch_schedule.csv" in name for name in namelist)

            strategy_name = next(name for name in namelist if name.endswith("launch_strategy.md"))
            strategy_bytes = zf.read(strategy_name)
            assert "发布会全案策略" in strategy_bytes.decode("utf-8")

            schedule_name = next(name for name in namelist if name.endswith("launch_schedule.csv"))
            schedule_bytes = zf.read(schedule_name)
            assert "预热" in schedule_bytes.decode("utf-8")


def test_get_unknown_bundle_returns_404(tmp_path: Path) -> None:
    vault = ArtifactVault(str(tmp_path))

    test_app = FastAPI()
    test_app.include_router(bundle_router, prefix="/api/v1/files/artifacts")
    test_app.dependency_overrides[_get_vault] = lambda: vault

    with TestClient(test_app) as client:
        resp = client.get("/api/v1/files/artifacts/bundles/bundle_missing")
        assert resp.status_code == 404


def test_zip_export_rejects_empty_bundle(tmp_path: Path) -> None:
    vault = ArtifactVault(str(tmp_path))

    test_app = FastAPI()
    test_app.include_router(bundle_router, prefix="/api/v1/files/artifacts")
    test_app.dependency_overrides[_get_vault] = lambda: vault

    with TestClient(test_app) as client:
        client.post(
            "/api/v1/files/artifacts/bundles",
            json={
                "bundle_id": "bundle_empty_001",
                "session_id": "session_beta_02",
                "title": "空交付包",
                "items": [],
            },
        )
        resp = client.get("/api/v1/files/artifacts/bundles/bundle_empty_001/zip")
        assert resp.status_code == 400
