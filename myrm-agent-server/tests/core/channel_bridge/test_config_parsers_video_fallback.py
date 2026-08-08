"""Tests for video fallback config parsing and probe engine."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.channel_bridge.config_parsers import (
    _infer_supports_video,
    build_video_fallback_probe_engine_from_providers,
    extract_video_fallback_model_configs,
)
from app.core.types import ModelConfig


def test_infer_supports_video_uses_custom_model_info() -> None:
    providers = {
        "customModelInfo": {
            "openai/gemini-2.5-flash": {"supports_video_input": True},
        }
    }
    assert _infer_supports_video("openai/gemini-2.5-flash", providers) is True


def test_infer_supports_video_defaults_false_without_metadata() -> None:
    assert _infer_supports_video("some-random-model", None) is False
    assert _infer_supports_video("gemini-flash", {"customModelInfo": {}}) is False


def test_extract_video_fallback_model_configs_from_slot() -> None:
    providers_dict: dict[str, object] = {
        "defaultModelConfig": {
            "videoFallbackModel": {
                "providerId": "openai",
                "model": "gpt-4o-mini",
            }
        },
        "providers": [
            {
                "id": "openai",
                "isEnabled": True,
                "providerType": "openai",
                "apiUrl": "https://api.openai.com/v1",
                "apiKey": "sk-video",
                "enabledModels": ["gpt-4o-mini"],
            }
        ],
        "customModelInfo": {
            "openai/gpt-4o-mini": {"supports_video_input": False},
        },
    }
    configs = extract_video_fallback_model_configs(providers_dict)
    assert len(configs) == 1
    assert configs[0].model == "openai/gpt-4o-mini"
    assert configs[0].supports_video is False


def test_build_video_fallback_probe_engine_returns_none_when_unconfigured() -> None:
    assert build_video_fallback_probe_engine_from_providers(None) is None
    assert build_video_fallback_probe_engine_from_providers({"defaultModelConfig": {}}) is None


def test_build_video_fallback_probe_engine_from_video_and_vision_chain() -> None:
    providers_dict: dict[str, object] = {
        "defaultModelConfig": {
            "videoFallbackModel": {
                "providerId": "openai",
                "model": "gpt-4o-mini",
            },
            "visionFallbackModel": {
                "providerId": "openai",
                "model": "gpt-4o",
            },
        },
        "providers": [
            {
                "id": "openai",
                "isEnabled": True,
                "providerType": "openai",
                "apiUrl": "https://api.openai.com/v1",
                "apiKey": "sk-test",
                "enabledModels": ["gpt-4o-mini", "gpt-4o"],
            }
        ],
    }
    engine = build_video_fallback_probe_engine_from_providers(providers_dict)
    assert engine is not None
    assert engine.fallback_configs[0].model == "openai/gpt-4o-mini"
