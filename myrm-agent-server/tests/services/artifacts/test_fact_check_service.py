"""Unit tests for FactCheckService deliverable persistence and loading."""

from __future__ import annotations

import json
from pathlib import Path

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.api import (
    ConflictSeverity,
    FactCheckItem,
    FactCheckSheet,
    ResolutionStatus,
    SourceClaim,
)
from myrm_agent_harness.core.artifacts.manifest import (
    DeliverableCategory,
    DeliverableStatus,
)

from app.services.artifacts.fact_check_service import FactCheckService


def test_persist_fact_check_sheet(tmp_path: Path) -> None:
    vault = ArtifactVault(str(tmp_path))
    service = FactCheckService(vault)

    src1 = SourceClaim(
        source_uri="vault://meeting_minutes.docx",
        document_title="内测发布会纪要.docx",
        line_anchor="L42-L45",
        claimed_value="1699元",
        snippet="内测体验价 1699 元",
        timestamp_hint="2026-07-15",
    )
    src2 = SourceClaim(
        source_uri="vault://official_announcement.pdf",
        document_title="正式发布会定价通告.pdf",
        line_anchor="P3",
        claimed_value="1999元",
        snippet="官方首发零售价 1999 元，首发特惠 1799 元",
        timestamp_hint="2026-08-20",
    )

    item1 = FactCheckItem(
        claim_topic="官方首发零售价",
        severity=ConflictSeverity.CRITICAL,
        status=ResolutionStatus.RESOLVED,
        sources=[src1, src2],
        adopted_value="1999元 (首发优惠1799元)",
        resolution_rationale="8月20日高管定稿邮件晚于7月内测纪要，以最终上市通告为准",
        confidence_score=0.98,
        affected_artifacts=["01_articles/launch.md", "02_social_post/weibo.png"],
    )

    sheet = FactCheckSheet(
        sheet_id="fcs_demo_999",
        session_id="sess_alpha",
        title="双周发布多源事实核查清单",
        summary="识别出核心定价口径冲突，已采纳最新定稿决策",
        items=[item1],
    )

    items = service.persist_fact_check_sheet(sheet)
    assert len(items) == 2

    json_item, md_item = items[0], items[1]

    # Verify JSON item
    assert json_item.id == f"fci_json_{sheet.sheet_id[:8]}"
    assert json_item.relative_path == "05_fact_check/fact_check.json"
    assert json_item.category == DeliverableCategory.FACT_CHECK
    assert json_item.status == DeliverableStatus.VERIFIED
    assert json_item.mime_type == "application/json"
    assert json_item.vault_uri.startswith("vault://")
    assert json_item.metadata["sheet_id"] == "fcs_demo_999"
    assert json_item.metadata["critical_count"] == "1"

    # Verify Markdown item
    assert md_item.id == f"fci_md_{sheet.sheet_id[:8]}"
    assert md_item.relative_path == "05_fact_check/fact_check_report.md"
    assert md_item.category == DeliverableCategory.FACT_CHECK
    assert md_item.status == DeliverableStatus.VERIFIED
    assert md_item.mime_type == "text/markdown"
    assert md_item.vault_uri.startswith("vault://")

    # Verify content in vault
    raw_json = vault.get(json_item.vault_uri)
    parsed = json.loads(raw_json.decode("utf-8"))
    assert parsed["sheet_id"] == "fcs_demo_999"
    assert len(parsed["items"]) == 1

    raw_md = vault.get(md_item.vault_uri).decode("utf-8")
    assert "# 双周发布多源事实核查清单" in raw_md
    assert "官方首发零售价" in raw_md
    assert "内测发布会纪要.docx" in raw_md


def test_load_fact_check_sheet(tmp_path: Path) -> None:
    vault = ArtifactVault(str(tmp_path))
    service = FactCheckService(vault)

    sheet = FactCheckSheet(
        sheet_id="fcs_recover_test",
        title="恢复测试核查单",
        items=[
            FactCheckItem(
                claim_topic="芯片型号",
                severity=ConflictSeverity.WARNING,
                status=ResolutionStatus.RESOLVED,
                adopted_value="Snapdragon 8 Gen 4",
                resolution_rationale="供应链采购合同确认单",
            )
        ],
    )

    items = service.persist_fact_check_sheet(sheet)
    json_item = items[0]

    recovered = service.load_fact_check_sheet(json_item.vault_uri)
    assert recovered is not None
    assert recovered.sheet_id == "fcs_recover_test"
    assert recovered.title == "恢复测试核查单"
    assert len(recovered.items) == 1
    assert recovered.items[0].claim_topic == "芯片型号"
    assert recovered.items[0].adopted_value == "Snapdragon 8 Gen 4"


def test_load_fact_check_sheet_invalid_uri(tmp_path: Path) -> None:
    vault = ArtifactVault(str(tmp_path))
    service = FactCheckService(vault)

    assert service.load_fact_check_sheet("file:///invalid/path") is None
    assert service.load_fact_check_sheet("vault://non_existent_id_9999") is None


def test_persist_fact_check_sheet_custom_relative_dir(tmp_path: Path) -> None:
    vault = ArtifactVault(str(tmp_path))
    service = FactCheckService(vault)

    sheet = FactCheckSheet(
        sheet_id="fcs_custom_dir",
        title="自定义目录核查单",
        items=[],
    )

    items = service.persist_fact_check_sheet(sheet, relative_dir="custom_audit_dir")
    assert len(items) == 2
    assert items[0].relative_path == "custom_audit_dir/fact_check.json"
    assert items[1].relative_path == "custom_audit_dir/fact_check_report.md"
