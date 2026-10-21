"""The reasoning display mode is the request's choice, else the saved personal setting, else collapsed."""

from __future__ import annotations

import dataclasses
from typing import Literal
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from tests.api.agent.utils import get_model_selection


async def _display_mode(
    *, requested: Literal["off", "collapsed", "inline"] | None, saved: object
) -> Literal["off", "collapsed", "inline"]:
    request = AgentRequest(
        message_id="test-msg-reasoning-mode",
        chat_id="test-chat-reasoning-mode",
        query="hello",
        model_selection=get_model_selection(),
        action_mode="agent",
        reasoning_display_mode=requested,
    )

    from tests.api.agent.conftest import _build_mock_user_configs

    configs = dataclasses.replace(_build_mock_user_configs(), personal_settings_dict={"reasoningDisplayMode": saved})
    with patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=configs)):
        params, *_ = await convert_to_general_agent_params(request, [])
    return params.reasoning_display_mode


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested", "saved", "expected"),
    [
        (None, None, "collapsed"),
        ("inline", "off", "inline"),
        (None, "  Inline ", "inline"),
        (None, "off", "off"),
        (None, "bogus", "collapsed"),
        (None, 3, "collapsed"),
    ],
)
async def test_resolves_request_then_saved_setting_then_default(
    requested: Literal["off", "collapsed", "inline"] | None, saved: object, expected: str
) -> None:
    assert await _display_mode(requested=requested, saved=saved) == expected
