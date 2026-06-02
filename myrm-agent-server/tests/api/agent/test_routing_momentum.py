"""Test routing momentum integration.

Validates that the complexity router correctly applies session momentum
when short follow-up messages would otherwise be classified as SIMPLE
in conversations operating at a higher tier.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.fixture
async def chat_with_routing_history(setup_test_database):
    """Create a chat with assistant messages that have routingTier in extra_data."""
    from app.database.connection import get_session
    from app.database.models import Chat, Message

    chat_id = str(uuid.uuid4())

    async with get_session() as db:
        chat = Chat(
            id=chat_id,
            title="Test Complex Conversation",
            created_at=datetime.now(timezone.utc),
        )
        db.add(chat)

        for i in range(5):
            msg = Message(
                id=str(uuid.uuid4()),
                chat_id=chat_id,
                role="assistant",
                content=f"Complex response {i}",
                sent_at=datetime.now(timezone.utc),
                sent_timezone="UTC",
                created_at=datetime.now(timezone.utc),
                extra_data={"routingTier": "standard"},
            )
            db.add(msg)
        await db.commit()

    return chat_id


@pytest.mark.asyncio
async def test_momentum_overrides_simple_in_complex_chat(client: TestClient, chat_with_routing_history: str):
    """Short message in a conversation with STANDARD history should NOT be SIMPLE."""
    chat_id = chat_with_routing_history

    request_body: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "chatId": chat_id,
        "query": "继续",
        "modelSelection": get_model_selection(),
        "lightModelSelection": get_model_selection(),
    }

    routing_events: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("type") == "routing_decision":
                    routing_events.append(data)
                    break

    assert len(routing_events) == 1, "Should receive a routing_decision SSE event"
    tier = routing_events[0].get("data", {}).get("tier")
    assert tier == "standard", f"Expected STANDARD due to momentum, got {tier}"


@pytest.mark.asyncio
async def test_no_momentum_for_new_chat(client: TestClient):
    """Short message in a new chat (no history) should be classified as SIMPLE."""
    chat_id = str(uuid.uuid4())

    request_body: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "chatId": chat_id,
        "query": "hello",
        "modelSelection": get_model_selection(),
        "lightModelSelection": get_model_selection(),
    }

    routing_events: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("type") == "routing_decision":
                    routing_events.append(data)
                    break

    assert len(routing_events) == 1
    tier = routing_events[0].get("data", {}).get("tier")
    assert tier == "simple", f"Expected SIMPLE for new chat greeting, got {tier}"


@pytest.mark.asyncio
async def test_get_recent_routing_tiers_query(setup_test_database):
    """Directly test the DB query for recent routing tiers."""
    from app.database.connection import get_session
    from app.database.models import Chat, Message
    from app.database.repositories.chat_repo import ChatRepository

    chat_id = str(uuid.uuid4())

    async with get_session() as db:
        chat = Chat(
            id=chat_id,
            title="Test",
            created_at=datetime.now(timezone.utc),
        )
        db.add(chat)

        tiers_to_insert = ["standard", "reasoning", "standard", "simple", "reasoning"]
        for i, tier in enumerate(tiers_to_insert):
            msg = Message(
                id=str(uuid.uuid4()),
                chat_id=chat_id,
                role="assistant",
                content=f"msg {i}",
                sent_at=datetime.now(timezone.utc),
                sent_timezone="UTC",
                created_at=datetime.now(timezone.utc),
                extra_data={"routingTier": tier},
            )
            db.add(msg)

        user_msg = Message(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="user",
            content="user message",
            sent_at=datetime.now(timezone.utc),
            sent_timezone="UTC",
            created_at=datetime.now(timezone.utc),
            extra_data=None,
        )
        db.add(user_msg)

        await db.commit()

    async with get_session() as db:
        tiers = await ChatRepository.get_recent_routing_tiers(db, chat_id, limit=5)

    assert len(tiers) == 5
    assert tiers == ["standard", "reasoning", "standard", "simple", "reasoning"]


@pytest.mark.asyncio
async def test_get_recent_routing_tiers_empty_chat(setup_test_database):
    """Empty chat returns empty tier list."""
    from app.database.connection import get_session
    from app.database.repositories.chat_repo import ChatRepository

    async with get_session() as db:
        tiers = await ChatRepository.get_recent_routing_tiers(db, "nonexistent-chat-id")

    assert tiers == []


@pytest.mark.asyncio
async def test_get_recent_routing_tiers_skips_null_extra_data(setup_test_database):
    """Messages without extra_data are skipped."""
    from app.database.connection import get_session
    from app.database.models import Chat, Message
    from app.database.repositories.chat_repo import ChatRepository

    chat_id = str(uuid.uuid4())

    async with get_session() as db:
        chat = Chat(
            id=chat_id,
            title="Test",
            created_at=datetime.now(timezone.utc),
        )
        db.add(chat)

        msg_with_tier = Message(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content="has tier",
            sent_at=datetime.now(timezone.utc),
            sent_timezone="UTC",
            created_at=datetime.now(timezone.utc),
            extra_data={"routingTier": "reasoning"},
        )
        db.add(msg_with_tier)

        msg_no_extra = Message(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content="no extra",
            sent_at=datetime.now(timezone.utc),
            sent_timezone="UTC",
            created_at=datetime.now(timezone.utc),
            extra_data=None,
        )
        db.add(msg_no_extra)

        msg_no_tier = Message(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content="has extra but no tier",
            sent_at=datetime.now(timezone.utc),
            sent_timezone="UTC",
            created_at=datetime.now(timezone.utc),
            extra_data={"someOtherField": "value"},
        )
        db.add(msg_no_tier)

        await db.commit()

    async with get_session() as db:
        tiers = await ChatRepository.get_recent_routing_tiers(db, chat_id)

    assert tiers == ["reasoning"]
