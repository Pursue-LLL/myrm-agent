"""Unit tests for enrich_model_capabilities (supports_vision wiring)."""

from __future__ import annotations

from app.core.channel_bridge.model_resolver import enrich_model_capabilities
from app.core.types import ModelConfig


def _base_cfg() -> ModelConfig:
    return ModelConfig(model="minimax/MiniMax-M2.7", api_key="sk-test")


def test_selection_supports_vision_overrides() -> None:
    cfg = enrich_model_capabilities(_base_cfg(), None, selection_supports_vision=True)
    assert cfg.supports_vision is True


def test_custom_model_info_supports_vision() -> None:
    providers = {
        "customModelInfo": {
            "minimax/MiniMax-M2.7": {"supports_vision": True},
        }
    }
    cfg = enrich_model_capabilities(_base_cfg(), providers)
    assert cfg.supports_vision is True


def test_provider_slash_model_key() -> None:
    providers = {
        "customModelInfo": {
            "openai-like/mimo-v2.5-pro": {"supports_vision": False},
        }
    }
    cfg = ModelConfig(model="openai/mimo-v2.5-pro", api_key="k")
    cfg = enrich_model_capabilities(cfg, providers)
    assert cfg.supports_vision is False
