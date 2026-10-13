"""The follow-up suggestion call is covered by the persisted privacy settings."""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.security.outbound_privacy_guard import set_process_privacy_policy
from myrm_agent_harness.toolkits.llms.adapters.chat_model.outbound_guard import set_outbound_message_guard

from app.api.agents.suggestions import SuggestionsRequest, get_suggestions
from app.core.security.privacy_policy_sync import sync_privacy_policy
from tests.support.privacy_wire import wire_llm

_PHONE = "13812345678"
_PASSWORD = "Sup3rSecret99"


@pytest.fixture(autouse=True)
def _clean_process_policy() -> Iterator[None]:
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)
    yield
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)


async def _suggest(personal_settings: dict[str, object]) -> str:
    sync_privacy_policy(personal_settings)
    llm, sent = wire_llm('["a", "b", "c"]')
    configs = SimpleNamespace(
        providers_dict={"providers": []},
        model_cfg=None,
        personal_settings_dict=personal_settings,
    )
    request = SuggestionsRequest(chat_history=[["user", f"手机 {_PHONE}，password: {_PASSWORD}"], ["assistant", "好的"]])
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", new=AsyncMock(return_value=configs)),
        patch("app.api.agents.suggestions._resolve_lite_model", new=lambda *_args: SimpleNamespace(api_keys=None)),
        patch("myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config", new=AsyncMock(return_value=llm)),
    ):
        response = await get_suggestions.__wrapped__(request=request, http_request=MagicMock())

    assert json.loads(response.body)["data"]["suggestions"] == ["a", "b", "c"]
    return "\n".join(sent)


@pytest.mark.asyncio
async def test_privacy_on_masks_the_conversation_sent_to_the_suggestion_model() -> None:
    prompt = await _suggest({"privacyEnabled": True})

    assert _PHONE not in prompt
    assert _PASSWORD not in prompt


@pytest.mark.asyncio
async def test_privacy_off_sends_the_conversation_unchanged() -> None:
    prompt = await _suggest({"privacyEnabled": False})

    assert _PHONE in prompt
