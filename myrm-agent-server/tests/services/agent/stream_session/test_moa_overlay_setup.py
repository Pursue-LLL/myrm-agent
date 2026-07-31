"""Tests for MoA overlay middleware setup (no main-model fallback)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_build_moa_overlay_middleware_disabled() -> None:
    from app.services.agent.stream_session.moa_overlay_setup import build_moa_overlay_middleware

    result = await build_moa_overlay_middleware(None)
    assert result is None

    result = await build_moa_overlay_middleware({"moa_overlay": {"enabled": False}})
    assert result is None


@pytest.mark.asyncio
async def test_build_moa_overlay_middleware_no_refs_returns_none() -> None:
    from app.services.agent.stream_session.moa_overlay_setup import build_moa_overlay_middleware

    with patch(
        "app.services.agent.stream_session.moa_overlay_setup.resolve_moa_overlay_models",
        new_callable=AsyncMock,
        return_value=({"enabled": True}, []),
    ):
        result = await build_moa_overlay_middleware({"moa_overlay": {"enabled": True}})
    assert result is None


@pytest.mark.asyncio
async def test_build_moa_overlay_middleware_skips_failed_llm_creation() -> None:
    from app.services.agent.stream_session.moa_overlay_setup import build_moa_overlay_middleware

    mock_cfg = MagicMock(model="ref-a", api_keys=None)
    with patch(
        "app.services.agent.stream_session.moa_overlay_setup.resolve_moa_overlay_models",
        new_callable=AsyncMock,
        return_value=({"enabled": True, "fanout": "user_turn"}, [mock_cfg]),
    ):
        with patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new_callable=AsyncMock,
            side_effect=RuntimeError("bad key"),
        ):
            result = await build_moa_overlay_middleware({"moa_overlay": {"enabled": True}})
    assert result is None


@pytest.mark.asyncio
async def test_build_moa_overlay_middleware_creates_middleware() -> None:
    from app.services.agent.stream_session.moa_overlay_setup import build_moa_overlay_middleware

    mock_cfg = MagicMock(model="ref-a", api_keys=None)
    mock_llm = MagicMock()
    overlay_raw = {
        "enabled": True,
        "fanout": "user_turn",
        "privacy_filter": "display",
        "reference_model_selections": [],
    }
    with patch(
        "app.services.agent.stream_session.moa_overlay_setup.resolve_moa_overlay_models",
        new_callable=AsyncMock,
        return_value=(overlay_raw, [mock_cfg]),
    ):
        with patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ):
            result = await build_moa_overlay_middleware({"moa_overlay": overlay_raw})
    assert result is not None
