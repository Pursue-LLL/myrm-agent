"""Contract: shared/config/chat_input_limits.json states how long the chat inputs a user types may be.

The frontend reads the same JSON to stop typing and pasting at the limit, so this test is what keeps that file
honest. Each input goes through its real route twice: at exactly the limit, which the server must not refuse for its
length, and one character over it, which the server must refuse with HTTP 422.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport

from app.services.copilot.advisor_thread_store import AdvisorThreadStore
from tests.support.minimal_app import build_minimal_app

_LIMITS_PATH = Path(__file__).resolve().parents[4] / "shared" / "config" / "chat_input_limits.json"
_API = "/api/v1"
_ADVISOR_CHAT = "chat-advisor-limit"
# A rare han character is one character to the server and two UTF-16 units to a browser. The limit is counted in the
# server's unit, so the boundary is probed with characters that tell the two units apart.
_CHARACTER = "\U00020bb7"

app = build_minimal_app("chats", "memory")

_Send = Callable[[httpx.AsyncClient, str], Awaitable[httpx.Response]]


async def _search_messages(client: httpx.AsyncClient, text: str) -> httpx.Response:
    return await client.get(f"{_API}/chats/search", params={"q": text})


async def _search_citable_chats(client: httpx.AsyncClient, text: str) -> httpx.Response:
    return await client.get(f"{_API}/chats/recall/search", params={"q": text})


async def _filter_sidebar(client: httpx.AsyncClient, text: str) -> httpx.Response:
    return await client.get(f"{_API}/chats/", params={"keyword": text})


async def _search_shared_context_history(client: httpx.AsyncClient, text: str) -> httpx.Response:
    return await client.post(f"{_API}/memory/shared-contexts/context-1/history/search", json={"query": text})


async def _compact_chat(client: httpx.AsyncClient, text: str) -> httpx.Response:
    return await client.post(f"{_API}/chats/chat-1/compact", json={"focus_topic": text})


async def _ask_advisor(client: httpx.AsyncClient, text: str) -> httpx.Response:
    # Past the length check the handler would ask a model; the stub keeps this test to the length check.
    with patch("app.api.chats.chat.copilot.ask_advisor", new_callable=AsyncMock, return_value=("a reply", "tier0")):
        try:
            return await client.post(f"{_API}/chats/{_ADVISOR_CHAT}/copilot/advisor/ask", json={"question": text})
        finally:
            AdvisorThreadStore.clear(_ADVISOR_CHAT)


# A limit in the JSON with no route listed here, or a route with no limit, fails the first test below.
_ROUTES_BY_LIMIT: dict[str, tuple[_Send, ...]] = {
    "history_search_query": (_search_messages, _search_citable_chats, _filter_sidebar, _search_shared_context_history),
    "compact_focus_topic": (_compact_chat,),
    "advisor_question": (_ask_advisor,),
}
_CASES = [
    pytest.param(limit, send, id=send.__name__.removeprefix("_")) for limit, routes in _ROUTES_BY_LIMIT.items() for send in routes
]


def _limit(name: str) -> int:
    value = json.loads(_LIMITS_PATH.read_text(encoding="utf-8"))[name]
    assert isinstance(value, int) and value > 0, f"{name} must be a positive whole number"
    return value


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    # A handler that fails on its own answers 500 here: only the length check decides these tests.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=60.0) as test_client:
        yield test_client


def test_every_limit_in_the_shared_file_has_routes_that_enforce_it() -> None:
    assert sorted(json.loads(_LIMITS_PATH.read_text(encoding="utf-8"))) == sorted(_ROUTES_BY_LIMIT)


@pytest.mark.parametrize(("limit", "send"), _CASES)
@pytest.mark.asyncio
async def test_a_text_of_exactly_the_limit_is_not_refused_for_its_length(
    client: httpx.AsyncClient, limit: str, send: _Send
) -> None:
    response = await send(client, _CHARACTER * _limit(limit))

    assert response.status_code != 422, response.text


@pytest.mark.parametrize(("limit", "send"), _CASES)
@pytest.mark.asyncio
async def test_a_text_one_character_over_the_limit_is_refused(client: httpx.AsyncClient, limit: str, send: _Send) -> None:
    response = await send(client, _CHARACTER * (_limit(limit) + 1))

    assert response.status_code == 422, response.text
