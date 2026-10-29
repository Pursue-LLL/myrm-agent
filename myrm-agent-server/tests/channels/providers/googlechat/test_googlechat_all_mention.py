"""Agent text cannot mention everyone in a Google Chat space, in either markup syntax.

``<users/all>`` (Chat markup) and ``<chat-user data-user="users/all">`` (Markdown) notify the whole space when
they arrive as sent; the client defuses them in every message it creates or edits.
"""

from __future__ import annotations

import json
import re

import httpx
import pytest

from app.channels.providers.googlechat.api import GoogleChatClient

_ZWSP = "\u200b"
_ALL_MENTION = re.compile(r"<(?:users/all\b|chat-user\b[^<>]*\bdata-user\s*=\s*[\"']?users/all\b)", re.IGNORECASE)

_ALL_FORMS = [
    "<users/all>",
    "<USERS/ALL>",
    '<chat-user data-user="users/all">',
    "<chat-user data-user='users/all'>",
    "<chat-user data-user=users/all>",
    '<chat-user class="x" data-user = "users/all">',
]
_INERT_TEXT = [
    "<users/123456789>",
    "<users/allen>",
    "<users/all_hands>",
    '<chat-user data-user="users/123">',
    '<chat-user data-user="users/all_hands">',
    "plain <b>text</b> & 100%",
    "the words users/all in prose",
]


def _client(requests: list[tuple[str, dict[str, object]]]) -> GoogleChatClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, json.loads(request.content)))
        return httpx.Response(200, json={"name": "spaces/S/messages/M"})

    client = GoogleChatClient("")
    client._token = "tok"
    client._token_expires_at = float("inf")
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


@pytest.mark.parametrize("form", _ALL_FORMS)
@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.asyncio
async def test_mention_everyone_is_defused(operation: str, form: str) -> None:
    requests: list[tuple[str, dict[str, object]]] = []
    client = _client(requests)
    text = f"Heads up {form}: deploy done"

    if operation == "create":
        await client.send_message("spaces/S", text)
    else:
        await client.update_message("spaces/S/messages/M", text)

    sent = str(requests[0][1]["text"])
    assert not _ALL_MENTION.search(sent)
    assert sent.replace(_ZWSP, "") == text
    assert _ZWSP in sent


@pytest.mark.parametrize("text", _INERT_TEXT)
@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.asyncio
async def test_other_text_is_sent_unchanged(operation: str, text: str) -> None:
    requests: list[tuple[str, dict[str, object]]] = []
    client = _client(requests)

    if operation == "create":
        await client.send_message("spaces/S", text)
    else:
        await client.update_message("spaces/S/messages/M", text)

    assert requests[0][1]["text"] == text
