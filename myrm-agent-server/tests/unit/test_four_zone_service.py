"""Unit tests for FourZoneService in server layer.

[POS]
Verifies server-level orchestration of four-zone workspace initialization,
permission checks, safe draft replication, and forward artifact promotion.
"""

from __future__ import annotations

import os
from pathlib import Path

from myrm_agent_harness.core.security.four_zone import WorkspaceZone

from app.schemas.four_zone import (
    FourZoneCheckRequest,
    FourZoneInitRequest,
    FourZonePromotionRequest,
    FourZoneReplicateRequest,
)
from app.services.workspace.four_zone_service import FourZoneService


def test_four_zone_service_init_and_check(tmp_path: Path) -> None:
    service = FourZoneService()
    ws_root = str(tmp_path / "sandbox_workspace")

    # 1. Initialize
    init_res = service.initialize_workspace(FourZoneInitRequest(workspace_root=ws_root))
    assert init_res.status == "success"
    assert len(init_res.zones) == 4
    assert WorkspaceZone.ZONE_01_RAW.value in init_res.zones

    # 2. Check: READ allowed on 01
    raw_file = os.path.join(ws_root, WorkspaceZone.ZONE_01_RAW.value, "raw.pdf")
    read_chk = service.check_operation(FourZoneCheckRequest(file_path=raw_file, operation="read"))
    assert read_chk.allowed is True
    assert read_chk.zone == WorkspaceZone.ZONE_01_RAW.value

    # 3. Check: WRITE blocked on 01
    write_chk = service.check_operation(FourZoneCheckRequest(file_path=raw_file, operation="write"))
    assert write_chk.allowed is False
    assert write_chk.zone == WorkspaceZone.ZONE_01_RAW.value
    assert "strictly READ-ONLY" in write_chk.reason

    # 4. Check: WRITE permitted on 02
    draft_file = os.path.join(ws_root, WorkspaceZone.ZONE_02_DRAFT.value, "notes.md")
    draft_chk = service.check_operation(FourZoneCheckRequest(file_path=draft_file, operation="write"))
    assert draft_chk.allowed is True


def test_four_zone_service_replicate_and_promote(tmp_path: Path) -> None:
    service = FourZoneService()
    ws_root = str(tmp_path / "sandbox_workspace")
    service.initialize_workspace(FourZoneInitRequest(workspace_root=ws_root))

    # Write client original file to Zone 01
    raw_dir = Path(ws_root) / WorkspaceZone.ZONE_01_RAW.value
    (raw_dir / "brief.txt").write_text("Client source data", encoding="utf-8")

    # 1. Replicate to Zone 02 draft
    rep_res = service.replicate_to_draft(
        FourZoneReplicateRequest(
            workspace_root=ws_root,
            source_rel_path="brief.txt",
            draft_rel_path="draft_v1.txt",
        )
    )
    assert os.path.isfile(rep_res.draft_full_path)
    assert Path(rep_res.draft_full_path).read_text(encoding="utf-8") == "Client source data"

    # Modify draft in Zone 02
    Path(rep_res.draft_full_path).write_text("Analysis complete", encoding="utf-8")

    # 2. Promote draft -> canonical (02 -> 03)
    prom_res1 = service.promote(
        FourZonePromotionRequest(
            workspace_root=ws_root,
            source_rel_path="draft_v1.txt",
            target_rel_path="canonical_spec.txt",
            promotion_type="draft_to_canonical",
            reviewer_id="reviewer_alice",
        )
    )
    assert prom_res1.source_zone == WorkspaceZone.ZONE_02_DRAFT.value
    assert prom_res1.target_zone == WorkspaceZone.ZONE_03_CANONICAL.value
    assert os.path.isfile(prom_res1.target_path)

    # 3. Promote canonical -> deliverable (03 -> 04)
    prom_res2 = service.promote(
        FourZonePromotionRequest(
            workspace_root=ws_root,
            source_rel_path="canonical_spec.txt",
            target_rel_path="final_report.txt",
            promotion_type="canonical_to_deliverable",
            reviewer_id="manager_bob",
        )
    )
    assert prom_res2.source_zone == WorkspaceZone.ZONE_03_CANONICAL.value
    assert prom_res2.target_zone == WorkspaceZone.ZONE_04_DELIVERABLE.value
    assert Path(prom_res2.target_path).read_text(encoding="utf-8") == "Analysis complete"
