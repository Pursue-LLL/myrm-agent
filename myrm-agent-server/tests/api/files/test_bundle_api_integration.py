"""Integration tests for Deliverable Bundles REST API & FactCheck integration."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.api import (
    ConflictSeverity,
    FactCheckItem,
    FactCheckSheet,
    ResolutionStatus,
    SourceClaim,
)

from app.api.files.bundle_api import _get_vault
from app.api.files.bundle_api import router as bundle_router
from app.services.artifacts.fact_check_service import FactCheckService


def test_bundle_api_fact_check_integration(tmp_path: Path) -> None:
    vault = ArtifactVault(str(tmp_path))
    service = FactCheckService(vault)

    # 1. 模拟生成事实核查单
    src1 = SourceClaim(
        source_uri="vault://meeting.docx",
        document_title="草案.docx",
        claimed_value="1699元",
        line_anchor="L42",
    )
    src2 = SourceClaim(
        source_uri="vault://notice.pdf",
        document_title="通告.pdf",
        claimed_value="1999元",
        line_anchor="P2",
    )
    item = FactCheckItem(
        claim_topic="官方首发零售价",
        severity=ConflictSeverity.CRITICAL,
        status=ResolutionStatus.RESOLVED,
        sources=[src1, src2],
        adopted_value="1999元 (首发特惠1799元)",
        resolution_rationale="8月定稿通告晚于7月草案",
    )
    sheet = FactCheckSheet(
        sheet_id="fcs_bundle_e2e_01",
        session_id="session_alpha_01",
        title="发布会全案事实核查单",
        summary="完成核心定价冲突仲裁",
        items=[item],
    )

    deliverable_items = service.persist_fact_check_sheet(sheet)
    assert len(deliverable_items) == 2

    # 2. 构建独立测试 App 挂载 bundle_router
    test_app = FastAPI()
    test_app.include_router(bundle_router, prefix="/api/v1/files/artifacts")
    test_app.dependency_overrides[_get_vault] = lambda: vault

    with TestClient(test_app) as client:
        # POST /api/v1/files/artifacts/bundles
        create_resp = client.post(
            "/api/v1/files/artifacts/bundles",
            json={
                "bundle_id": "bundle_fact_001",
                "session_id": "session_alpha_01",
                "title": "发布会全套交付物清单",
                "items": [d.model_dump() for d in deliverable_items],
            },
        )
        assert create_resp.status_code == 200
        manifest_data = create_resp.json()
        assert manifest_data["bundle_id"] == "bundle_fact_001"
        assert len(manifest_data["items"]) == 2

        # GET /api/v1/files/artifacts/bundles/{bundle_id}
        get_resp = client.get("/api/v1/files/artifacts/bundles/bundle_fact_001")
        assert get_resp.status_code == 200
        retrieved_manifest = get_resp.json()
        assert retrieved_manifest["title"] == "发布会全套交付物清单"

        # GET /api/v1/files/artifacts/bundles/{bundle_id}/zip (验证真实流式 ZIP 导出与解压)
        zip_resp = client.get("/api/v1/files/artifacts/bundles/bundle_fact_001/zip")
        assert zip_resp.status_code == 200
        assert zip_resp.headers["content-type"] == "application/zip"

        with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
            namelist = zf.namelist()
            assert any("fact_check.json" in name for name in namelist)
            assert any("fact_check_report.md" in name for name in namelist)

            # 读取 zip 内部的 Markdown 并验证
            md_name = next(name for name in namelist if name.endswith("fact_check_report.md"))
            md_bytes = zf.read(md_name)
            assert "发布会全案事实核查单" in md_bytes.decode("utf-8")
            assert "官方首发零售价" in md_bytes.decode("utf-8")
            assert "1999元" in md_bytes.decode("utf-8")
