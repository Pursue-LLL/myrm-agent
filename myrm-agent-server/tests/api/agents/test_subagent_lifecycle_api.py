"""Unit tests for Native Subagent Lifecycle Toolchain API (Item 46).

[INPUT]
- app.api.agents.subagent_lifecycle_router.router
- app.services.agent.subagent_lifecycle_service.SubagentLifecycleService

[OUTPUT]
- Pytest test cases validating subagent spawn, list, get, send_input, kill, wait,
  and error handling (404 / 400).

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_subagent_lifecycle_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.subagent_lifecycle_router import (
    get_subagent_lifecycle_service,
)
from app.api.agents.subagent_lifecycle_router import (
    router as subagent_lifecycle_router,
)
from app.services.agent.subagent_lifecycle_service import (
    SubagentLifecycleService,
)


@pytest.fixture
def lifecycle_service() -> SubagentLifecycleService:
    return SubagentLifecycleService()


@pytest.fixture
def client(
    lifecycle_service: SubagentLifecycleService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(subagent_lifecycle_router)
    app.dependency_overrides[get_subagent_lifecycle_service] = lambda: lifecycle_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_spawn_and_get_subagent_api(client: TestClient) -> None:
    chat_id = "test_chat_lc_1"

    # 1. Spawn subagent
    spawn_resp = client.post(
        f"/chats/{chat_id}/subagents/spawn",
        json={
            "task_prompt": "Perform security review on auth module",
            "agent_profile": "security_auditor",
            "tools_whitelist": ["read_file"],
            "timeout_seconds": 60.0,
        },
    )
    assert spawn_resp.status_code == 200
    data = spawn_resp.json()["data"]
    subagent_id = data["subagent_id"]
    assert subagent_id.startswith("subagent-")
    assert data["parent_session_id"] == chat_id
    assert data["status"] == "running"
    assert data["agent_profile"] == "security_auditor"

    # 2. Get subagent details
    get_resp = client.get(f"/chats/{chat_id}/subagents/{subagent_id}")
    assert get_resp.status_code == 200
    detail = get_resp.json()["data"]
    assert detail["subagent_id"] == subagent_id
    assert detail["status"] == "running"


def test_spawn_validation_error_api(client: TestClient) -> None:
    chat_id = "test_chat_lc_2"
    resp = client.post(
        f"/chats/{chat_id}/subagents/spawn",
        json={
            "task_prompt": "",
            "agent_profile": "general_worker",
        },
    )
    assert resp.status_code == 422  # Pydantic min_length=1 validation error


def test_send_input_and_kill_api(client: TestClient) -> None:
    chat_id = "test_chat_lc_3"

    # 1. Spawn subagent
    spawn_resp = client.post(
        f"/chats/{chat_id}/subagents/spawn",
        json={
            "task_prompt": "Scrape website products",
            "agent_profile": "scraper",
        },
    )
    subagent_id = spawn_resp.json()["data"]["subagent_id"]

    # 2. Send input guidance
    input_resp = client.post(
        f"/chats/{chat_id}/subagents/{subagent_id}/input",
        json={
            "content": "Only target category A products",
            "sender_role": "orchestrator",
        },
    )
    assert input_resp.status_code == 200
    input_data = input_resp.json()["data"]
    assert input_data["content"] == "Only target category A products"
    assert input_data["sender_role"] == "orchestrator"

    # 3. Kill subagent
    kill_resp = client.post(
        f"/chats/{chat_id}/subagents/{subagent_id}/kill",
        json={"reason": "Resource budget exceeded"},
    )
    assert kill_resp.status_code == 200
    kill_data = kill_resp.json()["data"]
    assert kill_data["status"] == "killed"
    assert kill_data["kill_reason"] == "Resource budget exceeded"


def test_wait_and_list_api(client: TestClient) -> None:
    chat_id = "test_chat_lc_4"

    # 1. Spawn two subagents
    s1 = client.post(
        f"/chats/{chat_id}/subagents/spawn",
        json={"task_prompt": "Subtask 1"},
    ).json()["data"]["subagent_id"]
    s2 = client.post(
        f"/chats/{chat_id}/subagents/spawn",
        json={"task_prompt": "Subtask 2"},
    ).json()["data"]["subagent_id"]

    # 2. List subagents
    list_resp = client.get(f"/chats/{chat_id}/subagents")
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] == 2

    # 3. Simulate completion for both
    client.post(
        f"/chats/{chat_id}/subagents/{s1}/simulate-complete",
        params={"summary_text": "Subtask 1 finished"},
    )
    client.post(
        f"/chats/{chat_id}/subagents/{s2}/simulate-complete",
        params={"summary_text": "Subtask 2 finished"},
    )

    # 4. Wait for them
    wait_resp = client.post(
        f"/chats/{chat_id}/subagents/wait",
        json={
            "subagent_ids": [s1, s2],
            "timeout_seconds": 2.0,
        },
    )
    assert wait_resp.status_code == 200
    wait_data = wait_resp.json()["data"]
    assert wait_data["all_completed"] is True
    assert wait_data["completed_count"] == 2


def test_subagent_not_found_api(client: TestClient) -> None:
    chat_id = "test_chat_lc_5"
    resp = client.get(f"/chats/{chat_id}/subagents/non_existent_subagent")
    assert resp.status_code == 404
