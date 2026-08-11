from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models import BaseChatModel

from app.ai_agents.general_agent.llm_factory import (
    apply_lite_context_downgrade,
    apply_lite_managed_fallback,
    create_agent_llms,
)
from app.core.types import ModelConfig
from myrm_agent_harness.toolkits.llms.fallback import ManagedLLM


def _cfg(model: str) -> ModelConfig:
    return ModelConfig(model=model, api_key="test-key")


@pytest.mark.asyncio
async def test_create_agent_llms_returns_stream_fallback_when_managed() -> None:
    main_cfg = _cfg("openai/main-model")
    fallback_cfg = _cfg("openai/fallback-model")
    mock_main = MagicMock(spec=BaseChatModel)
    mock_fallback = MagicMock(spec=BaseChatModel)
    mock_lite = MagicMock(spec=BaseChatModel)

    with patch(
        "app.ai_agents.general_agent.llm_factory.llm_manager.get_llm_from_config",
        new_callable=AsyncMock,
    ) as get_llm:
        get_llm.side_effect = [mock_main, mock_lite, mock_fallback]

        main_llm, lite_llm, stream_fallback, safety = await create_agent_llms(
            main_cfg,
            main_cfg,
            fallback_cfg,
            None,
        )

    assert isinstance(main_llm, ManagedLLM)
    assert lite_llm is mock_lite
    assert stream_fallback is mock_fallback
    assert safety is None


@pytest.mark.asyncio
async def test_create_agent_llms_no_fallback_returns_none_stream_slot() -> None:
    main_cfg = _cfg("openai/main-model")
    mock_main = MagicMock(spec=BaseChatModel)
    mock_lite = MagicMock(spec=BaseChatModel)

    with patch(
        "app.ai_agents.general_agent.llm_factory.llm_manager.get_llm_from_config",
        new_callable=AsyncMock,
    ) as get_llm:
        get_llm.side_effect = [mock_main, mock_lite]

        main_llm, _lite, stream_fallback, _safety = await create_agent_llms(
            main_cfg,
            main_cfg,
            None,
            None,
        )

    assert main_llm is mock_main
    assert stream_fallback is None


@pytest.mark.asyncio
async def test_apply_lite_managed_fallback_wraps_when_configured() -> None:
    lite_cfg = _cfg("openai/lite-model")
    fallback_cfg = _cfg("openai/lite-fallback")
    mock_lite = MagicMock(spec=BaseChatModel)
    mock_fallback = MagicMock(spec=BaseChatModel)

    with patch(
        "app.ai_agents.general_agent.llm_factory.llm_manager.get_llm_from_config",
        new_callable=AsyncMock,
        return_value=mock_fallback,
    ):
        wrapped = await apply_lite_managed_fallback(mock_lite, lite_cfg, fallback_cfg)

    assert isinstance(wrapped, ManagedLLM)


@pytest.mark.asyncio
async def test_apply_lite_managed_fallback_passthrough_when_unconfigured() -> None:
    mock_lite = MagicMock(spec=BaseChatModel)
    lite_cfg = _cfg("openai/lite-model")

    result = await apply_lite_managed_fallback(mock_lite, lite_cfg, None)
    assert result is mock_lite


@pytest.mark.asyncio
async def test_apply_lite_context_downgrade_returns_main_cfg_when_degraded() -> None:
    main_llm = MagicMock(spec=BaseChatModel)
    lite_llm = MagicMock(spec=BaseChatModel)
    degraded_llm = MagicMock(spec=BaseChatModel)
    main_cfg = _cfg("openai/main-model")
    lite_cfg = _cfg("openai/lite-model")

    with (
        patch(
            "myrm_agent_harness.toolkits.llms.utils.model_utils.get_model_context_limit",
            side_effect=[128000, 32000],
        ),
        patch(
            "app.ai_agents.general_agent.llm_factory.llm_manager.get_llm_from_config",
            new_callable=AsyncMock,
            return_value=degraded_llm,
        ),
    ):
        result_llm, effective_cfg = await apply_lite_context_downgrade(
            main_llm, lite_llm, main_cfg, lite_cfg
        )

    assert result_llm is degraded_llm
    assert effective_cfg.model == main_cfg.model


@pytest.mark.asyncio
async def test_apply_lite_managed_fallback_uses_effective_cfg_after_downgrade() -> None:
    main_cfg = _cfg("openai/main-model")
    lite_cfg = _cfg("openai/lite-model")
    fallback_cfg = _cfg("openai/lite-fallback")
    degraded_llm = MagicMock(spec=BaseChatModel)
    mock_fallback = MagicMock(spec=BaseChatModel)

    with patch(
        "app.ai_agents.general_agent.llm_factory.llm_manager.get_llm_from_config",
        new_callable=AsyncMock,
        return_value=mock_fallback,
    ):
        wrapped = await apply_lite_managed_fallback(
            degraded_llm, main_cfg, fallback_cfg
        )

    assert isinstance(wrapped, ManagedLLM)
    assert wrapped._main_model_name == main_cfg.model
