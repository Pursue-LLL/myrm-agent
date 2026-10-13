"""Privacy resolution through convert_to_general_agent_params.

The web chat sends the privacy settings with every message while protection is on. A client that sends nothing (the
OpenAI-compatible endpoint, an API caller, a web client that has not synced yet) must still get the protection the
persisted settings promise, and what a request does carry must win over them.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.utils import get_model_selection

_PERSISTED_ON = {
    "privacyEnabled": True,
    "privacyS2Action": "warn",
    "privacyS3Action": "block",
    "privacyCustomKeywordsS3": ["Project Falcon"],
    "privacyCustomPatternsS2": [r"EMP-\d{6}"],
}


def _request(**overrides: Any) -> AgentRequest:
    payload: dict[str, Any] = {
        "message_id": "test-msg-privacy-fallback",
        "chat_id": "test-chat-privacy-fallback",
        "query": "Summarize the conversation",
        "model_selection": get_model_selection(),
        "action_mode": "agent",
    }
    payload.update(overrides)
    return AgentRequest(**payload)


async def _convert(request: AgentRequest, personal_settings: dict[str, Any] | None) -> Any:
    configs = _build_mock_user_configs()
    configs.personal_settings_dict = personal_settings
    with patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=configs)):
        params, *_ = await convert_to_general_agent_params(request, [])
    return params


@pytest.mark.asyncio
async def test_a_silent_request_gets_the_persisted_protection() -> None:
    params = await _convert(_request(), _PERSISTED_ON)

    assert params.privacy_enabled is True
    assert (params.privacy_s2_action, params.privacy_s3_action) == ("warn", "block")
    assert params.privacy_custom_keywords_s3 == ["Project Falcon"]
    assert params.privacy_custom_patterns_s2 == [r"EMP-\d{6}"]


@pytest.mark.asyncio
async def test_a_silent_request_with_protection_off_stays_unprotected() -> None:
    params = await _convert(_request(), {"privacyEnabled": False, "privacyS3Action": "block"})

    assert params.privacy_enabled is False
    assert params.privacy_custom_keywords_s3 == []


@pytest.mark.asyncio
async def test_what_the_request_carries_wins_and_missing_rules_come_from_the_settings() -> None:
    request = _request(privacy_enabled=True, privacy_s2_action="redact", privacy_s3_action="redact")

    params = await _convert(request, _PERSISTED_ON)

    assert (params.privacy_s2_action, params.privacy_s3_action) == ("redact", "redact")
    assert params.privacy_custom_keywords_s3 == ["Project Falcon"]


@pytest.mark.asyncio
async def test_request_rules_replace_the_persisted_ones() -> None:
    request = _request(privacy_enabled=True, privacy_custom_keywords_s3=["Only This"])

    params = await _convert(request, _PERSISTED_ON)

    assert params.privacy_custom_keywords_s3 == ["Only This"]


@pytest.mark.asyncio
async def test_a_request_can_enable_protection_the_settings_leave_off() -> None:
    params = await _convert(_request(privacy_enabled=True), None)

    assert params.privacy_enabled is True
    assert (params.privacy_s2_action, params.privacy_s3_action) == ("warn", "redact")


@pytest.mark.asyncio
async def test_a_request_that_only_enables_protection_keeps_the_persisted_actions() -> None:
    params = await _convert(_request(privacy_enabled=True), _PERSISTED_ON)

    assert (params.privacy_s2_action, params.privacy_s3_action) == ("warn", "block")


@pytest.mark.asyncio
async def test_a_request_that_names_one_action_leaves_the_other_to_the_settings() -> None:
    params = await _convert(_request(privacy_enabled=True, privacy_s2_action="pseudonymize"), _PERSISTED_ON)

    assert (params.privacy_s2_action, params.privacy_s3_action) == ("pseudonymize", "block")


@pytest.mark.asyncio
async def test_an_explicit_off_in_the_request_wins_over_the_persisted_protection() -> None:
    params = await _convert(_request(privacy_enabled=False), _PERSISTED_ON)

    assert params.privacy_enabled is False
