"""Unit tests for Creator Mode Guardrailed Preset Synthesizer and Defensive Sandbox API (Item 39).

[INPUT]
- app.api.agents.creator_mode_router.router
- app.services.agent.creator_mode_service.CreatorModeService

[OUTPUT]
- Pytest test cases verifying natural language preset synthesis, defensive sandbox certification,
  and multi-platform roaming synchronization.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_creator_mode_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.creator_mode_router import (
    get_creator_mode_service,
)
from app.api.agents.creator_mode_router import (
    router as creator_mode_router,
)
from app.schemas.creator_mode import (
    AgentPresetDraftDTO,
    RoamingPlatformEnum,
)
from app.services.agent.creator_mode_service import (
    CreatorModeService,
)


@pytest.fixture
def creator_service() -> CreatorModeService:
    return CreatorModeService()


@pytest.fixture
def creator_client(
    creator_service: CreatorModeService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(creator_mode_router)
    app.dependency_overrides[get_creator_mode_service] = lambda: creator_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_synthesize_preset_api(creator_client: TestClient) -> None:
    resp = creator_client.post(
        "/agents/creator-mode/synthesize",
        json={
            "intent": "帮我做一个专用的代码审计机器人，只许读文件和搜索，坚决不许修改任何文件",
            "name": "AuditBot",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "AuditBot"
    assert data["role"] == "code_auditor"
    assert "file_read" in data["allowed_tools"]
    assert "web_search" in data["allowed_tools"]
    assert "file_write" in data["denied_tools"]
    assert data["guardrails"]["read_only"] is True


def test_synthesize_preset_empty_intent_error(creator_client: TestClient) -> None:
    resp = creator_client.post(
        "/agents/creator-mode/synthesize",
        json={"intent": "   "},
    )
    assert resp.status_code == 422


def test_verify_in_sandbox_api(creator_client: TestClient) -> None:
    # 1. Synthesize draft
    synth_resp = creator_client.post(
        "/agents/creator-mode/synthesize",
        json={"intent": "Read-only security reviewer, only file read and search, no bash"},
    )
    draft_data = synth_resp.json()["data"]

    # 2. Verify in sandbox
    verify_resp = creator_client.post(
        "/agents/creator-mode/verify-sandbox",
        json={"draft": draft_data},
    )
    assert verify_resp.status_code == 200
    report = verify_resp.json()["data"]
    assert report["is_safe"] is True
    assert report["total_cases"] > 0
    assert report["passed_cases"] == report["total_cases"]
    assert report["blocked_exploits"] > 0


def test_roaming_sync_and_list_records_api(creator_client: TestClient) -> None:
    draft = AgentPresetDraftDTO(
        preset_id="preset_roam_01",
        name="RoamingTestBot",
        role="code_auditor",
        description="Testing roaming sync across devices",
        system_prompt="You are a test bot",
        allowed_tools=["file_read"],
        denied_tools=["file_write", "root_shell"],
        guardrails={"read_only": True},
    )

    sync_resp = creator_client.post(
        "/agents/creator-mode/roaming-sync",
        json={
            "draft": draft.model_dump(mode="json"),
            "target_platforms": ["webui", "desktop_tauri", "cloud"],
            "legacy_broken_path": "~/.dsh/legacy_broken/preset.json",
        },
    )
    assert sync_resp.status_code == 200
    sync_data = sync_resp.json()["data"]
    assert len(sync_data["records"]) == 3
    assert any(r["platform"] == RoamingPlatformEnum.DESKTOP_TAURI.value for r in sync_data["records"])
    assert all(r["healed"] is True for r in sync_data["records"])

    # List all records
    list_resp = creator_client.get("/agents/creator-mode/records")
    assert list_resp.status_code == 200
    all_records = list_resp.json()["data"]
    assert len(all_records) >= 3
