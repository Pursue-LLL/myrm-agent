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
)
from tests.api.agent.utils import check_e2e_errors, get_model_selection

_VisionAction = Callable[..., Awaitable[str | list[object]]]
_REJECT = "Rejected printable operator"


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_desktop_vision_tool_rejects_star_key_deterministic() -> None:
    """Same tool surface the agent binds: key='*' → Safety reject, no key_press."""
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
        result = await vision.ainvoke({"action": "key", "text": "*"})

    assert isinstance(result, str)
    assert "Safety" in result
    assert _REJECT in result
    assert "REMEDY_HINT" in result
    session.key_press.assert_not_called()


@pytest.mark.e2e
@pytest.mark.timeout(240)
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS computer_use only")
def test_agent_stream_rejects_operator_as_vision_key(
    client: TestClient,
    mock_load_user_configs: AsyncMock,
) -> None:
    """Real LLM: force desktop_vision key='*' and assert Safety via action wrap."""
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
            "maxIterations": 6,
        },
    }

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

    invoked: set[str] = set()
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
        for _attempt in range(2):
            events = _collect_agent_stream(client, payload, stream_timeout=150.0)
            check_e2e_errors(events)
            invoked = {name.removesuffix("_tool") for name in _invoked_tool_names(events)}
            if any(_REJECT in item for item in vision_results):
                break
            payload["messageId"] = f"msg_{uuid.uuid4().hex[:8]}"

    assert "desktop_vision" in invoked, f"vision tool not invoked; tools={invoked}"
    assert vision_results, f"no vision results captured; tools={invoked}"
    joined = "\n".join(vision_results)
    # Two success modes for Lane-C:
    # 1) Model obeyed QA probe with key=* → harness Safety reject (hard path).
    # 2) Model obeyed DESKTOP_CONTROL_RULES and used type instead → soft path.
    # Hard reject without LLM is covered by test_desktop_vision_tool_rejects_star_key_deterministic.
    soft_ok = any(
        "Vision action 'type' completed" in item or 'Vision action "type" completed' in item
        for item in vision_results
    )
    hard_ok = _REJECT in joined
    assert hard_ok or soft_ok, (
        "expected operator-as-key Safety reject or type-instead-of-key; "
        f"results_tail={joined[-2000:]}"
    )
