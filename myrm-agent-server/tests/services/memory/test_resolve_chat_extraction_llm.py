"""Tests for chat extraction LLM resolver (factory-aligned SSOT)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.types import ModelConfig


@pytest.mark.asyncio
async def test_resolve_main_model_cfg_applies_agent_override() -> None:
    from app.services.memory.resolve_chat_extraction_llm import _resolve_main_model_cfg

    default_cfg = ModelConfig(model="openai/gpt-4o-mini", api_key="sk-default")
    agent_cfg = ModelConfig(model="openai/gpt-4o", api_key="sk-agent")

    resolved_profile = MagicMock()
    resolved_profile.model = "gpt-4o"
    resolved_profile.model_kwargs = None

    resolver = MagicMock()
    resolver.resolve = AsyncMock(return_value=resolved_profile)

    with (
        patch(
            "app.core.channel_bridge.model_resolver.resolve_model_config",
            side_effect=[default_cfg, agent_cfg],
        ),
        patch(
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=resolver,
        ),
    ):
        result = await _resolve_main_model_cfg("agent-1", {"providers": []}, None)

    assert result.model == agent_cfg.model


@pytest.mark.asyncio
async def test_resolve_chat_extraction_llm_uses_create_agent_llms() -> None:
    from app.services.memory.resolve_chat_extraction_llm import resolve_chat_extraction_llm

    main_llm = object()
    lite_llm = object()
    main_cfg = ModelConfig(model="openai/gpt-4o", api_key="sk-main")
    lite_cfg = ModelConfig(model="openai/gpt-4o-mini", api_key="sk-lite")

    chat_dto = MagicMock()
    chat_dto.agent_id = "agent-abc"

    create_llms = AsyncMock(return_value=(main_llm, lite_llm, None, None))

    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            new=AsyncMock(return_value=chat_dto),
        ),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=MagicMock(providers_dict={"providers": []})),
        ),
        patch(
            "app.services.memory.resolve_chat_extraction_llm._resolve_main_model_cfg",
            new=AsyncMock(return_value=main_cfg),
        ),
        patch(
            "app.services.memory.resolve_chat_extraction_llm._resolve_lite_model_cfg",
            new=AsyncMock(return_value=lite_cfg),
        ),
        patch(
            "app.core.channel_bridge.model_resolver.enrich_model_context_window",
            side_effect=lambda cfg, _providers: cfg,
        ),
        patch(
            "app.ai_agents.general_agent.llm_factory.create_agent_llms",
            new=create_llms,
        ),
        patch(
            "app.ai_agents.general_agent.llm_factory.apply_lite_context_downgrade",
            new=AsyncMock(return_value=lite_llm),
        ),
    ):
        llm, extraction_llm = await resolve_chat_extraction_llm("chat-1")

    create_llms.assert_awaited_once_with(main_cfg, lite_cfg, None, None)
    assert llm is main_llm
    assert extraction_llm is lite_llm


@pytest.mark.asyncio
async def test_apply_lite_context_downgrade_when_lite_too_small() -> None:
    from app.ai_agents.general_agent.llm_factory import apply_lite_context_downgrade

    main_llm = MagicMock()
    lite_llm = MagicMock()
    degraded_llm = MagicMock()
    model_cfg = ModelConfig(model="openai/gpt-4o", api_key="sk-main")

    with (
        patch(
            "myrm_agent_harness.toolkits.llms.utils.model_utils.get_model_context_limit",
            side_effect=[128000, 32000],
        ),
        patch(
            "app.ai_agents.general_agent.llm_factory._inject_low_reasoning_effort",
            return_value=model_cfg,
        ) as inject_mock,
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new=AsyncMock(return_value=degraded_llm),
        ) as get_llm_mock,
    ):
        result = await apply_lite_context_downgrade(main_llm, lite_llm, model_cfg)

    inject_mock.assert_called_once_with(model_cfg)
    get_llm_mock.assert_awaited_once()
    assert result is degraded_llm
