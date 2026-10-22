"""API integration tests for Chat-Driven Agent & Team Factory with Builder Safety Envelope (Item 74).

[INPUT]
- app.api.agents.bot_forge_router.router
- app.services.agent.bot_forge_service.BotForgeService

[OUTPUT]
- Pytest assertions verifying deterministic agent/team creation pipelines, zero-model readiness dry-run,
  safety boundary enforcement (anti-recursion, permission attenuation), duplicate/duty overlap detection,
  atomic transactional rollback, agent cloning, and catalog operations.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_bot_forge_api.py
"""

from __future__ import annotations

from typing import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.bot_forge_router import router as bot_forge_router
from app.services.agent.bot_forge_service import BotForgeService


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with isolated BotForgeService instance."""
    BotForgeService.reset_instance()
    app = FastAPI()
    app.include_router(bot_forge_router)

    with TestClient(app) as test_client:
        yield test_client

    BotForgeService.reset_instance()


def test_check_overlap_api(client: TestClient) -> None:
    """Test name uniqueness and semantic keyword duty overlap detection."""
    session_id = "test-session-overlap"

    # Step 1: Create an initial agent
    create_payload = {
        "spec": {
            "name": "security-auditor",
            "display_name": "Security Auditor",
            "description": "Performs vulnerability audits, smart contract analysis, and token governance",
            "system_prompt": "Audit code thoroughly",
            "model": "gpt-5",
            "tools": ["file_read"],
        },
        "is_sandbox": False,
        "allow_overlap": False,
    }
    resp = client.post(f"/agents/bot-forge/sessions/{session_id}/create-agent", json=create_payload)
    assert resp.status_code == 201

    # Step 2: Check duplicate name
    overlap_resp = client.post(
        f"/agents/bot-forge/sessions/{session_id}/check-overlap",
        json={
            "candidate_name": "security-auditor",
            "candidate_purpose": "Different purpose entirely",
            "duty_similarity_threshold": 0.65,
        },
    )
    assert overlap_resp.status_code == 200
    data = overlap_resp.json()
    assert data["verdict"] == "duplicate_name"
    assert data["conflicting_name"] == "security-auditor"

    # Step 3: Check overlapping duty
    duty_resp = client.post(
        f"/agents/bot-forge/sessions/{session_id}/check-overlap",
        json={
            "candidate_name": "smart-contract-checker",
            "candidate_purpose": "Performs vulnerability audits, smart contract analysis, and token governance",
            "duty_similarity_threshold": 0.65,
        },
    )
    assert duty_resp.status_code == 200
    duty_data = duty_resp.json()
    assert duty_data["verdict"] == "overlapping_duty"
    assert duty_data["conflicting_name"] == "security-auditor"

    # Step 4: Check unique agent
    unique_resp = client.post(
        f"/agents/bot-forge/sessions/{session_id}/check-overlap",
        json={
            "candidate_name": "frontend-styler",
            "candidate_purpose": "Tailwind CSS styling and responsive layout rendering",
            "duty_similarity_threshold": 0.65,
        },
    )
    assert unique_resp.status_code == 200
    assert unique_resp.json()["verdict"] == "unique"


def test_create_single_agent_success_and_catalog_api(client: TestClient) -> None:
    """Test full verified creation pipeline for single agent and catalog retrieval."""
    session_id = "test-session-single"

    create_payload = {
        "spec": {
            "name": "daily-summarizer",
            "display_name": "Daily Summarizer",
            "description": "Compiles executive daily briefing digests from emails and news feeds",
            "system_prompt": "Produce crisp 3-bullet briefings",
            "model": "gpt-5",
            "tools": ["file_read", "web_search"],
            "cron_routines": ["0 8 * * *"],
        },
        "is_sandbox": False,
        "allow_overlap": False,
    }
    resp = client.post(f"/agents/bot-forge/sessions/{session_id}/create-agent", json=create_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["current_stage"] == "completed"
    assert "daily-summarizer" in data["created_agents"]
    assert data["verification"]["passed"] is True
    assert data["verification"]["severity"] == "pass"

    # Fetch catalog
    list_resp = client.get(f"/agents/bot-forge/sessions/{session_id}/agents")
    assert list_resp.status_code == 200
    cat_data = list_resp.json()
    assert cat_data["total_agents"] == 1
    assert cat_data["agents"][0]["name"] == "daily-summarizer"

    # Fetch single profile
    get_resp = client.get(f"/agents/bot-forge/sessions/{session_id}/agents/daily-summarizer")
    assert get_resp.status_code == 200
    assert get_resp.json()["display_name"] == "Daily Summarizer"


def test_safety_envelope_boundary_rejection_api(client: TestClient) -> None:
    """Test that safety envelope rejects recursive creation and unauthorized tools with HTTP 400."""
    session_id = "test-session-safety"

    # 1. Anti-recursion rejection: trying to grant `bot_forge` meta-tool
    bad_recursive_payload = {
        "spec": {
            "name": "meta-replicator",
            "display_name": "Meta Replicator",
            "description": "Spawns subagents recursively",
            "system_prompt": "Build more bots",
            "model": "gpt-5",
            "tools": ["file_read", "bot_forge"],
        },
    }
    resp = client.post(f"/agents/bot-forge/sessions/{session_id}/create-agent", json=bad_recursive_payload)
    assert resp.status_code == 400
    assert "Recursive creation denied" in resp.json()["detail"]

    # 2. Sandbox boundary rejection: trying to grant desktop control in sandbox
    bad_sandbox_payload = {
        "spec": {
            "name": "sandbox-escapist",
            "display_name": "Sandbox Escapist",
            "description": "Desktop controlling bot in sandbox",
            "system_prompt": "Control mouse and keyboard",
            "model": "gpt-5",
            "tools": ["file_read", "desktop_control_approval"],
        },
        "is_sandbox": True,
    }
    resp2 = client.post(f"/agents/bot-forge/sessions/{session_id}/create-agent", json=bad_sandbox_payload)
    assert resp2.status_code == 400
    assert "Sandbox violation" in resp2.json()["detail"]


def test_team_atomic_rollback_on_member_failure_api(client: TestClient) -> None:
    """Test that squad creation failure rolls back all created agents atomically."""
    session_id = "test-session-team"

    team_payload = {
        "team_spec": {
            "team_name": "research-squad",
            "team_purpose": "Conduct deep academic research and generate synthesis reports",
            "lead": {
                "name": "research-lead",
                "display_name": "Research Lead",
                "description": "Coordinates research topics and reviews literature reviews",
                "system_prompt": "Orchestrate literature review",
                "model": "gpt-5",
                "tools": ["file_read", "web_search"],
            },
            "specialists": [
                {
                    "name": "doc-analyst",
                    "display_name": "Document Analyst",
                    "description": "Parses PDF papers and generates summaries",
                    "system_prompt": "Analyze PDF citations",
                    "model": "gpt-5",
                    "tools": ["file_read"],
                },
                {
                    # This member requests an unready/unconfigured model, failing dry-run precheck
                    "name": "quantum-specialist",
                    "display_name": "Quantum Specialist",
                    "description": "Simulates quantum topological circuits",
                    "system_prompt": "Run quantum physics simulation",
                    "model": "unready-quantum-llm-ultra-v99",
                    "tools": ["file_read"],
                },
            ],
        },
    }

    resp = client.post(f"/agents/bot-forge/sessions/{session_id}/create-team", json=team_payload)
    assert resp.status_code == 201
    state = resp.json()
    assert state["current_stage"] == "rolled_back"
    assert "failed creation" in state["error"]

    # Verify atomic rollback: research-lead and doc-analyst must be removed from the store!
    catalog_resp = client.get(f"/agents/bot-forge/sessions/{session_id}/agents")
    assert catalog_resp.status_code == 200
    assert catalog_resp.json()["total_agents"] == 0


def test_clone_and_delete_agent_api(client: TestClient) -> None:
    """Test cloning an agent with prompt sanitization, then deleting."""
    session_id = "test-session-clone"

    # Step 1: Create base agent
    create_payload = {
        "spec": {
            "name": "alice-writer",
            "display_name": "Alice Writer",
            "description": "Writes technical documentation and release notes",
            "system_prompt": "You are Alice. Alice crafts release logs with extreme precision.",
            "model": "gpt-5",
            "tools": ["file_read", "file_write"],
        },
    }
    client.post(f"/agents/bot-forge/sessions/{session_id}/create-agent", json=create_payload)

    # Step 2: Clone agent
    clone_payload = {
        "source_name": "alice-writer",
        "target_name": "bob-writer",
        "new_display_name": "Bob Writer",
        "custom_instructions": "Focus on API documentation style.",
    }
    clone_resp = client.post(f"/agents/bot-forge/sessions/{session_id}/clone-agent", json=clone_payload)
    assert clone_resp.status_code == 201
    assert clone_resp.json()["current_stage"] == "completed"

    # Step 3: Verify sanitized prompt
    get_bob = client.get(f"/agents/bot-forge/sessions/{session_id}/agents/bob-writer")
    assert get_bob.status_code == 200
    bob_data = get_bob.json()
    assert "Alice" not in bob_data["system_prompt"]
    assert "bob-writer crafts release logs" in bob_data["system_prompt"]
    assert "Focus on API documentation style." in bob_data["system_prompt"]

    # Step 4: Delete agent
    del_resp = client.delete(f"/agents/bot-forge/sessions/{session_id}/agents/bob-writer")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Verify 404 after deletion
    get_bob_again = client.get(f"/agents/bot-forge/sessions/{session_id}/agents/bob-writer")
    assert get_bob_again.status_code == 404
