"""Tests for session-level MoA preset activation."""

from __future__ import annotations

from app.services.agent.moa_preset_resolver import (
    MOA_PRESET_DEFAULT_ID,
    MOA_PRESET_FAST_ID,
    MOA_PRESET_REVIEW_ID,
    apply_moa_preset_activation,
    is_moa_preset_configured,
    resolve_effective_moa_preset_id,
)


def _sample_engine_params(*, overlay_enabled: bool = True) -> dict[str, object]:
    return {
        "moa_overlay": {
            "enabled": overlay_enabled,
            "reference_model_selections": [
                {"providerId": "openai", "model": "gpt-4o-mini"},
            ],
            "fanout": "user_turn",
        },
    }


def test_is_moa_preset_configured_requires_enabled_and_refs() -> None:
    assert is_moa_preset_configured(_sample_engine_params()) is True
    assert is_moa_preset_configured(_sample_engine_params(overlay_enabled=False)) is False
    assert is_moa_preset_configured({"moa_overlay": {"enabled": True}}) is False
    assert is_moa_preset_configured(None) is False


def test_apply_activation_enables_overlay_for_default_preset() -> None:
    result = apply_moa_preset_activation(_sample_engine_params(), MOA_PRESET_DEFAULT_ID)
    assert result is not None
    overlay = result["moa_overlay"]
    assert isinstance(overlay, dict)
    assert overlay["enabled"] is True


def test_apply_activation_disables_when_preset_not_selected() -> None:
    result = apply_moa_preset_activation(_sample_engine_params(), None)
    assert result is not None
    overlay = result["moa_overlay"]
    assert isinstance(overlay, dict)
    assert overlay["enabled"] is False


def test_apply_activation_accepts_review_and_fast_presets() -> None:
    for preset_id in (MOA_PRESET_REVIEW_ID, MOA_PRESET_FAST_ID):
        result = apply_moa_preset_activation(_sample_engine_params(), preset_id)
        assert result is not None
        overlay = result["moa_overlay"]
        assert isinstance(overlay, dict)
        assert overlay["enabled"] is True

    review = apply_moa_preset_activation(_sample_engine_params(), MOA_PRESET_REVIEW_ID)
    assert review is not None
    review_overlay = review["moa_overlay"]
    assert isinstance(review_overlay, dict)
    assert review_overlay["reference_reasoning_effort"] == "high"

    fast = apply_moa_preset_activation(_sample_engine_params(), MOA_PRESET_FAST_ID)
    assert fast is not None
    fast_overlay = fast["moa_overlay"]
    assert isinstance(fast_overlay, dict)
    assert fast_overlay["reference_max_tokens"] == 600
    assert fast_overlay["reference_reasoning_effort"] == "low"


def test_apply_activation_ignores_unknown_preset_id() -> None:
    result = apply_moa_preset_activation(_sample_engine_params(), "unknown")
    assert result is not None
    overlay = result["moa_overlay"]
    assert isinstance(overlay, dict)
    assert overlay["enabled"] is False


def test_apply_activation_uses_preset_specific_refs() -> None:
    params = {
        "moa_overlay": {
            "enabled": True,
            "reference_model_selections": [
                {"providerId": "openai", "model": "gpt-4o-mini"},
            ],
            "presets": {
                MOA_PRESET_REVIEW_ID: {
                    "reference_model_selections": [
                        {"providerId": "anthropic", "model": "claude-3-5-sonnet"},
                    ],
                },
            },
        },
    }
    result = apply_moa_preset_activation(params, MOA_PRESET_REVIEW_ID)
    assert result is not None
    overlay = result["moa_overlay"]
    assert isinstance(overlay, dict)
    refs = overlay["reference_model_selections"]
    assert isinstance(refs, list)
    assert refs[0]["model"] == "claude-3-5-sonnet"
    assert overlay["reference_reasoning_effort"] == "high"


def test_is_moa_preset_configured_with_preset_only_refs() -> None:
    params = {
        "moa_overlay": {
            "enabled": True,
            "presets": {
                MOA_PRESET_FAST_ID: {
                    "reference_model_selections": [
                        {"providerId": "openai", "model": "gpt-4o-mini"},
                    ],
                },
            },
        },
    }
    assert is_moa_preset_configured(params) is True


def test_apply_activation_no_op_without_overlay_block() -> None:
    assert apply_moa_preset_activation({"consensus": {"enabled": True}}, MOA_PRESET_DEFAULT_ID) == {
        "consensus": {"enabled": True},
    }


def test_resolve_preset_refs_strict_when_presets_key_exists() -> None:
    from app.services.agent.moa_preset_resolver import (
        resolve_preset_reference_selections,
    )

    overlay = {
        "reference_model_selections": [
            {"providerId": "openai", "model": "gpt-4o"},
        ],
        "presets": {
            MOA_PRESET_FAST_ID: {"reference_model_selections": []},
            MOA_PRESET_REVIEW_ID: {
                "reference_model_selections": [
                    {"providerId": "anthropic", "model": "claude-3-5-sonnet"},
                ],
            },
        },
    }
    assert resolve_preset_reference_selections(overlay, MOA_PRESET_FAST_ID) == []
    review_refs = resolve_preset_reference_selections(overlay, MOA_PRESET_REVIEW_ID)
    assert isinstance(review_refs, list)
    assert review_refs[0]["model"] == "claude-3-5-sonnet"


def test_apply_activation_clears_top_level_refs_for_empty_preset() -> None:
    params = {
        "moa_overlay": {
            "enabled": True,
            "reference_model_selections": [
                {"providerId": "openai", "model": "gpt-4o"},
            ],
            "presets": {
                MOA_PRESET_FAST_ID: {"reference_model_selections": []},
            },
        },
    }
    result = apply_moa_preset_activation(params, MOA_PRESET_FAST_ID)
    assert result is not None
    overlay = result["moa_overlay"]
    assert isinstance(overlay, dict)
    assert overlay["enabled"] is True
    assert overlay["reference_model_selections"] == []


def test_is_moa_preset_configured_strict_when_presets_key_exists() -> None:
    params = {
        "moa_overlay": {
            "enabled": True,
            "reference_model_selections": [
                {"providerId": "openai", "model": "gpt-4o-mini"},
            ],
            "presets": {
                MOA_PRESET_DEFAULT_ID: {"reference_model_selections": []},
                MOA_PRESET_REVIEW_ID: {"reference_model_selections": []},
                MOA_PRESET_FAST_ID: {"reference_model_selections": []},
            },
        },
    }
    assert is_moa_preset_configured(params) is False


def test_resolve_effective_moa_preset_explicit_takes_precedence() -> None:
    params = _sample_engine_params()
    # Explicit request should be honored regardless of routing tier or auto flags
    assert (
        resolve_effective_moa_preset_id(
            engine_params=params,
            requested_preset_id=MOA_PRESET_FAST_ID,
            routing_tier="simple",
            auto_moa_reasoning=False,
        )
        == MOA_PRESET_FAST_ID
    )


def test_resolve_effective_moa_preset_auto_on_reasoning_tier() -> None:
    params = _sample_engine_params()
    # Reasoning tier with auto_moa_reasoning enabled activates default/review preset
    assert (
        resolve_effective_moa_preset_id(
            engine_params=params,
            requested_preset_id=None,
            routing_tier="reasoning",
            auto_moa_reasoning=True,
        )
        == MOA_PRESET_REVIEW_ID
    )
    # Simple or standard tier does not activate
    assert (
        resolve_effective_moa_preset_id(
            engine_params=params,
            requested_preset_id=None,
            routing_tier="simple",
            auto_moa_reasoning=True,
        )
        is None
    )
    assert (
        resolve_effective_moa_preset_id(
            engine_params=params,
            requested_preset_id=None,
            routing_tier="standard",
            auto_moa_reasoning=True,
        )
        is None
    )


def test_resolve_effective_moa_preset_agent_profile_override() -> None:
    params = {
        "moa_overlay": {
            "enabled": True,
            "auto_on_reasoning": True,
            "reference_model_selections": [
                {"providerId": "openai", "model": "gpt-4o"},
            ],
        },
    }
    # Profile has auto_on_reasoning: True, even if request auto_moa_reasoning is False
    assert (
        resolve_effective_moa_preset_id(
            engine_params=params,
            requested_preset_id=None,
            routing_tier="reasoning",
            auto_moa_reasoning=False,
        )
        == MOA_PRESET_REVIEW_ID
    )


def test_resolve_effective_moa_preset_fallback_to_default_when_review_empty() -> None:
    params = {
        "moa_overlay": {
            "enabled": True,
            "presets": {
                MOA_PRESET_DEFAULT_ID: {
                    "reference_model_selections": [
                        {"providerId": "openai", "model": "gpt-4o-mini"},
                    ],
                },
                MOA_PRESET_REVIEW_ID: {
                    "reference_model_selections": [],
                },
            },
        },
    }
    # Review is empty, should fall back to default preset which has refs
    assert (
        resolve_effective_moa_preset_id(
            engine_params=params,
            requested_preset_id=None,
            routing_tier="reasoning",
            auto_moa_reasoning=True,
        )
        == MOA_PRESET_DEFAULT_ID
    )


def test_resolve_effective_moa_preset_respects_auto_moa_preset_id() -> None:
    params = {
        "moa_overlay": {
            "enabled": True,
            "presets": {
                MOA_PRESET_FAST_ID: {
                    "reference_model_selections": [
                        {"providerId": "openai", "model": "gpt-4o-mini"},
                    ],
                },
                MOA_PRESET_REVIEW_ID: {
                    "reference_model_selections": [
                        {"providerId": "anthropic", "model": "claude-3-5-sonnet"},
                    ],
                },
            },
        },
    }
    # Explicit auto target preset id requested
    assert (
        resolve_effective_moa_preset_id(
            engine_params=params,
            requested_preset_id=None,
            routing_tier="reasoning",
            auto_moa_reasoning=True,
            auto_moa_preset_id=MOA_PRESET_FAST_ID,
        )
        == MOA_PRESET_FAST_ID
    )


