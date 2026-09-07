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
from tests.api.agent.utils import check_e2e_errors, get_model_selection


def _tool_payload_text(events: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for event in events:
        if event.get("type") not in {"tool_end", "tasks_steps", "message"}:
            continue
        for key in ("content", "result", "output", "message"):
            value = event.get(key)
            if isinstance(value, str) and value:
                chunks.append(value)
        data = event.get("data")
        if isinstance(data, str) and data:
            chunks.append(data)
        elif isinstance(data, dict):
            chunks.append(json.dumps(data, ensure_ascii=False))
    return "\n".join(chunks)


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
        "CRITICAL: You MUST call desktop_vision_tool exactly once with "
        "action=key and text=* (asterisk only). Do not use type, click, or other tools. "
        "Do not rewrite * as multiply or Return. After the tool returns, reply DONE."
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

    async def _allow_fg(*_args: object, **_kwargs: object) -> None:
        return None

    async def _allow_app(*_args: object, **_kwargs: object) -> None:
        return None

    events: list[dict[str, object]] = []
    invoked: set[str] = set()
    blob = ""

    with (
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.DesktopSession.check_foreground_permission",
            new=AsyncMock(side_effect=_allow_fg),
        ),
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.DesktopSession.check_app_approval",
            new=AsyncMock(side_effect=_allow_app),
        ),
    ):
        for _attempt in range(3):
            events = _collect_agent_stream(client, payload)
            check_e2e_errors(events)
            invoked = {name.removesuffix("_tool") for name in _invoked_tool_names(events)}
            blob = _tool_payload_text(events)
            if "desktop_vision" in invoked and (
                "Rejected printable operator" in blob or "REMEDY_HINT" in blob
            ):
                break
            payload["messageId"] = f"msg_{uuid.uuid4().hex[:8]}"

    if "desktop_vision" not in invoked:
        pytest.skip(
            "model did not invoke desktop_vision_tool after 3 attempts; "
            f"invoked={sorted(invoked)} types="
            f"{sorted({e.get('type') for e in events if isinstance(e.get('type'), str)})}"
        )

    assert "Rejected printable operator" in blob or "REMEDY_HINT" in blob, (
        "expected operator-as-key safety reject in tool/stream payload; "
        f"invoked={sorted(invoked)} blob_sample={blob[:800]!r}"
    )
