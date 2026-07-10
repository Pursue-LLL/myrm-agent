"""Live E2E: agent-stream PONG and direct external CLI delegate PONG."""

from __future__ import annotations

import json
import os
import shutil
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.test_capability_gap_integration import _collect_agent_stream
from tests.api.agent.utils import check_e2e_errors, get_model_selection


def _message_text(events: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for event in events:
        if event.get("type") != "message":
            continue
        data = event.get("data")
        if isinstance(data, str) and data:
            chunks.append(data)
    return "".join(chunks)


def _delegate_stream_started(events: list[dict[str, object]]) -> bool:
    for event in events:
        try:
            raw = json.dumps(event)
        except TypeError:
            continue
        if "delegate:" in raw or "delegation_" in raw:
            return True
    return False


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="Live E2E requires LITE_API_KEY or BASIC_API_KEY",
)
def test_live_agent_stream_pong_reply_ok(client: TestClient) -> None:
    """Primary model returns exactly OK for a minimal prompt (real LLM)."""
    chat_id = f"test_live_pong_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "query": "只回复 OK",
        "message_id": str(uuid.uuid4()),
        "chat_id": chat_id,
        "action_mode": "agent",
        "model_selection": get_model_selection(),
        "timezone": "UTC",
        "enable_memory": False,
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)
    reply = _message_text(events).strip().upper().replace(" ", "")
    assert reply == "OK", f"Expected OK, got {_message_text(events)!r}"


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="Live E2E requires LITE_API_KEY or BASIC_API_KEY",
)
@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not on PATH")
def test_live_direct_delegate_pong_via_force_delegate(
    client: TestClient,
    mock_load_user_configs,
) -> None:
    """Direct delegate via force_delegate_agent uses UserConfig agent name (claude-code)."""
    claude_path = shutil.which("claude")
    assert claude_path is not None
    configs = _build_mock_user_configs()
    configs.external_agents_dict = {
        "agents": [
            {
                "name": "claude-code",
                "type": "cli",
                "command": claude_path,
                "args": ["--output-format", "stream-json", "-p"],
                "enabled": True,
            }
        ]
    }
    mock_load_user_configs.return_value = configs

    chat_id = f"test_live_delegate_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "query": "Reply PONG only",
        "message_id": str(uuid.uuid4()),
        "chat_id": chat_id,
        "agent_id": "builtin-general",
        "action_mode": "agent",
        "force_delegate_agent": "claude-code",
        "agent_config": {"enabled_builtin_tools": ["external_cli"]},
        "model_selection": get_model_selection(),
        "timezone": "UTC",
        "enable_memory": False,
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)
    assert _delegate_stream_started(events), "Direct delegate SSE events missing"
    assert "PONG" in _message_text(events).upper()
