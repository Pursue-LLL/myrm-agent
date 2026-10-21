"""HITL approval gate and resume against the real agent-stream pipeline: real model, no mocks.

A loopback HTTP server stands in for the command's target, so the test knows from the outside whether the approved
``curl`` really ran: no request may arrive while the turn is parked behind the approval card, one must arrive once the
user approved and the run resumed. Several parked turns follow each other in one chat to prove every resume works.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.core.events.types import AgentEventType

from tests.api.agent.utils import build_approval_resume_value, get_model_selection

_APPROVAL_EVENT_TYPE = AgentEventType.TOOL_APPROVAL_REQUEST.value
_ERROR_EVENT_TYPE = AgentEventType.ERROR.value
_MESSAGE_EVENT_TYPE = AgentEventType.MESSAGE.value

_PARKED_TURNS = 3
# A model may answer without calling the tool; each turn is asked again before it counts as a failure.
_PARK_ATTEMPTS = 3
# Cards one turn may park behind: the model's first command and a retry or two of it.
_APPROVALS_PER_TURN = 3
# The resume races the previous stream's session release; a busy answer is retried for a few seconds.
_BUSY_RETRIES = 20
_UPSTREAM_FLAKY_SIGNALS = (
    "Authentication",
    "Authorization",
    "Cannot connect",
    "Connection error",
    "InternalServerError",
    "quota exceeded",
)


class _ProbeServer(ThreadingHTTPServer):
    """Records the path of every request it answers."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _ProbeHandler)
        self.paths: list[str] = []


class _ProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        cast("_ProbeServer", self.server).paths.append(self.path)
        body = b"HITL-PROBE"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture
def probe_server() -> Iterator[_ProbeServer]:
    server = _ProbeServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _stream(client: TestClient, payload: dict[str, object]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload, timeout=240.0) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            line = line.strip()
            if not line.startswith("data: "):
                continue
            raw = line[6:]
            if raw == "[DONE]":
                break
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                events.append(data)
    return events


def _request(chat_id: str, query: str, **extra: object) -> dict[str, object]:
    return {
        "chatId": chat_id,
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "enableMemory": False,
        **extra,
    }


def _skip_on_upstream_error(events: list[dict[str, object]]) -> None:
    for event in events:
        if event.get("type") == _ERROR_EVENT_TYPE and any(signal in str(event) for signal in _UPSTREAM_FLAKY_SIGNALS):
            pytest.skip(f"upstream model error: {str(event)[:240]}")


def _is_parked(events: list[dict[str, object]]) -> bool:
    return any(event.get("type") == _APPROVAL_EVENT_TYPE for event in events)


def _park(client: TestClient, chat_id: str, query: str) -> None:
    """Send ``query`` until the run stops behind a tool-approval card."""
    kinds: list[str] = []
    for _ in range(_PARK_ATTEMPTS):
        events = _stream(client, _request(chat_id, query))
        _skip_on_upstream_error(events)
        if _is_parked(events):
            return
        kinds = [str(event.get("type")) for event in events]
    pytest.fail(f"the model never requested the approval ({_PARK_ATTEMPTS} attempts); last event types: {kinds}")


def _approve(client: TestClient, chat_id: str) -> list[dict[str, object]]:
    """Press Approve for the run parked in ``chat_id`` and return what the resumed run streamed."""
    for _ in range(_BUSY_RETRIES):
        events = _stream(client, _request(chat_id, "", resumeValue=build_approval_resume_value(allow_always=False)))
        if any(event.get("error_type") == "AgentBusyError" for event in events):
            time.sleep(0.25)
            continue
        _skip_on_upstream_error(events)
        return events
    pytest.fail("the resume was answered with AgentBusyError for the whole retry window")


def _reply_text(events: list[dict[str, object]]) -> str:
    return "".join(str(event.get("data")) for event in events if event.get("type") == _MESSAGE_EVENT_TYPE)


@pytest.mark.e2e
@pytest.mark.skipif(not os.environ.get("BASIC_API_KEY"), reason="E2E test requires BASIC_API_KEY environment variable")
def test_each_parked_turn_runs_its_command_only_after_approval(
    client: TestClient, mock_load_user_configs: pytest.AsyncMock, probe_server: _ProbeServer
) -> None:
    mock_load_user_configs.return_value.security_config_dict = {"yoloModeEnabled": False, "autoModeEnabled": False}
    chat_id = f"hitl_{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/chats/", json={"chat_id": chat_id}).status_code == 200

    for turn in range(1, _PARKED_TURNS + 1):
        path = f"/hitl-turn-{turn}"
        done_token = f"HITL-TURN-{turn}-DONE"
        _park(
            client,
            chat_id,
            f"Run exactly this one plain command with the bash tool, with no ';', '&&', pipe or redirect: "
            f"curl -sS http://127.0.0.1:{probe_server.server_port}{path} . Run no other command. "
            f"After it finishes, reply with exactly: {done_token}",
        )
        assert path not in probe_server.paths, f"turn {turn}: the command ran before the user approved it"

        resumed: list[dict[str, object]] = []
        for _ in range(_APPROVALS_PER_TURN):
            resumed = _approve(client, chat_id)
            if not _is_parked(resumed):
                break
        else:
            pytest.fail(f"turn {turn}: still parked after {_APPROVALS_PER_TURN} approvals")

        kinds = [str(event.get("type")) for event in resumed]
        assert path in probe_server.paths, f"turn {turn}: the approved command never ran; resumed event types: {kinds}"
        assert _ERROR_EVENT_TYPE not in kinds, f"turn {turn}: the resumed run errored: {resumed}"
        assert "rejected by user" not in json.dumps(resumed).lower(), f"turn {turn}: the approval was treated as a rejection"
        assert done_token in _reply_text(resumed), (
            f"turn {turn}: the resumed run did not finish its turn: {_reply_text(resumed)[-200:]!r}"
        )
