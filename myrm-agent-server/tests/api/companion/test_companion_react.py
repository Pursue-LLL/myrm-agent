"""Unit tests for companion /react wire-aware LLM path."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.types import ModelConfig
from tests.support.minimal_app import build_minimal_app


@pytest.fixture
def companion_app():
    return build_minimal_app(preset="companion")


@pytest.mark.asyncio
async def test_companion_react_uses_load_llm_from_model_config(companion_app) -> None:
    from myrm_agent_harness.core.features import init_features

    from app.services.features.registration import register_all_features

    register_all_features()
    init_features(overrides={"companion_mode": True})

    mock_configs = MagicMock()
    mock_configs.providers_dict = {"providers": []}
    mock_configs.model_cfg = ModelConfig(model="openai/gpt-4o-mini", api_key="sk-test")

    mock_llm = MagicMock()
    response = MagicMock()
    response.content = "Nice work!"
    response.additional_kwargs = {}
    mock_llm.ainvoke = AsyncMock(return_value=response)

    with (
        patch(
            "app.api.companion.router.load_user_configs",
            new=AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.api.companion.router.extract_lite_model_config",
            return_value=None,
        ),
        patch(
            "app.api.companion.router.load_llm_from_model_config",
            new=AsyncMock(return_value=mock_llm),
        ) as load_llm,
    ):
        async with AsyncClient(transport=ASGITransport(app=companion_app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/companion/react",
                json={
                    "snippet": "I finished the summary.",
                    "personality": "cheerful",
                    "name": "Ferris",
                    "species": "crab",
                },
            )

    assert resp.status_code == 200
    assert resp.json()["reaction"] == "Nice work!"
    load_llm.assert_awaited_once()
    invoke_cfg = load_llm.await_args.args[0]
    assert invoke_cfg.temperature == 0.9
    assert invoke_cfg.model_kwargs is not None
    assert invoke_cfg.model_kwargs.get("max_tokens") == 30
