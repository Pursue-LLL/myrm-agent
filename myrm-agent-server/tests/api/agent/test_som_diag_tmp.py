"""TEMPORARY diagnostic for SOM e2e snapshot 404 root cause. Delete after use."""

from __future__ import annotations

import platform
import threading
import time
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_capability_gap_integration import (
    _collect_agent_stream,
    _invoked_tool_names,
)
from tests.api.agent.utils import get_model_selection


@pytest.mark.e2e
@pytest.mark.timeout(600)
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_som_diag_gateway_state(
    client: TestClient,
    mock_load_user_configs: AsyncMock,
) -> None:
    """Diagnose why snapshot API returns 404 during stream."""
    from app.services.agent.gateway import get_agent_gateway

    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yoloModeEnabledAt": time.time(),
    }

    chat_id = f"som_diag_{uuid.uuid4().hex[:12]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    gateway = get_agent_gateway()

    statuses: list[tuple[float, int, str]] = []
    stop_poll = threading.Event()

    def _poll_snapshot() -> None:
        while not stop_poll.is_set():
            response = client.get("/webui/desktop/snapshot")
            info = gateway._session_info.get(chat_id)
            agent_ref = info.agent if info else None
            agent_alive = agent_ref() is not None if agent_ref else None
            desktop_session = getattr(agent_ref(), "_desktop_session", None) if (agent_ref and agent_ref()) else None
            statuses.append(
                (
                    time.monotonic(),
                    response.status_code,
                    f"info={bool(info)} agent_alive={agent_alive} desktop_session={desktop_session is not None}",
                )
            )
            time.sleep(0.3)

    poller = threading.Thread(target=_poll_snapshot, daemon=True)
    poller.start()

    query = (
        "CRITICAL: ONLY desktop_snapshot_tool once — no text reply before it. "
        "Call desktop_snapshot_tool with include_screenshot=true and scope=foreground. "
        "Do not use bash, web_search, or any other tools. "
        "After the tool succeeds reply with a single line: DONE."
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

    invoked: set[str] = set()
    try:
        for _attempt in range(2):
            events = _collect_agent_stream(client, payload)
            invoked = {name.removesuffix("_tool") for name in _invoked_tool_names(events)}
            print(f"[diag] attempt={_attempt} invoked={sorted(invoked)}")
            if "desktop_snapshot" in invoked:
                break
            payload["messageId"] = f"msg_{uuid.uuid4().hex[:8]}"
    finally:
        stop_poll.set()
        poller.join(timeout=10)

    print(f"[diag] invoked={sorted(invoked)}")
    print(f"[diag] snapshot polls ({len(statuses)}):")
    for ts, code, detail in statuses[:40]:
        print(f"[diag]   t+{ts - statuses[0][0]:6.1f}s code={code} {detail}")

    assert False, "diagnostic run completed"
