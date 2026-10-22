"""Unit tests for Bot Mode Named Profile Roster & Inter-Bot Mailbox API endpoints.

[INPUT]
- app.api.agents.bot_mode_router.router
- app.services.agent.bot_mode_service.BotModeService

[OUTPUT]
- Pytest cases verifying workstation profile registration, dual indexing lookup,
  peer-to-peer message delivery, @mention dispatch resolution, and mailbox lifecycle.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_bot_mode_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.bot_mode_router import (
    get_bot_mode_service,
)
from app.api.agents.bot_mode_router import (
    router as bot_mode_router,
)
from app.services.agent.bot_mode_service import BotModeService


@pytest.fixture
def bot_service() -> BotModeService:
    return BotModeService()


@pytest.fixture
def bot_client(
    bot_service: BotModeService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(bot_mode_router)
    app.dependency_overrides[get_bot_mode_service] = lambda: bot_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_register_bot_and_list_roster(bot_client: TestClient) -> None:
    chat_id = "chat_bot_mode_01"

    # Register bot 1
    resp1 = bot_client.post(
        f"/chats/{chat_id}/bot-mode/register",
        json={
            "bot_id": "bot_reviewer",
            "handle": "code_reviewer",  # Should normalize to @code_reviewer
            "display_name": "Senior Reviewer",
            "role_description": "Performs multi-perspective architecture and security review",
            "avatar_seed": "seed_rev_01",
            "model_tier": "reasoning",
            "skills": ["code-analysis", "security-audit"],
            "tools": ["read_file", "search_code"],
            "status": "idle",
        },
    )
    assert resp1.status_code == 200
    data1 = resp1.json()["data"]
    assert data1["bot_id"] == "bot_reviewer"
    assert data1["handle"] == "@code_reviewer"
    assert data1["display_name"] == "Senior Reviewer"
    assert data1["status"] == "idle"

    # Register bot 2
    resp2 = bot_client.post(
        f"/chats/{chat_id}/bot-mode/register",
        json={
            "bot_id": "bot_tester",
            "handle": "@qa_tester",
            "display_name": "QA Specialist",
            "role_description": "Executes automated test suites and regression checks",
            "avatar_seed": "seed_qa_02",
            "model_tier": "fast",
            "skills": ["pytest-runner"],
            "tools": ["run_test"],
            "status": "idle",
        },
    )
    assert resp2.status_code == 200

    # List all bots
    roster_resp = bot_client.get(f"/chats/{chat_id}/bot-mode/roster")
    assert roster_resp.status_code == 200
    roster_data = roster_resp.json()["data"]
    assert roster_data["total_count"] == 2
    handles = {b["handle"] for b in roster_data["bots"]}
    assert "@code_reviewer" in handles
    assert "@qa_tester" in handles

    # Lookup by handle without leading @
    lookup_resp = bot_client.get(f"/chats/{chat_id}/bot-mode/bots/code_reviewer")
    assert lookup_resp.status_code == 200
    assert lookup_resp.json()["data"]["bot_id"] == "bot_reviewer"

    # Lookup by bot_id
    lookup_resp2 = bot_client.get(f"/chats/{chat_id}/bot-mode/bots/bot_tester")
    assert lookup_resp2.status_code == 200
    assert lookup_resp2.json()["data"]["handle"] == "@qa_tester"


def test_update_bot_status(bot_client: TestClient) -> None:
    chat_id = "chat_bot_mode_02"

    bot_client.post(
        f"/chats/{chat_id}/bot-mode/register",
        json={
            "bot_id": "bot_worker_1",
            "handle": "@worker_1",
            "display_name": "Worker One",
            "role_description": "Backend engineer",
            "avatar_seed": "seed_w1",
        },
    )

    update_resp = bot_client.patch(
        f"/chats/{chat_id}/bot-mode/bots/bot_worker_1/status",
        json={"status": "busy", "active_task_id": "task_999"},
    )
    assert update_resp.status_code == 200
    data = update_resp.json()["data"]
    assert data["status"] == "busy"
    assert data["active_task_id"] == "task_999"

    # Verify filter by status
    busy_list = bot_client.get(
        f"/chats/{chat_id}/bot-mode/roster",
        params={"status_filter": "busy"},
    )
    assert busy_list.status_code == 200
    assert busy_list.json()["data"]["total_count"] == 1

    idle_list = bot_client.get(
        f"/chats/{chat_id}/bot-mode/roster",
        params={"status_filter": "idle"},
    )
    assert idle_list.status_code == 200
    assert idle_list.json()["data"]["total_count"] == 0


def test_send_direct_message_and_inbox(bot_client: TestClient) -> None:
    chat_id = "chat_bot_mode_03"

    # Register sender & recipient
    bot_client.post(
        f"/chats/{chat_id}/bot-mode/register",
        json={
            "bot_id": "bot_sender",
            "handle": "@lead",
            "display_name": "Team Lead",
            "role_description": "Orchestrates squad",
            "avatar_seed": "seed_lead",
        },
    )
    bot_client.post(
        f"/chats/{chat_id}/bot-mode/register",
        json={
            "bot_id": "bot_recipient",
            "handle": "@developer",
            "display_name": "Dev",
            "role_description": "Implements features",
            "avatar_seed": "seed_dev",
        },
    )

    # Deliver direct message
    msg_resp = bot_client.post(
        f"/chats/{chat_id}/bot-mode/messages/send",
        json={
            "from_bot": "@lead",
            "to_bot": "@developer",
            "subject": "Refactor router task",
            "body": "Please refactor the subagent router to adhere to 400 lines limit.",
            "priority": "urgent",
            "task_payload": {"ticket_id": 42, "is_critical": True},
        },
    )
    assert msg_resp.status_code == 200
    msg_data = msg_resp.json()["data"]
    assert msg_data["from_bot"] == "@lead"
    assert msg_data["to_bot"] == "@developer"
    assert msg_data["priority"] == "urgent"
    assert msg_data["is_read"] is False
    msg_id = msg_data["message_id"]

    # Check recipient inbox
    inbox_resp = bot_client.get(f"/chats/{chat_id}/bot-mode/bots/@developer/inbox")
    assert inbox_resp.status_code == 200
    inbox_data = inbox_resp.json()["data"]
    assert inbox_data["unread_count"] == 1
    assert inbox_data["total_count"] == 1
    assert len(inbox_data["messages"]) == 1
    assert inbox_data["messages"][0]["message_id"] == msg_id

    # Mark as read
    mark_resp = bot_client.post(
        f"/chats/{chat_id}/bot-mode/bots/@developer/inbox/mark-read",
        json={"message_ids": [msg_id]},
    )
    assert mark_resp.status_code == 200
    assert mark_resp.json()["data"]["updated_count"] == 1

    # Verify unread count is now 0
    inbox_unread = bot_client.get(
        f"/chats/{chat_id}/bot-mode/bots/@developer/inbox",
        params={"unread_only": True},
    )
    assert inbox_unread.status_code == 200
    assert len(inbox_unread.json()["data"]["messages"]) == 0
    assert inbox_unread.json()["data"]["unread_count"] == 0


def test_dispatch_mentions_flow(bot_client: TestClient) -> None:
    chat_id = "chat_bot_mode_04"

    bot_client.post(
        f"/chats/{chat_id}/bot-mode/register",
        json={
            "bot_id": "bot_arch",
            "handle": "@architect",
            "display_name": "Architect",
            "role_description": "System design",
            "avatar_seed": "seed_arch",
        },
    )
    bot_client.post(
        f"/chats/{chat_id}/bot-mode/register",
        json={
            "bot_id": "bot_sec",
            "handle": "@sec_ops",
            "display_name": "Security Ops",
            "role_description": "Vulnerability scanning",
            "avatar_seed": "seed_sec",
        },
    )

    # Dispatch text containing mentions
    dispatch_resp = bot_client.post(
        f"/chats/{chat_id}/bot-mode/messages/dispatch-mentions",
        json={
            "text": "Hello @architect and @sec_ops, please review Item 33. Ping @ghost_agent too.",
            "from_bot": "orchestrator",
        },
    )
    assert dispatch_resp.status_code == 200
    results = dispatch_resp.json()["data"]
    assert len(results) == 3

    dispatched_handles = {r["target_handle"] for r in results if r["dispatched"]}
    assert "@architect" in dispatched_handles
    assert "@sec_ops" in dispatched_handles

    failed_mentions = [r for r in results if not r["dispatched"]]
    assert len(failed_mentions) == 1
    assert failed_mentions[0]["target_handle"] == "@ghost_agent"


def test_error_and_clear_inbox(bot_client: TestClient) -> None:
    chat_id = "chat_bot_mode_05"

    # Non-existent bot lookup
    resp404 = bot_client.get(f"/chats/{chat_id}/bot-mode/bots/nonexistent_bot")
    assert resp404.status_code == 404

    # Register bot and clear inbox
    bot_client.post(
        f"/chats/{chat_id}/bot-mode/register",
        json={
            "bot_id": "bot_clean",
            "handle": "@cleaner",
            "display_name": "Cleaner",
            "role_description": "Cleanups",
            "avatar_seed": "seed_c",
        },
    )

    del_resp = bot_client.delete(f"/chats/{chat_id}/bot-mode/bots/@cleaner/inbox")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["cleared"] is True
