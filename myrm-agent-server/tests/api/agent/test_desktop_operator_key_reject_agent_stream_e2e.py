"""E2E: real agent-stream forces desktop_vision key='*' → safety operator reject.

Validates prompt + harness soft-reject path without mocking is_operator_as_key_name.
Foreground/app gates are waived so the operator check is reachable on CI macOS.
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


@pytest.mark.e2e
@pytest.mark.timeout(420)
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS computer_use only")
def test_agent_stream_rejects_operator_as_vision_key(
    client: TestClient,
    mock_load_user_configs: AsyncMock,
) -> None:
    """Real LLM turn: desktop_vision_tool(action=key, text=*) must hit Safety reject."""
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yoloModeEnabledAt": time.time(),
    }

    chat_id = f"op_key_rej_{uuid.uuid4().hex[:12]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    query = (
        "CRITICAL: Call desktop_vision_tool EXACTLY once with action=key and text=* "
        "(asterisk character only). Do not use type, click, snapshot, bash, or web_search. "
        "Do not substitute Escape/Return. After the tool returns, reply with one line: DONE."
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

    blob = ""
    invoked: set[str] = set()
    with (
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.DesktopSession.check_foreground_permission",
            new=_allow_fg,
        ),
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.DesktopSession.check_app_approval",
            new=_allow_app,
        ),
    ):
        for _attempt in range(3):
            events = _collect_agent_stream(client, payload)
            check_e2e_errors(events)
            invoked = {name.removesuffix("_tool") for name in _invoked_tool_names(events)}
            blob = json.dumps(events, ensure_ascii=False)
            if "desktop_vision" in invoked and "Rejected printable operator" in blob:
                break
            payload["messageId"] = f"msg_{uuid.uuid4().hex[:8]}"

    assert "desktop_vision" in invoked, f"vision tool not invoked; tools={invoked}"
    assert "Rejected printable operator" in blob, (
        "operator-as-key safety reject missing from stream; "
        f"tools={invoked} blob_tail={blob[-2000:]}"
    )
    assert "REMEDY_HINT" in blob or "type" in blob.lower()
