"""Agent text cannot mention everyone in a Feishu chat, whichever message type carries it.

``<at user_id="all">`` in a text message and ``<at id=all>`` in card markdown notify the whole group when they
arrive as sent. Every message the client posts or edits, and every streamed card update, defuses them.
"""

from __future__ import annotations

import json
import re
import time

import httpx
import pytest

from app.channels.providers.feishu.cards import build_post_content, build_result_card, wrap_text_as_card
from app.channels.providers.feishu.sdk import FeishuClient

_ZWSP = "\u200b"
# What Feishu treats as mention-everyone, written independently of the production pattern.
_AT_ALL = re.compile(r"<at\b[^<>]*\b(?:user_)?id\s*=\s*[\"']?all\b", re.IGNORECASE)

_AT_ALL_FORMS = [
    '<at user_id="all"></at>',
    '<at user_id="all">Everyone</at>',
    "<at user_id='all'></at>",
    '<at user_id = "all"></at>',
    "<at id=all></at>",
    '<at id="all"></at>',
    '<AT USER_ID="ALL"></AT>',
    "<at\nid=all></at>",
]
_INERT_TEXT = [
    '<at user_id="ou_abc123">Alice</at> hello',
    '<at id="ou_abc123"></at>',
    '<at id="all_hands_bot">bot</at>',
    '<at email="a@b.co"></at>',
    "no tags here, 100% & <b>bold</b>",
    "the word all and <at> alone",
]


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


def _client(requests: list[tuple[str, dict[str, object]]]) -> FeishuClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, json.loads(request.content)))
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1"}})

    client = FeishuClient("app", "secret")
    client._token = "tok"
    client._token_expires_at = time.monotonic() + 3600
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def _contents(text: str) -> dict[str, str]:
    """The same agent text as each message type the channel builds."""
    return {
        "text": json.dumps({"text": text}, ensure_ascii=False),
        "post": json.dumps(build_post_content(text), ensure_ascii=False),
        "card": json.dumps(wrap_text_as_card(text), ensure_ascii=False),
        "result card": json.dumps(build_result_card(text, title="t", timestamp="now"), ensure_ascii=False),
    }


def _sent_strings(requests: list[tuple[str, dict[str, object]]]) -> list[str]:
    return [s for _, body in requests for s in _strings(json.loads(str(body["content"])))]


@pytest.mark.parametrize("form", _AT_ALL_FORMS)
@pytest.mark.parametrize("kind", ["text", "post", "card", "result card"])
@pytest.mark.parametrize("operation", ["send", "reply", "edit", "patch"])
@pytest.mark.asyncio
async def test_every_message_operation_defuses_mention_everyone(operation: str, kind: str, form: str) -> None:
    requests: list[tuple[str, dict[str, object]]] = []
    client = _client(requests)
    content = _contents(f"notice {form} now")[kind]

    if operation == "send":
        await client.send_message("oc_1", "text", content)
    elif operation == "reply":
        await client.reply_message("om_1", "text", content)
    elif operation == "edit":
        await client.edit_message("om_1", "interactive", content)
    else:
        await client.patch_message("om_1", "interactive", content)

    sent = _sent_strings(requests)
    assert not any(_AT_ALL.search(s) for s in sent)
    assert str(requests[0][1]["content"]).replace(_ZWSP, "") == content
    # A post splits text at newlines, which already takes a tag apart; every other layout carried a live tag.
    carried_a_tag = any(_AT_ALL.search(s) for s in _strings(json.loads(content)))
    assert carried_a_tag or (kind == "post" and "\n" in form)
    assert carried_a_tag == any(_ZWSP in s for s in sent)


@pytest.mark.parametrize("form", _AT_ALL_FORMS)
@pytest.mark.parametrize("is_final", [False, True])
@pytest.mark.asyncio
async def test_a_streamed_card_update_defuses_mention_everyone(form: str, is_final: bool) -> None:
    requests: list[tuple[str, dict[str, object]]] = []
    client = _client(requests)

    await client.streaming_card_update("card_1", f"so far {form}", seq=2, is_final=is_final)

    text = str(requests[0][1]["content"])
    assert not _AT_ALL.search(text)
    assert text.replace(_ZWSP, "") == f"so far {form}"


@pytest.mark.parametrize("text", _INERT_TEXT)
@pytest.mark.parametrize("kind", ["text", "post", "card"])
@pytest.mark.asyncio
async def test_other_text_is_sent_unchanged(kind: str, text: str) -> None:
    requests: list[tuple[str, dict[str, object]]] = []
    client = _client(requests)
    content = _contents(text)[kind]

    await client.send_message("oc_1", "text", content)

    assert requests[0][1]["content"] == content


@pytest.mark.asyncio
async def test_a_streamed_card_update_without_a_mention_is_unchanged() -> None:
    requests: list[tuple[str, dict[str, object]]] = []
    client = _client(requests)

    await client.streaming_card_update("card_1", '<at user_id="ou_1">Alice</at> done', seq=2)

    assert requests[0][1]["content"] == '<at user_id="ou_1">Alice</at> done'
