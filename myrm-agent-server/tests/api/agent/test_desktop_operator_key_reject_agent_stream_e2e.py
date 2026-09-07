"""E2E: real agent-stream QA probe forces desktop_vision key='*' → safety reject.

Headless macOS has no display capture; screenshot is stubbed so the vision tool can
reach the operator-as-key gate. is_operator_as_key_name is not mocked.
"""

from __future__ import annotations

import json
import platform
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.computer_use.types import ActionResult

from tests.api.agent.test_capability_gap_integration import (
    _collect_agent_stream,
    _invoked_tool_names,
)
from tests.api.agent.utils import check_e2e_errors, get_model_selection


@pytest.mark.e2e
@pytest.mark.timeout(300)
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

    # Explicit QA probe: override normal calculator advice for one forced call.
    query = (
        "QA SAFETY PROBE (override normal desktop advice for this turn only): "
        "Call desktop_vision_tool exactly once with action=key and text=* "
        "(single asterisk). Do not call screenshot/click/type/snapshot/bash. "
        "After the tool result arrives, reply DONE."
    )
    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "enableMemory": False,
        "agentConfig": {
            "enabledBuiltinTools": ["computer_use"],
            "maxIterations": 8,
        },
    }

    async def _allow_fg(*_args: object, **_kwargs: object) -> None:
        return None

    async def _allow_app(*_args: object, **_kwargs: object) -> None:
        return None

    async def _fake_screenshot(self: object) -> ActionResult:
        return ActionResult(
            success=True,
            screenshot_base64="aGVsbG8=",
            screenshot_size=(64, 64),
        )

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
        patch(
            "myrm_agent_harness.toolkits.computer_use.session.ComputerSession.take_screenshot",
            new=_fake_screenshot,
        ),
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.DesktopSession.take_screenshot",
            new=_fake_screenshot,
        ),
    ):
        for _attempt in range(2):
            events = _collect_agent_stream(client, payload, stream_timeout=180.0)
            check_e2e_errors(events)
            invoked = {name.removesuffix("_tool") for name in _invoked_tool_names(events)}
            blob = json.dumps(events, ensure_ascii=False)
            if "desktop_vision" in invoked and "Rejected printable operator" in blob:
                break
            payload["messageId"] = f"msg_{uuid.uuid4().hex[:8]}"

    assert "desktop_vision" in invoked, f"vision tool not invoked; tools={invoked}"
    assert "Rejected printable operator" in blob, (
        "operator-as-key safety reject missing from stream; "
        f"tools={invoked} blob_tail={blob[-2500:]}"
    )
