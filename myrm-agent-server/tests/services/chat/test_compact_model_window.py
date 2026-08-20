"""Tests verifying compact paths use real model context window instead of hardcoded 128k.

Covers:
- Normal path: real window returned (32k, 64k, 200k)
- Fallback path: None → 128000
- Config propagation: max_context_tokens passed to generate_structured_summary
- Edge case: zero value treated as falsy → fallback
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_llm_for_user_returns_real_window():
    """_get_llm_for_user returns the model's actual max_context_tokens."""
    from app.core.types import ModelConfig

    mock_model_cfg = ModelConfig(model="openai/gpt-4o", api_key="test-key", max_context_tokens=32000)

    mock_configs = MagicMock()
    mock_configs.model_cfg = mock_model_cfg

    mock_llm = AsyncMock()

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_configs,
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
    ):
        from app.services.chat.compact.llm_config import get_llm_for_user

        llm, max_tokens = await get_llm_for_user()

        assert llm is mock_llm
        assert max_tokens == 32000


@pytest.mark.asyncio
async def test_get_llm_for_user_fallback_128k_when_none():
    """_get_llm_for_user falls back to 128000 when max_context_tokens is None."""
    from app.core.types import ModelConfig

    mock_model_cfg = ModelConfig(model="openai/gpt-4o", api_key="test-key")

    mock_configs = MagicMock()
    mock_configs.model_cfg = mock_model_cfg

    mock_llm = AsyncMock()

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_configs,
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
    ):
        from app.services.chat.compact.llm_config import get_llm_for_user

        _, max_tokens = await get_llm_for_user()

        assert max_tokens == 128000


@pytest.mark.asyncio
async def test_get_llm_for_user_normalizes_legacy_prefix():
    """Legacy ``openai-like/xxx`` default_model must be converged to ``openai/xxx``."""
    from app.core.types import ModelConfig

    mock_model_cfg = ModelConfig(
        model="openai-like/agnes-2.5-flash",
        api_key="test-key",
        max_context_tokens=32000,
    )

    mock_configs = MagicMock()
    mock_configs.model_cfg = mock_model_cfg

    mock_llm = AsyncMock()
    mock_get_llm = AsyncMock(return_value=mock_llm)

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_configs,
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new=mock_get_llm,
        ),
    ):
        from app.services.chat.compact.llm_config import get_llm_for_user

        llm, max_tokens = await get_llm_for_user()

        assert llm is mock_llm
        assert max_tokens == 32000
        passed_cfg = mock_get_llm.call_args.args[0]
        assert passed_cfg.model == "openai/agnes-2.5-flash"


@pytest.mark.asyncio
async def test_guarded_compact_summarize_passes_config():
    """_guarded_compact_summarize passes ContextConfig with correct max_context_tokens."""
    from myrm_agent_harness.agent.context_management.infra.schemas import (
        ContextConfig,
        StructuredSummary,
    )

    captured_config: list[ContextConfig | None] = []

    async def fake_generate(messages, llm, chat_id, existing_summary=None, focus_topic="", progress_tracker=None, config=None):
        captured_config.append(config)
        return messages, StructuredSummary(
            user_goal="test",
            completed_actions=[],
            key_findings=[],
            files_modified=[],
            last_action="",
        )

    with patch(
        "myrm_agent_harness.agent.context_management.strategies.summary.summarizer.generate_structured_summary",
        side_effect=fake_generate,
    ):
        from app.services.chat.compact.summarize_guard import guarded_compact_summarize

        mock_llm = AsyncMock()
        await guarded_compact_summarize(
            lc_messages=[],
            llm=mock_llm,
            chat_id="test-chat",
            existing_summary=None,
            focus_topic="",
            max_context_tokens=64000,
        )

        assert len(captured_config) == 1
        assert captured_config[0] is not None
        assert captured_config[0].max_context_tokens == 64000


@pytest.mark.asyncio
async def test_get_llm_for_user_large_window_200k():
    """_get_llm_for_user correctly returns large windows like Gemini 1M or Claude 200k."""
    from app.core.types import ModelConfig

    mock_model_cfg = ModelConfig(model="openai/gpt-4o", api_key="test-key", max_context_tokens=200000)

    mock_configs = MagicMock()
    mock_configs.model_cfg = mock_model_cfg

    mock_llm = AsyncMock()

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_configs,
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
    ):
        from app.services.chat.compact.llm_config import get_llm_for_user

        _, max_tokens = await get_llm_for_user()

        assert max_tokens == 200000


@pytest.mark.asyncio
async def test_get_llm_for_user_zero_treated_as_falsy():
    """max_context_tokens=0 is treated as falsy and falls back to 128000."""
    from app.core.types import ModelConfig

    mock_model_cfg = ModelConfig(model="openai/gpt-4o", api_key="test-key", max_context_tokens=0)

    mock_configs = MagicMock()
    mock_configs.model_cfg = mock_model_cfg

    mock_llm = AsyncMock()

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_configs,
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
    ):
        from app.services.chat.compact.llm_config import get_llm_for_user

        _, max_tokens = await get_llm_for_user()

        assert max_tokens == 128000


@pytest.mark.asyncio
async def test_guarded_compact_summarize_default_128k():
    """Without explicit max_context_tokens, defaults to 128000."""
    from myrm_agent_harness.agent.context_management.infra.schemas import (
        ContextConfig,
        StructuredSummary,
    )

    captured_config: list[ContextConfig | None] = []

    async def fake_generate(messages, llm, chat_id, existing_summary=None, focus_topic="", progress_tracker=None, config=None):
        captured_config.append(config)
        return messages, StructuredSummary(
            user_goal="test",
            completed_actions=[],
            key_findings=[],
            files_modified=[],
            last_action="",
        )

    with patch(
        "myrm_agent_harness.agent.context_management.strategies.summary.summarizer.generate_structured_summary",
        side_effect=fake_generate,
    ):
        from app.services.chat.compact.summarize_guard import guarded_compact_summarize

        mock_llm = AsyncMock()
        await guarded_compact_summarize(
            lc_messages=[],
            llm=mock_llm,
            chat_id="test-chat",
            existing_summary=None,
            focus_topic="",
        )

        assert len(captured_config) == 1
        assert captured_config[0] is not None
        assert captured_config[0].max_context_tokens == 128000
