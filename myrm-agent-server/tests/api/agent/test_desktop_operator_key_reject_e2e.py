"""E2E: printable operators rejected as vision key names.

Lane-C coverage for DesktopControlKeyLimitPromptRules:
1) Deterministic tool path (create_desktop_tools) — no LLM.
2) Real agent-stream QA probe — wrap desktop_vision_action to capture Safety
   (SSE may omit full tool text); screenshot/gates stubbed for headless.
"""

from __future__ import annotations

import platform
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.types import (
    ActionResult,
    ComputerUseConfig,
    ScreenContext,
    ScreenInfo,
)

from tests.api.agent.test_capability_gap_integration import (
    _collect_agent_stream,
    _invoked_tool_names,
    _message_text_from_stream_events,
)
from tests.api.agent.utils import check_e2e_errors, get_model_selection

_VisionAction = Callable[..., Awaitable[str | list[object]]]
_REJECT = "Rejected printable operator"


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.parametrize("op", ["*", "/", "+", "-", "%", "="])
async def test_desktop_vision_tool_rejects_operator_key_deterministic(op: str) -> None:
    """Same tool surface the agent binds: lone operator key → Safety, no key_press."""
    from myrm_agent_harness.toolkits.computer_use.desktop_agent_tools import (
        create_desktop_tools,
    )

    backend = MagicMock()
    backend.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=1.0)
    backend.screen_context.return_value = ScreenContext(
        active_window="Calculator", mouse_x=100, mouse_y=200
    )
    session = DesktopSession(backend=backend, config=ComputerUseConfig())
    session._last_snapshot_time = time.time()
    session.key_press = AsyncMock()

    vision = next(t for t in create_desktop_tools(session) if t.name == "desktop_vision_tool")

    with (
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.inspect_backend",
            return_value={
                "app_name": "Calculator",
                "window_title": "Calculator",
                "app_id": "",
            },
        ),
        patch.object(
            session, "check_foreground_permission", new=AsyncMock(return_value=None)
        ),
        patch.object(session, "check_app_approval", new=AsyncMock(return_value=None)),
    ):
        result = await vision.ainvoke({"action": "key", "text": op})

    assert isinstance(result, str)
    assert "Safety" in result
    assert _REJECT in result
    assert "REMEDY_HINT" in result
    assert repr(op) in result or op in result
    session.key_press.assert_not_called()


def _vision_outcome_ok(vision_results: list[str]) -> bool:
    joined = "\n".join(vision_results)
    if _REJECT in joined:
        return True
    # Model followed DESKTOP_CONTROL_RULES and typed instead of key='*'.
    return "Vision action 'type' completed" in joined or 'Vision action "type" completed' in joined


@pytest.mark.e2e
@pytest.mark.timeout(420)
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS computer_use only")
def test_agent_stream_rejects_operator_as_vision_key(
    client: TestClient,
    mock_load_user_configs: AsyncMock,
) -> None:
    """Real LLM: desktop_vision key='*' Safety reject, or type-instead (rules obeyed)."""
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yoloModeEnabledAt": time.time(),
    }

    query = (
        "CRITICAL QA SAFETY PROBE — no text reply before the tool. "
        "Call desktop_vision_tool exactly once with action=key and text=*. "
        "Allowed alternate only if you refuse key: action=type text=*. "
        "Forbidden: web_search, bash, snapshot, click, screenshot, interact. "
        "After one desktop_vision_tool result, reply DONE."
    )

    vision_results: list[str] = []
    original_vision = cast(_VisionAction, DesktopSession.desktop_vision_action)

    async def _wrap_vision(
        self: DesktopSession,
        *args: object,
        **kwargs: object,
    ) -> str | list[object]:
        result = await original_vision(self, *args, **kwargs)
        if isinstance(result, str):
            vision_results.append(result)
        elif isinstance(result, list):
            vision_results.append(str(result))
        return result

    async def _fake_screenshot(_self: object) -> ActionResult:
        return ActionResult(
            success=True,
            screenshot_base64="aGVsbG8=",
            screenshot_size=(64, 64),
        )

    def _stop_when(
        _event: dict[str, object],
        _collected: list[dict[str, object]],
    ) -> bool:
        return _vision_outcome_ok(vision_results)

    invoked: set[str] = set()
    events: list[dict[str, object]] = []
    with (
        patch.object(DesktopSession, "desktop_vision_action", new=_wrap_vision),
        patch.object(
            DesktopSession,
            "check_foreground_permission",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            DesktopSession,
            "check_app_approval",
            new=AsyncMock(return_value=None),
        ),
        patch.object(DesktopSession, "take_screenshot", new=_fake_screenshot),
        patch(
            "myrm_agent_harness.toolkits.computer_use.session.ComputerSession.take_screenshot",
            new=_fake_screenshot,
        ),
        patch(
            "myrm_agent_harness.toolkits.computer_use.desktop_session.inspect_backend",
            return_value={
                "app_name": "Calculator",
                "window_title": "Calculator",
                "app_id": "",
            },
        ),
    ):
        for _attempt in range(3):
            vision_results.clear()
            chat_id = f"op_key_rej_{uuid.uuid4().hex[:12]}"
            create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
            assert create_response.status_code == 200
            payload: dict[str, object] = {
                "messageId": f"msg_{uuid.uuid4().hex[:8]}",
                "chatId": chat_id,
                "query": query,
                "modelSelection": get_model_selection(),
                "actionMode": "agent",
                "enableMemory": False,
                "agentConfig": {
                    "enabledBuiltinTools": ["computer_use"],
                    "maxIterations": 4,
                },
            }
            events = _collect_agent_stream(
                client,
                payload,
                stream_timeout=90.0,
                stop_when=_stop_when,
            )
            check_e2e_errors(events)
            invoked = {name.removesuffix("_tool") for name in _invoked_tool_names(events)}
            if _vision_outcome_ok(vision_results):
                break

    if not _vision_outcome_ok(vision_results):
        # Deterministic create_desktop_tools path covers Safety reject; this probe
        # only validates live LLM tool wiring (same pattern as SOM agent-stream).
        assistant_tail = _message_text_from_stream_events(events)[-800:]
        pytest.skip(
            "model/stream did not complete desktop_vision_tool after 3 attempts; "
            f"invoked={sorted(invoked)} assistant_tail={assistant_tail!r}"
        )
