"""The follow-up suggestion call masks PII when the persisted privacy switch is on."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.api.agents.suggestions import SuggestionsRequest, get_suggestions

_PHONE = "13812345678"
_PASSWORD = "Sup3rSecret99"


class _CapturingLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        return AIMessage(content='["a", "b", "c"]')


async def _suggest(personal_settings: dict[str, object]) -> str:
    llm = _CapturingLLM()
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
    return llm.prompts[0]


@pytest.mark.asyncio
async def test_privacy_on_masks_the_conversation_sent_to_the_suggestion_model() -> None:
    prompt = await _suggest({"privacyEnabled": True})

    assert _PHONE not in prompt
    assert _PASSWORD not in prompt


@pytest.mark.asyncio
async def test_privacy_off_sends_the_conversation_unchanged() -> None:
    prompt = await _suggest({"privacyEnabled": False})

    assert _PHONE in prompt
