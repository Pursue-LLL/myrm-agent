"""Tests verifying compact paths use real model context window instead of hardcoded 128k."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_llm_for_user_returns_real_window():
    """_get_llm_for_user returns the model's actual max_context_tokens."""
    mock_model_cfg = MagicMock()
    mock_model_cfg.max_context_tokens = 32000
    mock_model_cfg.api_keys = None

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
        from app.services.chat.compact_service import _get_llm_for_user

        llm, max_tokens = await _get_llm_for_user()

        assert llm is mock_llm
        assert max_tokens == 32000


@pytest.mark.asyncio
async def test_get_llm_for_user_fallback_128k_when_none():
    """_get_llm_for_user falls back to 128000 when max_context_tokens is None."""
    mock_model_cfg = MagicMock()
    mock_model_cfg.max_context_tokens = None
    mock_model_cfg.api_keys = None

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
        from app.services.chat.compact_service import _get_llm_for_user

        _, max_tokens = await _get_llm_for_user()

        assert max_tokens == 128000


@pytest.mark.asyncio
async def test_guarded_compact_summarize_passes_config():
    """_guarded_compact_summarize passes ContextConfig with correct max_context_tokens."""
    from myrm_agent_harness.agent.context_management.infra.schemas import (
        ContextConfig,
        StructuredSummary,
    )

    captured_config: list[ContextConfig | None] = []

    async def fake_generate(
        messages, llm, chat_id, existing_summary=None, focus_topic="", progress_tracker=None, config=None
    ):
        captured_config.append(config)
        return messages, StructuredSummary(
            user_goal="test",
            completed_actions=[],
            key_findings=[],
            files_modified=[],
            last_action="",
        )

    with patch(
        "myrm_agent_harness.agent.context_management.strategies.summarizer.generate_structured_summary",
        side_effect=fake_generate,
    ):
        from app.services.chat.compact_service import _guarded_compact_summarize

        mock_llm = AsyncMock()
        await _guarded_compact_summarize(
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
