"""Integration tests for InstalledSkillSupplyChainRescan full flow.

Tests full chain across:
1. Real disk skill directories with real manifests (package.json, requirements.txt)
2. Dependency extraction & offline KnownCompromisedAdvisoryCatalog matching
3. OSV vulnerability scanning & TTL caching
4. AdvisoryAckRegistry user acknowledgment & dismissal flow
5. Auto-quarantine / disabling in skills_service.user_config
6. AppEventBus SKILL_POOL_UPDATED broadcast
7. Skills API /api/v1/skills/rescan and /api/v1/skills/advisories/ack REST endpoints
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.api import (
    AdvisoryAckRegistry,
    InstalledSkillRescanEngine,
)
from myrm_agent_harness.backends.skills.scanning.vuln_cache import VulnScanCache
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.api.skills import rescan
from app.core.skills.discovery.rescan_service import SkillRescanService
from app.core.skills.store.service import SkillsService
from app.services.event.app_event_bus import AppEventType, get_event_bus


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path / "storage"))


@pytest.fixture(autouse=True)
def bind_skills_service(storage: LocalStorageBackend) -> SkillsService:
    service = SkillsService(storage=storage)
    with (
        patch("app.core.skills.store.service.skills_service", service),
        patch("app.core.skills.effective_skill_ids.skills_service", service),
    ):
        yield service


@pytest.fixture
def rescan_client() -> TestClient:
    app = FastAPI(title="Skill Rescan Full Flow Integration")
    app.include_router(rescan.router, prefix="/api/v1/skills")
    return TestClient(app)


@pytest.mark.asyncio
async def test_full_supply_chain_rescan_compromise_and_quarantine_integration(
    tmp_path: Path,
    rescan_client: TestClient,
    bind_skills_service: SkillsService,
) -> None:
    """Full chain:

    1. Prepare clean skill & malicious/compromised skill on disk.
    2. Enable both in user_config.
    3. Trigger rescan via API.
    4. Assert clean skill remains active, compromised skill is auto-disabled/quarantined.
    5. Assert SKILL_POOL_UPDATED event published on event bus.
    6. Assert last report API returns correct counts.
    """
    skills_root = tmp_path / "installed_skills"
    skills_root.mkdir(parents=True, exist_ok=True)

    # 1. Clean skill
    clean_skill = skills_root / "clean-tool"
    clean_skill.mkdir()
    (clean_skill / "SKILL.md").write_text("# Clean Tool\nSafe utility", encoding="utf-8")
    (clean_skill / "package.json").write_text(
        '{"dependencies": {"safe-math": "1.0.0"}}', encoding="utf-8"
    )

    # 2. Compromised skill (using notorious ua-parser-js miner injection)
    evil_skill = skills_root / "compromised-tool"
    evil_skill.mkdir()
    (evil_skill / "SKILL.md").write_text("# Compromised Tool", encoding="utf-8")
    (evil_skill / "package.json").write_text(
        '{"dependencies": {"ua-parser-js": "0.7.29"}}', encoding="utf-8"
    )

    user_id = "test_user_integration"
    await bind_skills_service.user_config.enable_local_skill(user_id, "clean-tool")
    await bind_skills_service.user_config.enable_local_skill(user_id, "compromised-tool")

    user_cfg = await bind_skills_service.user_config.get_config(user_id)
    assert "clean-tool" in user_cfg.enabled_local_skill_ids
    assert "compromised-tool" in user_cfg.enabled_local_skill_ids

    # Setup isolated service and registry
    acks_file = tmp_path / "acks.json"
    vuln_cache = VulnScanCache()
    registry = AdvisoryAckRegistry()
    engine = InstalledSkillRescanEngine(ack_registry=registry, vuln_cache=vuln_cache)
    custom_rescan_service = SkillRescanService(engine=engine, acks_file=acks_file)

    event_bus = get_event_bus()
    captured_events = []

    async def _capture_listener(event):
        captured_events.append(event)

    event_bus.subscribe(AppEventType.SKILL_POOL_UPDATED, _capture_listener)

    with (
        patch("app.api.skills.rescan.require_local_skills_capability"),
        patch("app.api.skills.rescan.rescan_service", custom_rescan_service),
        patch("app.core.skills.discovery.rescan_service.LOCAL_INSTALL_DIR", skills_root),
        patch("myrm_agent_harness.backends.skills.scanning.rescan_engine.query_osv_batch", AsyncMock(return_value=[])),
    ):
        # 3. Post /rescan
        response = rescan_client.post(
            "/api/v1/skills/rescan",
            params={"user_id": user_id},
            json={"enable_online_osv": False, "auto_quarantine": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_scanned"] == 2
        assert data["clean_count"] == 1
        assert data["quarantined_count"] == 1

        item_map = {it["skill_name"]: it for it in data["items"]}
        assert item_map["clean-tool"]["is_clean"] is True
        assert item_map["clean-tool"]["quarantined"] is False

        assert item_map["compromised-tool"]["is_clean"] is False
        assert item_map["compromised-tool"]["has_critical_or_malware"] is True
        assert item_map["compromised-tool"]["quarantined"] is True
        assert item_map["compromised-tool"]["unacked_advisories_count"] == 1

        # 4. Verify user_config state
        updated_cfg = await bind_skills_service.user_config.get_config(user_id)
        assert "clean-tool" in updated_cfg.enabled_local_skill_ids
        assert "compromised-tool" not in updated_cfg.enabled_local_skill_ids

        # 5. Verify event bus broadcast
        assert len(captured_events) >= 1
        assert captured_events[0].data.get("action") == "quarantine"

        # 6. Verify get last report API
        rep_resp = rescan_client.get("/api/v1/skills/rescan/report")
        assert rep_resp.status_code == 200
        assert rep_resp.json()["total_scanned"] == 2


@pytest.mark.asyncio
async def test_supply_chain_advisory_ack_and_reinstatement_integration(
    tmp_path: Path,
    rescan_client: TestClient,
    bind_skills_service: SkillsService,
) -> None:
    """Ack governance flow:

    1. Skill with compromised package initially quarantined.
    2. User acknowledges the advisory with reason via API.
    3. Re-scan: the advisory is acked, skill is no longer marked CRITICAL/quarantined.
    4. User un-acknowledges: advisory is reinstated, skill is quarantined on next scan.
    """
    skills_root = tmp_path / "installed_skills"
    skills_root.mkdir(parents=True, exist_ok=True)

    test_skill = skills_root / "legacy-tool"
    test_skill.mkdir()
    (test_skill / "SKILL.md").write_text("# Legacy Tool", encoding="utf-8")
    (test_skill / "requirements.txt").write_text("ctx==0.1.2\n", encoding="utf-8")

    user_id = "test_user_ack"
    acks_file = tmp_path / "acks.json"
    vuln_cache = VulnScanCache()
    registry = AdvisoryAckRegistry()
    engine = InstalledSkillRescanEngine(ack_registry=registry, vuln_cache=vuln_cache)
    custom_rescan_service = SkillRescanService(engine=engine, acks_file=acks_file)

    with (
        patch("app.api.skills.rescan.require_local_skills_capability"),
        patch("app.api.skills.rescan.rescan_service", custom_rescan_service),
        patch("app.core.skills.discovery.rescan_service.LOCAL_INSTALL_DIR", skills_root),
        patch("myrm_agent_harness.backends.skills.scanning.rescan_engine.query_osv_batch", AsyncMock(return_value=[])),
    ):
        # Initial scan: rejected & quarantined
        resp1 = rescan_client.post(
            "/api/v1/skills/rescan",
            params={"user_id": user_id},
            json={"enable_online_osv": False, "auto_quarantine": True},
        )
        assert resp1.status_code == 200
        assert resp1.json()["items"][0]["recommendation"] == "reject"
        assert resp1.json()["items"][0]["unacked_advisories_count"] == 1

        # User acks MAL-2022-004
        ack_resp = rescan_client.post(
            "/api/v1/skills/advisories/ack",
            json={
                "advisory_id": "MAL-2022-004",
                "package_name": "ctx",
                "reason": "Sandbox strictly network-isolated",
                "acked_by": "sec-team",
            },
        )
        assert ack_resp.status_code == 200
        assert ack_resp.json()["advisory_id"] == "MAL-2022-004"

        # List acks
        list_resp = rescan_client.get("/api/v1/skills/advisories/acks")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        # Rescan: now acked, not rejected
        resp2 = rescan_client.post(
            "/api/v1/skills/rescan",
            params={"user_id": user_id},
            json={"enable_online_osv": False, "auto_quarantine": True},
        )
        assert resp2.status_code == 200
        item2 = resp2.json()["items"][0]
        assert item2["unacked_advisories_count"] == 0
        assert item2["acked_advisories_count"] == 1
        assert item2["has_critical_or_malware"] is False
        assert item2["quarantined"] is False

        # Un-ack advisory
        unack_resp = rescan_client.post(
            "/api/v1/skills/advisories/unack",
            json={"advisory_id": "MAL-2022-004", "package_name": "ctx"},
        )
        assert unack_resp.status_code == 200
        assert unack_resp.json()["success"] is True

        # Rescan again: quarantined once more
        resp3 = rescan_client.post(
            "/api/v1/skills/rescan",
            params={"user_id": user_id},
            json={"enable_online_osv": False, "auto_quarantine": True},
        )
        assert resp3.status_code == 200
        assert resp3.json()["items"][0]["unacked_advisories_count"] == 1
        assert resp3.json()["items"][0]["quarantined"] is True
