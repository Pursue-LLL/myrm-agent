"""Fallback parsers read provider credentials the way the model resolver does.

Provider rows reach the parsers exactly as the WebUI stores them: ``apiKeys`` holds
``{key, isActive}`` entries, and OAuth providers carry an injected ``_oauthToken``.
"""

from __future__ import annotations

from app.core.channel_bridge.config_parsers import (
    extract_fallback_model_configs,
    extract_video_fallback_model_configs,
    extract_vision_fallback_model_config,
)

_SELECTION = {"providerId": "openai", "model": "gpt-4o-mini"}


def _providers_dict(credentials: dict[str, object]) -> dict[str, object]:
    """One enabled provider that backs every fallback slot."""
    return {
        "providers": [
            {
                "id": "openai",
                "isEnabled": True,
                "providerType": "openai",
                "apiUrl": "https://api.openai.com/v1",
                "enabledModels": ["gpt-4o-mini"],
                **credentials,
            }
        ],
        "defaultModelConfig": {
            "baseModel": {"primary": _SELECTION, "fallback": _SELECTION},
            "liteModel": {"primary": _SELECTION, "fallback": _SELECTION},
            "visionFallbackModel": {"primary": _SELECTION},
            "videoFallbackModel": {"primary": _SELECTION},
        },
    }


def _resolved_keys(providers_dict: dict[str, object]) -> list[str | None]:
    """API key of every fallback slot, ``None`` where the slot did not resolve."""
    vision = extract_vision_fallback_model_config(providers_dict)
    video = extract_video_fallback_model_configs(providers_dict)
    base, lite = extract_fallback_model_configs(providers_dict)
    return [
        vision.api_key if vision else None,
        video[0].api_key if video else None,
        base.api_key if base else None,
        lite.api_key if lite else None,
    ]


def test_stored_api_keys_resolve_every_fallback_slot() -> None:
    providers_dict = _providers_dict({"apiKeys": [{"key": "sk-stored", "isActive": True}]})

    assert _resolved_keys(providers_dict) == ["sk-stored"] * 4


def test_inactive_stored_keys_leave_every_fallback_slot_unresolved() -> None:
    providers_dict = _providers_dict({"apiKeys": [{"key": "sk-stored", "isActive": False}]})

    assert _resolved_keys(providers_dict) == [None] * 4


def test_oauth_token_resolves_every_fallback_slot_without_stored_keys() -> None:
    providers_dict = _providers_dict({"_oauthToken": "oauth-token"})

    assert _resolved_keys(providers_dict) == ["oauth-token"] * 4
