"""E2E: agent-stream desktop_snapshot_tool → live GET /webui/desktop/snapshot with SOM nth.

Polls snapshot API while stream is active (gateway keeps desktop session until stream end).
"""

from __future__ import annotations

import platform
import subprocess
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
from tests.api.agent.utils import check_e2e_errors, get_model_selection


def _activate_textedit() -> None:
    if platform.system() != "Darwin":
        return
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "TextEdit" to activate',
            "-e",
            'tell application "System Events" to tell process "TextEdit" to set frontmost to true',
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )


@pytest.mark.e2e
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS computer_use only")
def test_agent_stream_desktop_snapshot_api_returns_som_nth(
    client: TestClient,
    mock_load_user_configs: AsyncMock,
) -> None:
    """Real agent-stream: desktop_snapshot_tool active session exposes nth via snapshot API."""
    _activate_textedit()

    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yoloModeEnabledAt": time.time(),
    }

    chat_id = f"som_stream_e2e_{uuid.uuid4().hex[:12]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    snapshots: list[dict[str, object]] = []
    stop_poll = threading.Event()

    def _poll_snapshot() -> None:
        while not stop_poll.is_set():
            response = client.get("/webui/desktop/snapshot")
            if response.status_code == 200:
                body = response.json()
                if isinstance(body, dict):
                    snapshots.append(body)
            time.sleep(0.4)

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
        for _attempt in range(3):
            events = _collect_agent_stream(client, payload)
            check_e2e_errors(events)
            invoked = {name.removesuffix("_tool") for name in _invoked_tool_names(events)}
            if "desktop_snapshot" in invoked:
                break
            payload["messageId"] = f"msg_{uuid.uuid4().hex[:8]}"
    finally:
        stop_poll.set()
        poller.join(timeout=10)

    if "desktop_snapshot" not in invoked:
        pytest.skip(
            "model did not invoke desktop_snapshot_tool after 3 attempts; "
            f"invoked={sorted(invoked)} event_types="
            f"{sorted({e.get('type') for e in events if isinstance(e.get('type'), str)})}"
        )

    assert snapshots, (
        "GET /webui/desktop/snapshot never returned 200 during stream; "
        "gateway may have closed session before poll"
    )

    nth_values: list[int] = []
    for snap in snapshots:
        refs = snap.get("refs")
        if not isinstance(refs, dict):
            continue
        for ref in refs.values():
            if isinstance(ref, dict) and ref.get("nth") is not None:
                nth_values.append(int(ref["nth"]))  # type: ignore[arg-type]

    assert nth_values, (
        f"No nth in snapshot refs across {len(snapshots)} successful polls; "
        f"last_app={snapshots[-1].get('app_name')!r} ref_count="
        f"{len(snapshots[-1].get('refs', {})) if isinstance(snapshots[-1].get('refs'), dict) else 0}"
    )
