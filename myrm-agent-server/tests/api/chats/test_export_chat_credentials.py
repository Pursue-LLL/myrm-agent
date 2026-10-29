"""GET /chats/{chat_id}/export masks a credential by the field that holds it, however deep the field sits."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from app.config.settings import settings
from app.database.models.chat import Chat, Message
from app.platform_utils import get_session_factory
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")

_COOKIE_SECRET = "Zx81qPw0Lm3"
_BASIC_SECRET = "dXNlcjpwYXNz"
_PASSWORD = "Summer2024!x"
_TOKEN = "sk-test-abcdefghijklmnopqrstuvwxyz1234567890abcdef"


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


async def _create_chat(chat_id: str, *, metadata: dict[str, object] | None = None) -> None:
    async with get_session_factory()() as db:
        db.add(Chat(id=chat_id, title="Export", action_mode="fast", source="web"))
        db.add(
            Message(
                id=f"msg-{uuid.uuid4().hex[:8]}",
                chat_id=chat_id,
                role="assistant",
                content="Done.",
                extra_data=metadata,
                sent_at=datetime.now(tz=timezone.utc),
                sent_timezone="UTC",
            )
        )
        await db.commit()


def _write_tool_call(chat_id: str, tool_input: dict[str, object]) -> None:
    """Write the event-log lines of one tool call whose input is ``tool_input``."""
    log_dir = Path(settings.database.event_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    start = datetime.now(tz=timezone.utc).timestamp() - 10
    events = [
        ("tool_start", start, {"tool_name": "http_request", "tool_call_id": "call-1", **tool_input}),
        ("tool_end", start + 0.2, {"tool_name": "http_request", "tool_call_id": "call-1", "duration_ms": 200}),
    ]
    with (log_dir / f"{chat_id}.jsonl").open("w", encoding="utf-8") as log:
        for seq, (kind, ts, data) in enumerate(events):
            log.write(json.dumps({"seq": seq, "ts": ts, "type": kind, "sid": chat_id, "data": data}) + "\n")


def _nested(levels: int, leaf: object) -> dict[str, object]:
    payload: dict[str, object] = {"a": leaf}
    for _ in range(levels - 1):
        payload = {"a": payload}
    return payload


async def _export(client: httpx.AsyncClient, chat_id: str, *, redact_secrets: bool = True) -> dict[str, object]:
    res = await client.get(f"/api/v1/chats/{chat_id}/export?redact_secrets={str(redact_secrets).lower()}")
    assert res.status_code == 200, res.text
    return res.json()["data"]


@pytest.mark.asyncio
async def test_a_credential_field_inside_a_nested_tool_argument_is_masked(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test-export-cred-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    _write_tool_call(
        chat_id,
        {
            "url": "https://example.com",
            "headers": {
                "Accept": "text/html",
                "Cookie": f"sessionid={_COOKIE_SECRET}",
                "Authorization": f"Basic {_BASIC_SECRET}",
            },
            "auth": [{"password": _PASSWORD}],
        },
    )

    summary = (await _export(async_client, chat_id))["toolCallDetails"][0]["argsSummary"]

    for secret in (_COOKIE_SECRET, _BASIC_SECRET, _PASSWORD):
        assert secret not in summary
    assert "https://example.com" in summary
    assert "text/html" in summary


@pytest.mark.asyncio
async def test_the_tool_argument_stays_readable_when_redaction_is_off(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test-export-cred-raw-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    _write_tool_call(chat_id, {"headers": {"Cookie": f"sessionid={_COOKIE_SECRET}"}})

    summary = (await _export(async_client, chat_id, redact_secrets=False))["toolCallDetails"][0]["argsSummary"]

    assert _COOKIE_SECRET in summary


@pytest.mark.asyncio
@pytest.mark.parametrize("levels", [20, 40])
async def test_metadata_nested_past_the_old_depth_limit_does_not_leak(async_client: httpx.AsyncClient, levels: int) -> None:
    chat_id = f"test-export-deep-{uuid.uuid4().hex[:8]}-{levels}"
    await _create_chat(chat_id, metadata=_nested(levels, f"Authorization: Bearer {_TOKEN}"))

    exported = await _export(async_client, chat_id)

    assert _TOKEN not in json.dumps(exported)


@pytest.mark.asyncio
async def test_a_key_that_is_a_credential_is_masked(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test-export-key-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id, metadata={"env": {_TOKEN: "prod"}})

    exported = await _export(async_client, chat_id)

    assert _TOKEN not in json.dumps(exported)


@pytest.mark.asyncio
async def test_a_credential_field_in_message_metadata_is_masked_whatever_the_shape_of_its_text(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = f"test-export-meta-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id, metadata={"headers": {"Cookie": f"sessionid={_COOKIE_SECRET}", "Accept": "text/html"}})

    exported = await _export(async_client, chat_id)

    assert _COOKIE_SECRET not in json.dumps(exported)
    assert "text/html" in json.dumps(exported)
