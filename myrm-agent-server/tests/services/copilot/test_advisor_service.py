"""Unit tests for Session Advisor wire-aware LLM path."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.types import ModelConfig
from app.services.copilot.advisor_service import ask_advisor


def _mock_llm(content: str) -> MagicMock:
    llm = MagicMock()
    response = MagicMock()
    response.content = content
    response.additional_kwargs = {}
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


@pytest.mark.asyncio
async def test_ask_advisor_tier0_status_without_llm() -> None:
    reply, tier = await ask_advisor(
        chat_id="missing-chat",
        question="现在在干嘛？",
        accept_language="zh-CN",
    )
    assert tier == "tier0"
    assert reply


@pytest.mark.asyncio
async def test_ask_advisor_tier1_uses_load_llm_from_model_config() -> None:
    mock_configs = MagicMock()
    mock_configs.providers_dict = {"providers": []}
    mock_configs.model_cfg = ModelConfig(model="openai/gpt-4o-mini", api_key="sk-test")

    with (
        patch(
            "app.services.copilot.advisor_service.load_user_configs",
            new=AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.services.copilot.advisor_service.extract_lite_model_config",
            return_value=None,
        ),
        patch(
            "app.services.copilot.advisor_service.load_llm_from_model_config",
            new=AsyncMock(return_value=_mock_llm("The agent is summarizing files.")),
        ) as load_llm,
    ):
        reply, tier = await ask_advisor(
            chat_id="chat-1",
            question="What is the agent trying to accomplish right now?",
            accept_language="en",
        )

    assert tier == "tier1"
    assert "summarizing" in reply.lower()
    load_llm.assert_awaited_once()
    invoke_cfg = load_llm.await_args.args[0]
    assert invoke_cfg.temperature == 0.2
    assert invoke_cfg.model_kwargs is not None
    assert invoke_cfg.model_kwargs.get("max_tokens") == 256
