"""E2E: agent-stream computer_use rejects printable operators as vision key names.

Real LLM must call desktop_vision_tool(action=key, text='*'); safety returns
Rejected printable operator + REMEDY_HINT before any OS key press.
"""

from __future__ import annotations

import json
import platform
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_capability_gap_integration import (
    _collect_agent_stream,
    _invoked_tool_names,
)
from tests.api.agent.utils import get_model_selection

_REJECT_MARKERS = ("Rejected printable operator", "REMEDY_HINT: Printable operators")


def _events_blob(events: list[dict[str, object]]) -> str:
    return json.dumps(events, ensure_ascii=False, default=str)


def _stop_on_operator_reject(
    event: dict[str, object],
    collected: list[dict[str, object]],
) -> bool:
    blob = _events_blob(collected)
    return any(marker in blob for marker in _REJECT_MARKERS)


@pytest.mark.e2e
@pytest.mark.timeout(420)
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS computer_use only")
def test_agent_stream_rejects_operator_as_vision_key(
    client: TestClient,
    mock_load_user_configs: AsyncMock,
) -> None:
    """Lane-C: real model + computer_use → key='*' must hit safety reject."""
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yoloModeEnabledAt": time.time(),
    }

    chat_id = f"op_key_e2e_{uuid.uuid4().hex[:12]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    query = (
        "CRITICAL: Call desktop_vision_tool exactly once with action=key and text=*. "
        "Do not use type/click/other tools. After the tool returns, reply with DONE only."
    )
    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "enableMemory": False,
        "agentConfig": {"enabledBuiltinTools": ["computer_use"]},
    }

    events: list[dict[str, object]] = []
    invoked: set[str] = set()
    blob = ""

    with (
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.DesktopSession.check_foreground_permission",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.DesktopSession.check_app_approval",
            new=AsyncMock(return_value=None),
        ),
    ):
        for _attempt in range(3):
            events = _collect_agent_stream(
                client,
                payload,
                stream_timeout=180.0,
                stop_when=_stop_on_operator_reject,
            )
            invoked = {name.removesuffix("_tool") for name in _invoked_tool_names(events)}
            blob = _events_blob(events)
            if any(marker in blob for marker in _REJECT_MARKERS):
                break
            if "desktop_vision" in invoked:
                # Tool ran but payload not yet in stream markers — keep blob for assert.
                break
            payload["messageId"] = f"msg_{uuid.uuid4().hex[:8]}"

    if "desktop_vision" not in invoked and not any(m in blob for m in _REJECT_MARKERS):
        pytest.skip(
            "model did not invoke desktop_vision_tool after 3 attempts; "
            f"invoked={sorted(invoked)} types="
            f"{sorted({e.get('type') for e in events if isinstance(e.get('type'), str)})}"
        )

    assert any(marker in blob for marker in _REJECT_MARKERS), (
        "expected operator-as-key safety reject in agent-stream events; "
        f"invoked={sorted(invoked)} blob_sample={blob[:1200]!r}"
    )
