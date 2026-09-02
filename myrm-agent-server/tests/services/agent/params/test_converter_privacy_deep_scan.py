"""privacy_deep_scan resolution through convert_to_general_agent_params.

The WebUI only sends the field when the toggle is touched, so the converter must
fall back to the persisted personalSettings (privacyDeepScan) and never silently
re-enable an explicitly disabled scan.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.utils import get_model_selection


def _build_request(**overrides: Any) -> AgentRequest:
    payload: dict[str, Any] = {
        "message_id": "test-msg-privacy-deep-scan",
        "chat_id": "test-chat-privacy-deep-scan",
        "query": "Summarize the conversation",
        "model_selection": get_model_selection(),
        "action_mode": "agent",
    }
    payload.update(overrides)
    return AgentRequest(**payload)


def _mock_configs(personal_settings: dict[str, Any] | None) -> Any:
    configs = _build_mock_user_configs()
    configs.personal_settings_dict = personal_settings
    return configs


@pytest.mark.asyncio
async def test_request_explicit_false_overrides_persisted_true() -> None:
    """Explicit request value must win over the persisted setting."""
    request = _build_request(privacy_deep_scan=False)
    mock_configs = _mock_configs({"privacyDeepScan": True})

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=mock_configs),
    ):
        params, *rest = await convert_to_general_agent_params(request, [])

    assert params.privacy_deep_scan is False


@pytest.mark.asyncio
async def test_request_unspecified_falls_back_to_persisted_true() -> None:
    """Unspecified request must pick up the persisted privacyDeepScan=True."""
    request = _build_request()
    mock_configs = _mock_configs({"privacyDeepScan": True})

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=mock_configs),
    ):
        params, *rest = await convert_to_general_agent_params(request, [])

    assert params.privacy_deep_scan is True


@pytest.mark.asyncio
async def test_request_unspecified_and_no_persisted_setting_defaults_false() -> None:
    """No setting anywhere must resolve to deep scan disabled."""
    request = _build_request()
    mock_configs = _mock_configs(None)

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=mock_configs),
    ):
        params, *rest = await convert_to_general_agent_params(request, [])

    assert params.privacy_deep_scan is False


@pytest.mark.asyncio
async def test_request_unspecified_and_persisted_false_stays_false() -> None:
    """Persisted False must not flip to True."""
    request = _build_request()
    mock_configs = _mock_configs({"privacyDeepScan": False})

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=mock_configs),
    ):
        params, *rest = await convert_to_general_agent_params(request, [])

    assert params.privacy_deep_scan is False
