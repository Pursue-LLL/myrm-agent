"""End-to-end tests for credential pool strategy configuration.

Verifies the complete flow: frontend ModelSelection → Server resolver
→ Harness LLMManager → CredentialPool with correct strategy.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.toolkits.llms.core.credential_pool import CredentialPoolStrategy
from myrm_agent_harness.toolkits.llms.core.manager import LLMManager

from app.services.agent.params.models import ModelSelection
from app.services.agent.params.resolvers import _resolve_model_config


@pytest.fixture(autouse=True)
def _clear_llm_cache() -> None:
    """Clear LLM cache before and after each test."""
    LLMManager.clear_cache()
    yield
    LLMManager.clear_cache()


def _mock_litellm_model(*, api_key: str, **kwargs: object) -> MagicMock:
    """Create a mock LiteLLM model for testing."""
    model = MagicMock()
    model.model = f"model-{api_key}"
    model._agenerate = MagicMock(return_value=MagicMock())
    return model


@pytest.fixture
def mock_providers() -> dict[str, object]:
    """Mock provider configuration with multiple API keys."""
    return {
        "providers": [
            {
                "id": "openai",
                "providerType": "openai",
                "isEnabled": True,
                "apiKeys": [
                    {"isActive": True, "key": "sk-test-key-1"},
                    {"isActive": True, "key": "sk-test-key-2"},
                    {"isActive": True, "key": "sk-test-key-3"},
                ],
            }
        ]
    }


@pytest.mark.asyncio
async def test_strategy_from_frontend_to_harness_fill_first(
    mock_providers: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test FILL_FIRST strategy flows from frontend to Harness pool."""
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.llms.core.manager.create_litellm_model",
        _mock_litellm_model,
    )

    # Frontend sends ModelSelection with fill_first strategy
    selection = ModelSelection(
        provider_id="openai",
        model="gpt-4",
        credential_pool_strategy="fill_first",
    )

    # Resolve to ModelConfig (Server layer)
    model_config = await _resolve_model_config(selection, mock_providers)
    assert model_config.credential_pool_strategy == "fill_first"
    assert model_config.api_keys == ["sk-test-key-1", "sk-test-key-2", "sk-test-key-3"]

    # Create LLM instance (Harness layer)
    llm = await LLMManager.get_llm_from_config(model_config, streaming=False)

    # Verify pool strategy is correctly set
    assert hasattr(llm, "credential_pool")
    assert llm.credential_pool.strategy == CredentialPoolStrategy.FILL_FIRST


@pytest.mark.asyncio
async def test_strategy_from_frontend_to_harness_least_used(
    mock_providers: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test LEAST_USED strategy flows from frontend to Harness pool."""
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.llms.core.manager.create_litellm_model",
        _mock_litellm_model,
    )

    selection = ModelSelection(
        provider_id="openai",
        model="gpt-4",
        credential_pool_strategy="least_used",
    )

    model_config = await _resolve_model_config(selection, mock_providers)
    assert model_config.credential_pool_strategy == "least_used"

    llm = await LLMManager.get_llm_from_config(model_config, streaming=False)
    assert llm.credential_pool.strategy == CredentialPoolStrategy.LEAST_USED


@pytest.mark.asyncio
async def test_strategy_defaults_to_round_robin_when_omitted(
    mock_providers: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test default ROUND_ROBIN strategy when frontend doesn't specify."""
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.llms.core.manager.create_litellm_model",
        _mock_litellm_model,
    )

    selection = ModelSelection(
        provider_id="openai",
        model="gpt-4",
        # No credential_pool_strategy specified
    )

    model_config = await _resolve_model_config(selection, mock_providers)
    assert model_config.credential_pool_strategy is None

    llm = await LLMManager.get_llm_from_config(model_config, streaming=False)
    # Should default to ROUND_ROBIN
    assert llm.credential_pool.strategy == CredentialPoolStrategy.ROUND_ROBIN


@pytest.mark.asyncio
async def test_strategy_case_insensitive_normalization(
    mock_providers: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test strategy normalization handles various case formats."""
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.llms.core.manager.create_litellm_model",
        _mock_litellm_model,
    )

    # Frontend sends uppercase with underscores
    selection = ModelSelection(
        provider_id="openai",
        model="gpt-4",
        credential_pool_strategy="FILL_FIRST",
    )

    model_config = await _resolve_model_config(selection, mock_providers)
    llm = await LLMManager.get_llm_from_config(model_config, streaming=False)
    assert llm.credential_pool.strategy == CredentialPoolStrategy.FILL_FIRST


@pytest.mark.asyncio
async def test_invalid_strategy_raises_error(
    mock_providers: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test invalid strategy raises descriptive error."""
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.llms.core.manager.create_litellm_model",
        _mock_litellm_model,
    )

    selection = ModelSelection(
        provider_id="openai",
        model="gpt-4",
        credential_pool_strategy="invalid_strategy",
    )

    model_config = await _resolve_model_config(selection, mock_providers)

    with pytest.raises(ValueError, match="Unsupported credential pool strategy"):
        await LLMManager.get_llm_from_config(model_config, streaming=False)


@pytest.mark.asyncio
async def test_single_key_always_uses_round_robin(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test single-key pool defaults to ROUND_ROBIN regardless of frontend choice."""
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.llms.core.manager.create_litellm_model",
        _mock_litellm_model,
    )

    providers = {
        "providers": [
            {
                "id": "openai",
                "providerType": "openai",
                "isEnabled": True,
                "apiKeys": [
                    {"isActive": True, "key": "sk-single-key"},
                ],
            }
        ]
    }

    selection = ModelSelection(
        provider_id="openai",
        model="gpt-4",
        credential_pool_strategy="fill_first",  # User requests fill_first
    )

    model_config = await _resolve_model_config(selection, providers)
    # Should create single-key LLM, not pooled
    llm = await LLMManager.get_llm_from_config(model_config, streaming=False)
    # Verify single-key mode: api_keys should be None
    assert model_config.api_keys is None
    # Single-key LLM should not be a KeyPoolLLM (checked by type name)
    assert llm.__class__.__name__ != "KeyPoolLLM"


@pytest.mark.asyncio
async def test_strategy_affects_cache_key(
    mock_providers: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test different strategies result in different cached instances."""
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.llms.core.manager.create_litellm_model",
        _mock_litellm_model,
    )

    # Create two selections with different strategies
    selection_fill_first = ModelSelection(
        provider_id="openai",
        model="gpt-4",
        credential_pool_strategy="fill_first",
    )
    selection_least_used = ModelSelection(
        provider_id="openai",
        model="gpt-4",
        credential_pool_strategy="least_used",
    )

    config1 = await _resolve_model_config(selection_fill_first, mock_providers)
    config2 = await _resolve_model_config(selection_least_used, mock_providers)

    llm1 = await LLMManager.get_llm_from_config(config1, streaming=False)
    llm2 = await LLMManager.get_llm_from_config(config2, streaming=False)

    # Different strategies should result in different instances
    assert llm1 is not llm2
    assert llm1.credential_pool.strategy == CredentialPoolStrategy.FILL_FIRST
    assert llm2.credential_pool.strategy == CredentialPoolStrategy.LEAST_USED
