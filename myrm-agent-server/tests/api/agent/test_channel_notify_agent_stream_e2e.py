"""Live-server E2E: agent-stream must invoke channel_notify_tool and deliver to chat."""

from __future__ import annotations

import json
import os
import uuid

import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8080")
_E2E_TIMEOUT = httpx.Timeout(180.0)
NOTIFY_BODY = "E2E agent-stream integration test"

_skip_e2e = pytest.mark.skipif(
    not os.getenv("RUN_E2E_TESTS"),
    reason="Set RUN_E2E_TESTS=1 to run end-to-end tests against live server",
)


def _e2e_request(method: str, url: str, **kwargs: object) -> httpx.Response:
    with httpx.Client(trust_env=False, timeout=_E2E_TIMEOUT) as client:
        return client.request(method, url, **kwargs)


def _collect_agent_stream(payload: dict[str, object]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    with httpx.Client(trust_env=False, timeout=_E2E_TIMEOUT) as client:
        with client.stream(
            "POST",
            f"{BASE_URL}/api/v1/agents/agent-stream",
            json=payload,
            headers={"Accept": "text/event-stream"},
        ) as response:
            if response.status_code != 200:
                body = response.read().decode("utf-8", errors="replace")
                raise AssertionError(f"agent-stream failed: {response.status_code} {body}")
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw == "[DONE]":
                    break
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    events.append(parsed)
    return events


def _invoked_tool_names(events: list[dict[str, object]]) -> set[str]:
    names: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") not in {"tasks_steps", "tool_start", "tool_end"}:
            continue
        tool_name = event.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            names.add(tool_name)
    return names


@_skip_e2e
@pytest.mark.e2e
class TestChannelNotifyAgentStreamLive:
    def test_agent_stream_channel_notify_delivers_to_chat(self) -> None:
        """Real agent-stream on live server: channel_notify_tool → chat channel ORM write."""
        raw_model = os.environ.get("LITE_MODEL") or os.environ.get("BASIC_MODEL")
        assert raw_model, "LITE_MODEL or BASIC_MODEL required in .env.test"
        provider_id = raw_model.split("/")[0] if "/" in raw_model else "minimax"
        model = raw_model.split("/", 1)[1] if "/" in raw_model else raw_model

        recipient_chat_id = f"notify_stream_{uuid.uuid4().hex[:8]}"
        agent_resp = _e2e_request(
            "POST",
            f"{BASE_URL}/api/v1/user-agents",
            json={
                "name": "Channel Notify Stream Live E2E",
                "system_prompt": "You send notifications when asked.",
                "notify_targets": [
                    {"channel": "chat", "recipient_id": recipient_chat_id, "label": "Stream E2E"},
                ],
            },
        )
        assert agent_resp.status_code == 200, agent_resp.text
        agent_id = agent_resp.json()["data"]["id"]

        chat_id = f"stream_src_{uuid.uuid4().hex[:8]}"
        assert _e2e_request("POST", f"{BASE_URL}/api/v1/chats/", json={"chat_id": chat_id}).status_code == 200

        query = (
            "Call channel_notify_tool exactly once. "
            f'Send body "{NOTIFY_BODY}" to the configured chat target. '
            "Do not call any other tools. After success, reply NOTIFY_DONE."
        )

        try:
            events = _collect_agent_stream(
                {
                    "message_id": f"msg_{uuid.uuid4().hex[:8]}",
                    "chat_id": chat_id,
                    "query": query,
                    "action_mode": "agent",
                    "agent_id": agent_id,
                    "model_selection": {"providerId": provider_id, "model": model},
                    "enable_memory": False,
                },
            )
            assert "channel_notify_tool" in _invoked_tool_names(events)

            msg_resp = _e2e_request("GET", f"{BASE_URL}/api/v1/chats/{recipient_chat_id}/messages")
            assert msg_resp.status_code == 200, msg_resp.text
            messages = msg_resp.json().get("data", {}).get("messages", [])
            delivered = [
                msg
                for msg in messages
                if isinstance(msg, dict)
                and isinstance(msg.get("content"), str)
                and NOTIFY_BODY in msg["content"]
            ]
            assert delivered, f"Expected delivery in {recipient_chat_id}; messages={messages}"
        finally:
            _e2e_request("DELETE", f"{BASE_URL}/api/v1/user-agents/{agent_id}")
