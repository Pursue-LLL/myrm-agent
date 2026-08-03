"""Tests for session-level MoA preset activation."""

from __future__ import annotations

from app.services.agent.moa_preset_resolver import (
    MOA_PRESET_DEFAULT_ID,
    MOA_PRESET_FAST_ID,
    MOA_PRESET_REVIEW_ID,
    apply_moa_preset_activation,
    is_moa_preset_configured,
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


def test_apply_activation_no_op_without_overlay_block() -> None:
    assert apply_moa_preset_activation({"consensus": {"enabled": True}}, MOA_PRESET_DEFAULT_ID) == {
        "consensus": {"enabled": True},
    }
