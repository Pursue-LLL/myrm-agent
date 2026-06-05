import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
import pytest
from httpx import ASGITransport

from app.main import app

HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {os.environ.get('BASIC_API_KEY', 'dummy')}"}


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", headers=HEADERS, timeout=30.0
    ) as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_catchup_flow(async_client: httpx.AsyncClient) -> None:
    """Test the Catchup Inbox flow: create chat, add messages with tool calls, get brief, mark read."""
    chat_id = f"test-catchup-{uuid.uuid4().hex[:8]}"

    # 1. Create a chat and add some messages directly via DB
    from app.database.models.chat import Chat, Message
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(id=chat_id, title="Refactor main.py", action_mode="fast", source="web")
        db.add(chat)

        msg1 = Message(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            chat_id=chat_id,
            role="user",
            content="Refactor main.py",
            sent_at=datetime.now(timezone.utc),
            sent_timezone="UTC",
        )
        db.add(msg1)

        msg2 = Message(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            chat_id=chat_id,
            role="assistant",
            content="I have refactored the file.",
            sent_at=datetime.now(timezone.utc),
            sent_timezone="UTC",
            extra_data={"progressSteps": [{"tool_name": "file_write_tool", "items": [{"path": "main.py"}]}]},
        )
        db.add(msg2)
        await db.commit()

    # 2. Fetch the catchup briefs
    catchup_res = await async_client.get("/api/v1/chats/catchup")
    assert catchup_res.status_code == 200
    data = catchup_res.json()
    assert "data" in data
    assert "briefs" in data["data"]

    briefs = data["data"]["briefs"]

    # Find our chat in the briefs
    our_brief = next((b for b in briefs if b["chat_id"] == chat_id), None)
    assert our_brief is not None, f"Chat {chat_id} not found in catchup briefs"

    assert our_brief["last_user_prompt"] == "Refactor main.py"
    assert our_brief["status"] == "completed"

    # 3. Mark as read
    read_res = await async_client.post(f"/api/v1/chats/{chat_id}/read")
    assert read_res.status_code == 200

    # 4. Fetch briefs again, our chat should be gone
    catchup_res2 = await async_client.get("/api/v1/chats/catchup")
    data2 = catchup_res2.json()
    briefs2 = data2["data"]["briefs"]
    our_brief2 = next((b for b in briefs2 if b["chat_id"] == chat_id), None)
    assert our_brief2 is None, f"Chat {chat_id} should have been marked as read and removed from briefs"
