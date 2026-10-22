"""Unit tests for AgentProfileAdvisorAutoActivationPolicy in moa_preset_resolver."""

from app.services.agent.moa_preset_resolver import (
    apply_moa_preset_activation,
    resolve_effective_moa_preset_id,
    resolve_profile_moa_activation_mode,
)


def _build_test_engine_params(
    *,
    enabled: bool = True,
    activation_mode: str = "manual",
    default_preset_id: str = "review",
    auto_on_reasoning: bool = False,
    risk_trigger_tools: list[str] | None = None,
) -> dict[str, object]:
    refs_review = [{"providerId": "anthropic", "model": "claude-3-5-sonnet"}]
    refs_default = [{"providerId": "openai", "model": "gpt-4o"}]
    refs_fast = [{"providerId": "deepseek", "model": "deepseek-chat"}]

    overlay: dict[str, object] = {
        "enabled": enabled,
        "activation_mode": activation_mode,
        "default_preset_id": default_preset_id,
        "auto_on_reasoning": auto_on_reasoning,
        "presets": {
            "review": {"reference_model_selections": refs_review},
            "default": {"reference_model_selections": refs_default},
            "fast": {"reference_model_selections": refs_fast},
        },
    }
    if risk_trigger_tools is not None:
        overlay["risk_trigger_tools"] = risk_trigger_tools

    return {"moa_overlay": overlay}


class TestAgentProfileAdvisorAutoActivationPolicy:
    """Test policy resolution, risk triggering, and explicit request priority."""

    def test_resolve_profile_activation_mode(self) -> None:
        # Default manual
        params_manual = _build_test_engine_params(activation_mode="manual")
        assert resolve_profile_moa_activation_mode(params_manual) == "manual"

        # Explicit always
        params_always = _build_test_engine_params(activation_mode="always")
        assert resolve_profile_moa_activation_mode(params_always) == "always"

        # Explicit risk_triggered
        params_risk = _build_test_engine_params(activation_mode="risk_triggered")
        assert resolve_profile_moa_activation_mode(params_risk) == "risk_triggered"

        # Legacy auto_on_reasoning maps to risk_triggered
        params_legacy = _build_test_engine_params(activation_mode="unknown", auto_on_reasoning=True)
        assert resolve_profile_moa_activation_mode(params_legacy) == "risk_triggered"

        # Disabled overlay always returns manual
        params_disabled = _build_test_engine_params(enabled=False, activation_mode="always")
        assert resolve_profile_moa_activation_mode(params_disabled) == "manual"

    def test_explicit_picker_request_takes_highest_priority(self) -> None:
        params_always = _build_test_engine_params(activation_mode="always", default_preset_id="review")

        # User explicitly requested fast -> honor fast
        assert resolve_effective_moa_preset_id(params_always, requested_preset_id="fast") == "fast"

        # User explicitly requested none -> turn off
        assert resolve_effective_moa_preset_id(params_always, requested_preset_id="none") is None
        assert resolve_effective_moa_preset_id(params_always, requested_preset_id="disabled") is None

    def test_always_mode_auto_activates_default_preset(self) -> None:
        params = _build_test_engine_params(activation_mode="always", default_preset_id="review")
        # No explicit request -> auto activates review
        assert resolve_effective_moa_preset_id(params) == "review"

        # Apply activation enables overlay with review refs
        activated = apply_moa_preset_activation(params)
        assert activated is not None
        overlay = activated["moa_overlay"]
        assert isinstance(overlay, dict)
        assert overlay["enabled"] is True
        assert overlay["active_preset_id"] == "review"
        assert len(overlay["reference_model_selections"]) == 1

    def test_risk_triggered_mode_inactive_under_normal_conditions(self) -> None:
        params = _build_test_engine_params(activation_mode="risk_triggered", default_preset_id="review")
        # Normal turn with no risk signals -> None
        assert resolve_effective_moa_preset_id(params) is None

        applied = apply_moa_preset_activation(params)
        assert applied is not None
        assert applied["moa_overlay"]["enabled"] is False

    def test_risk_triggered_mode_triggers_on_reasoning_tier(self) -> None:
        params = _build_test_engine_params(activation_mode="risk_triggered", default_preset_id="review")
        # Reasoning tier -> auto activates
        assert resolve_effective_moa_preset_id(params, routing_tier="reasoning") == "review"

        applied = apply_moa_preset_activation(params, routing_tier="reasoning")
        assert applied is not None
        assert applied["moa_overlay"]["enabled"] is True
        assert applied["moa_overlay"]["active_preset_id"] == "review"

    def test_risk_triggered_mode_triggers_on_risk_flag(self) -> None:
        params = _build_test_engine_params(activation_mode="risk_triggered", default_preset_id="review")
        # Explicit risk flag -> auto activates
        assert resolve_effective_moa_preset_id(params, has_risk_trigger=True) == "review"

    def test_risk_triggered_mode_triggers_on_dangerous_tools(self) -> None:
        params = _build_test_engine_params(activation_mode="risk_triggered", default_preset_id="review")
        # Safe read tools -> does not trigger
        assert resolve_effective_moa_preset_id(params, task_tools=["file_read_tool", "grep_tool"]) is None

        # Destructive write tool -> auto triggers
        assert (
            resolve_effective_moa_preset_id(params, task_tools=["file_read_tool", "bash_code_execute_tool"])
            == "review"
        )
        assert resolve_effective_moa_preset_id(params, task_tools=["file_edit_tool"]) == "review"
