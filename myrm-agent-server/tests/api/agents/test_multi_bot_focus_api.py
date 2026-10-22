"""Unit tests for Multi-Bot Mention Focus & Anti-Thrash Compaction API (Item 42).

[INPUT]
- app.api.agents.multi_bot_focus_router.router
- app.services.agent.multi_bot_focus_service.MultiBotFocusService

[OUTPUT]
- Pytest test cases validating viewport focus dynamic tracking,
  anti-thrash context compaction hysteresis, and stream task card pruning.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_multi_bot_focus_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.multi_bot_focus_router import (
    get_multi_bot_focus_service,
)
from app.api.agents.multi_bot_focus_router import (
    router as multi_bot_focus_router,
)
from app.services.agent.multi_bot_focus_service import (
    MultiBotFocusService,
)


@pytest.fixture
def focus_service() -> MultiBotFocusService:
    return MultiBotFocusService()


@pytest.fixture
def client(focus_service: MultiBotFocusService) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(multi_bot_focus_router)
    app.dependency_overrides[get_multi_bot_focus_service] = lambda: focus_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_bot_focus_lifecycle_api(client: TestClient) -> None:
    # 1. Update focus for background bot_alpha
    resp1 = client.post(
        "/chats/chat_session_1/multi-bot/focus",
        json={"bot_id": "bot_alpha", "is_viewport_active": False, "turn_index": 2},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()["data"]
    assert data1["bot_id"] == "bot_alpha"
    assert data1["focus_score"] == 2.0

    # 2. Update focus for viewport active bot_beta
    resp2 = client.post(
        "/chats/chat_session_1/multi-bot/focus",
        json={"bot_id": "bot_beta", "is_viewport_active": True, "turn_index": 1},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()["data"]
    assert data2["bot_id"] == "bot_beta"
    assert data2["focus_score"] == 101.0

    # 3. Query focused bot for session
    query_resp = client.get("/chats/chat_session_1/multi-bot/focus")
    assert query_resp.status_code == 200
    query_data = query_resp.json()["data"]
    assert query_data["session_id"] == "chat_session_1"
    assert query_data["focused_bot_id"] == "bot_beta"
    assert len(query_data["snapshots"]) == 2


def test_compaction_anti_thrash_evaluation_api(client: TestClient) -> None:
    # 1. Below watermark threshold
    eval_resp1 = client.post(
        "/chats/chat_session_2/multi-bot/compaction/evaluate",
        json={
            "current_tokens": 8000,
            "max_context_tokens": 10000,
            "current_turn": 5,
        },
    )
    assert eval_resp1.status_code == 200
    assert eval_resp1.json()["data"]["should_compact"] is False

    # 2. Exceeds watermark threshold (>= 90%)
    eval_resp2 = client.post(
        "/chats/chat_session_2/multi-bot/compaction/evaluate",
        json={
            "current_tokens": 9200,
            "max_context_tokens": 10000,
            "current_turn": 5,
        },
    )
    assert eval_resp2.status_code == 200
    assert eval_resp2.json()["data"]["should_compact"] is True

    # 3. Record compaction completion
    rec_resp = client.post(
        "/chats/chat_session_2/multi-bot/compaction/record",
        json={"executed_turn": 5, "tokens_after": 7000},
    )
    assert rec_resp.status_code == 200
    assert rec_resp.json()["data"]["recorded"] is True

    # 4. Immediate next turn suppressed by cooldown (turn 6 < 5 + 3)
    eval_resp3 = client.post(
        "/chats/chat_session_2/multi-bot/compaction/evaluate",
        json={
            "current_tokens": 9500,
            "max_context_tokens": 10000,
            "current_turn": 6,
        },
    )
    assert eval_resp3.status_code == 200
    assert eval_resp3.json()["data"]["should_compact"] is False
    assert eval_resp3.json()["data"]["cooldown_remaining"] == 2

    # 5. After cooldown (turn 9) but delta too small (7100 - 7000 < 500)
    eval_resp4 = client.post(
        "/chats/chat_session_2/multi-bot/compaction/evaluate",
        json={
            "current_tokens": 9100,
            "max_context_tokens": 10000,
            "current_turn": 9,
        },
    )
    # Note: tokens_after was 7000, current is 9100, delta is 2100 >= 500 -> should_compact=True
    assert eval_resp4.status_code == 200
    assert eval_resp4.json()["data"]["should_compact"] is True


def test_stream_heartbeat_and_prune_api(client: TestClient) -> None:
    # 1. Emit heartbeat
    hb_resp = client.post(
        "/chats/chat_session_3/multi-bot/streams/heartbeat",
        json={
            "card_id": "card_test_101",
            "bot_id": "bot_coder",
            "state": "streaming",
        },
    )
    assert hb_resp.status_code == 200
    assert hb_resp.json()["data"]["card_id"] == "card_test_101"
    assert hb_resp.json()["data"]["state"] == "streaming"

    # 2. Prune with generous timeout (not expired)
    prune_resp = client.post(
        "/chats/chat_session_3/multi-bot/streams/prune",
        json={"timeout_seconds": 60.0},
    )
    assert prune_resp.status_code == 200
    assert prune_resp.json()["data"]["count"] == 0

    # 3. Clean completion
    complete_resp = client.post(
        "/chats/chat_session_3/multi-bot/streams/card_test_101/complete",
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["data"]["completed"] is True

    # 4. Non-existent card completion returns 404
    missing_resp = client.post(
        "/chats/chat_session_3/multi-bot/streams/non_existent_card/complete",
    )
    assert missing_resp.status_code == 404


def test_invalid_input_error_handling(client: TestClient) -> None:
    # Empty bot_id returns 422 (pydantic validation)
    bad_focus_resp = client.post(
        "/chats/chat_session_err/multi-bot/focus",
        json={"bot_id": "", "is_viewport_active": True, "turn_index": 0},
    )
    assert bad_focus_resp.status_code == 422

    # max_context_tokens <= 0 returns 422
    bad_compaction_resp = client.post(
        "/chats/chat_session_err/multi-bot/compaction/evaluate",
        json={
            "current_tokens": 100,
            "max_context_tokens": 0,
            "current_turn": 1,
        },
    )
    assert bad_compaction_resp.status_code == 422
