"""Unit tests for Skill Bundles Batch Manifest & Lifecycle Warmup API (Item 41).

[INPUT]
- app.api.agents.skill_bundle_router.router
- app.services.agent.skill_bundle_service.SkillBundleService

[OUTPUT]
- Pytest test cases verifying bundle discovery, custom manifest registration,
  pre-flight diagnostic warmup checks, and session activation lifecycle.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_skill_bundle_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.skill_bundle_router import (
    get_skill_bundle_service,
)
from app.api.agents.skill_bundle_router import (
    router as skill_bundle_router,
)
from app.services.agent.skill_bundle_service import (
    SkillBundleService,
)


@pytest.fixture
def bundle_service() -> SkillBundleService:
    return SkillBundleService()


@pytest.fixture
def client(bundle_service: SkillBundleService) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(skill_bundle_router)
    app.dependency_overrides[get_skill_bundle_service] = lambda: bundle_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_and_get_default_bundles_api(client: TestClient) -> None:
    resp = client.get("/skills/bundles")
    assert resp.status_code == 200
    bundles = resp.json()["data"]
    assert len(bundles) >= 3

    # Check coding bundle
    bundle_ids = [b["bundle_id"] for b in bundles]
    assert "bundle_fullstack_coding" in bundle_ids

    # Query specific bundle
    detail_resp = client.get("/skills/bundles/bundle_fullstack_coding")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["bundle_id"] == "bundle_fullstack_coding"
    assert detail["category"] == "coding"
    assert len(detail["skills"]) == 3


def test_register_custom_bundle_api(client: TestClient) -> None:
    manifest_payload = {
        "manifest": {
            "bundle_id": "bundle_marketing_ad_blast",
            "name": "Global Ad Campaign Suite",
            "description": "Multi-channel advertising copy generator and compliance filter.",
            "category": "marketing",
            "skills": [
                {
                    "skill_id": "ad-copywriter",
                    "name": "Ad Copywriter",
                    "description": "Writes high-CTR headlines and ad body text.",
                    "required_env_vars": ["OPENAI_API_KEY"],
                    "required_tools": [],
                    "is_optional": False,
                }
            ],
            "author": "growth-team",
            "version": "1.1.0",
            "tags": ["marketing", "ads", "growth"],
        }
    }
    resp = client.post("/skills/bundles", json=manifest_payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["bundle_id"] == "bundle_marketing_ad_blast"

    # Verify retrieval
    get_resp = client.get("/skills/bundles/bundle_marketing_ad_blast")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["name"] == "Global Ad Campaign Suite"


def test_warmup_bundle_api(client: TestClient) -> None:
    # 1. Warmup with complete dependencies
    warmup_payload = {
        "available_skills": ["code-refactor", "test-runner", "security-linter"],
        "env_vars": {},
        "available_tools": [],
    }
    resp = client.post(
        "/skills/bundles/bundle_fullstack_coding/warmup", json=warmup_payload
    )
    assert resp.status_code == 200
    report = resp.json()["data"]
    assert report["bundle_id"] == "bundle_fullstack_coding"
    assert report["overall_status"] == "ready"
    assert len(report["checks"]) >= 3

    # 2. Warmup missing required skill -> blocked
    blocked_payload = {
        "available_skills": ["security-linter"],  # missing code-refactor & test-runner
        "env_vars": {},
    }
    blocked_resp = client.post(
        "/skills/bundles/bundle_fullstack_coding/warmup", json=blocked_payload
    )
    assert blocked_resp.status_code == 200
    assert blocked_resp.json()["data"]["overall_status"] == "blocked"


def test_activate_and_deactivate_bundle_api(client: TestClient) -> None:
    chat_id = "chat_sess_finance_01"

    activate_payload = {
        "bundle_id": "bundle_finance_audit",
        "available_skills": ["excel-cleaner", "invoice-matcher"],
        "env_vars": {},
        "force": False,
    }
    resp = client.post(
        f"/chats/{chat_id}/skill-bundles/activate", json=activate_payload
    )
    assert resp.status_code == 200
    record = resp.json()["data"]
    assert record["session_id"] == chat_id
    assert record["bundle_id"] == "bundle_finance_audit"
    assert record["warmup_status"] == "ready"
    assert len(record["activated_skills"]) == 2

    # Query active bundles for chat
    active_resp = client.get(f"/chats/{chat_id}/skill-bundles/active")
    assert active_resp.status_code == 200
    active_list = active_resp.json()["data"]
    assert len(active_list) == 1
    assert active_list[0]["bundle_id"] == "bundle_finance_audit"

    # Deactivate bundle
    deact_resp = client.post(
        f"/chats/{chat_id}/skill-bundles/deactivate",
        json={"bundle_id": "bundle_finance_audit"},
    )
    assert deact_resp.status_code == 200
    assert deact_resp.json()["data"]["deactivated"] is True

    # Confirm no active bundles
    empty_resp = client.get(f"/chats/{chat_id}/skill-bundles/active")
    assert empty_resp.json()["data"] == []


def test_activate_bundle_conflict_when_blocked_api(client: TestClient) -> None:
    chat_id = "chat_sess_blocked_02"

    # Attempt to activate WeChat bundle without required secret
    activate_payload = {
        "bundle_id": "bundle_wechat_publisher",
        "available_skills": [
            "content-topic-generator",
            "wechat-publisher",
            "title-ab-tester",
        ],
        "env_vars": {},  # Missing WECHAT_APP_SECRET
        "force": False,
    }
    resp = client.post(
        f"/chats/{chat_id}/skill-bundles/activate", json=activate_payload
    )
    assert resp.status_code == 409
    assert "warmup blocked" in resp.json()["detail"]

    # Force activation succeeds
    activate_payload["force"] = True
    force_resp = client.post(
        f"/chats/{chat_id}/skill-bundles/activate", json=activate_payload
    )
    assert force_resp.status_code == 200
    assert force_resp.json()["data"]["warmup_status"] == "blocked"
