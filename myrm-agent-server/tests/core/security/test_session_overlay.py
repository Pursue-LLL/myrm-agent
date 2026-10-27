"""Unit tests for the request-scoped security overlays (session presets, remote admission, /learn authoring)."""

import pytest
from myrm_agent_harness.agent.security.config import remote_exposed_permissions

from app.core.security.session_overlay import PRESET_OVERLAYS, SecurityOverlaySpec, apply_session_preset

# ---------------------------------------------------------------------------
# apply_session_preset: pure dict merge
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# apply_session_preset: pure dict merge
# ---------------------------------------------------------------------------


class TestApplySessionPreset:
    """apply_session_preset overlay merge logic."""

    def test_none_preset_returns_base_unchanged(self) -> None:
        base: dict[str, object] = {"permissions": {"*": "ask"}, "autoModeEnabled": False}
        result = apply_session_preset(base, None)
        assert result is base

    def test_hitl_preset_returns_base_unchanged(self) -> None:
        base: dict[str, object] = {"permissions": {"*": "ask"}}
        result = apply_session_preset(base, "hitl")
        assert result is base

    def test_empty_string_preset_returns_base_unchanged(self) -> None:
        base: dict[str, object] = {"permissions": {"*": "ask"}}
        result = apply_session_preset(base, "")
        assert result is base

    def test_accept_edits_merges_overlay(self) -> None:
        base: dict[str, object] = {"yoloModeEnabled": False, "permissions": {"*": "ask"}}
        result = apply_session_preset(base, "accept_edits")
        assert result is not base
        assert result["yoloModeEnabled"] is False
        assert result["autoModeEnabled"] is True
        assert isinstance(result["permissions"], dict)
        assert result["permissions"]["*"] == "allow"
        assert result["permissions"]["shell_exec"] == "ask"

    def test_explore_merges_overlay(self) -> None:
        base: dict[str, object] = {"yoloModeEnabled": False, "permissions": {"*": "ask"}}
        result = apply_session_preset(base, "explore")
        assert result is not base
        assert isinstance(result["permissions"], dict)
        assert result["permissions"]["file_write"] == "deny"
        assert result["permissions"]["file_edit"] == "deny"
        assert result["permissions"]["shell_exec"] == "deny"
        assert result["permissions"]["spawn_subagent"] == "allow"
        assert result["permissions"]["invoke_external_agent"] == "deny"
        assert "autoModeEnabled" not in result

    def test_base_none_with_accept_edits_creates_new_dict(self) -> None:
        result = apply_session_preset(None, "accept_edits")
        assert result is not None
        assert result["autoModeEnabled"] is True
        assert isinstance(result["permissions"], dict)

    def test_base_none_with_explore_creates_new_dict(self) -> None:
        result = apply_session_preset(None, "explore")
        assert result is not None
        permissions = result["permissions"]
        assert isinstance(permissions, dict)
        assert permissions["file_write"] == "deny"

    def test_base_none_with_hitl_returns_none(self) -> None:
        result = apply_session_preset(None, "hitl")
        assert result is None

    def test_unknown_preset_returns_base(self) -> None:
        base: dict[str, object] = {"permissions": {"*": "ask"}}
        result = apply_session_preset(base, "nonexistent")
        assert result is base

    def test_overlay_does_not_mutate_original_base(self) -> None:
        base: dict[str, object] = {"permissions": {"*": "ask"}, "extra": True}
        original_base = dict(base)
        apply_session_preset(base, "accept_edits")
        assert base == original_base


# ---------------------------------------------------------------------------
# PRESET_OVERLAYS structure validation
# ---------------------------------------------------------------------------


class TestPresetOverlaysStructure:
    """Validate the static overlay dictionaries are well-formed."""

    def test_accept_edits_overlay_has_required_keys(self) -> None:
        overlay = PRESET_OVERLAYS["accept_edits"]
        assert "permissions" in overlay
        assert "autoModeEnabled" in overlay
        assert overlay["autoModeEnabled"] is True

    def test_explore_overlay_denies_all_writes(self) -> None:
        overlay = PRESET_OVERLAYS["explore"]
        permissions = overlay["permissions"]
        assert isinstance(permissions, dict)
        write_ops = ["file_write", "file_edit", "file_delete", "shell_exec", "code_interpreter"]
        for op in write_ops:
            assert permissions[op] == "deny", f"{op} should be deny in explore"

    def test_explore_overlay_allows_read_operations(self) -> None:
        overlay = PRESET_OVERLAYS["explore"]
        permissions = overlay["permissions"]
        assert isinstance(permissions, dict)
        assert permissions["*"] == "allow"
        assert permissions["spawn_subagent"] == "allow"
        assert permissions["invoke_external_agent"] == "deny"

    def test_explore_overlay_does_not_enable_auto_mode(self) -> None:
        overlay = PRESET_OVERLAYS["explore"]
        assert "autoModeEnabled" not in overlay


# ---------------------------------------------------------------------------
# SecurityOverlaySpec: the overlays of one request layered over a persisted config
# ---------------------------------------------------------------------------

_SAVED: dict[str, object] = {
    "yoloModeEnabled": True,
    "permissions": {"*": "allow", "file_edit": "allow", "shell_exec": "ask"},
}


class TestSecurityOverlaySpec:
    def test_empty_spec_returns_base_unchanged(self) -> None:
        assert SecurityOverlaySpec().apply(_SAVED) is _SAVED
        assert SecurityOverlaySpec().apply(None) is None

    def test_explore_denies_what_the_saved_config_allows(self) -> None:
        result = SecurityOverlaySpec(preset="explore").apply(_SAVED)
        assert result is not None
        permissions = result["permissions"]
        assert isinstance(permissions, dict)
        assert permissions["file_edit"] == "deny"
        assert _SAVED["permissions"]["file_edit"] == "allow"  # type: ignore[index]

    def test_remote_exposed_denies_and_turns_yolo_off(self) -> None:
        result = SecurityOverlaySpec(trust_zone="remote_exposed", admission_path="tunnel").apply(_SAVED)
        assert result is not None
        assert result["yoloModeEnabled"] is False
        permissions = result["permissions"]
        assert isinstance(permissions, dict)
        for tool, action in remote_exposed_permissions().items():
            assert permissions[tool] == action

    def test_local_trusted_request_leaves_the_saved_config_alone(self) -> None:
        spec = SecurityOverlaySpec(trust_zone="local_trusted", admission_path="loopback_direct")
        assert spec.apply(_SAVED) is _SAVED

    def test_learn_authoring_elevates_skill_manage_over_a_preset_deny(self) -> None:
        result = SecurityOverlaySpec(preset="explore", learn_authoring=True).apply(_SAVED)
        assert result is not None
        permissions = result["permissions"]
        assert isinstance(permissions, dict)
        assert permissions["skill_manage"] == "ask"
        assert permissions["file_edit"] == "deny"

    def test_overlays_apply_in_order_preset_then_remote_then_learn(self) -> None:
        spec = SecurityOverlaySpec(
            preset="accept_edits", trust_zone="remote_exposed", admission_path="tunnel", learn_authoring=True
        )
        result = spec.apply(_SAVED)
        assert result is not None
        permissions = result["permissions"]
        assert isinstance(permissions, dict)
        # accept_edits allows spawn_subagent; the remote overlay is applied after it and takes it away again
        assert permissions["spawn_subagent"] == remote_exposed_permissions()["spawn_subagent"]
        assert permissions["skill_manage"] == "ask"

    def test_serialization_round_trip_keeps_every_field(self) -> None:
        spec = SecurityOverlaySpec(preset="explore", trust_zone="remote_exposed", admission_path="tunnel", learn_authoring=True)
        assert SecurityOverlaySpec.model_validate(spec.model_dump(mode="json")) == spec

    def test_spec_is_immutable(self) -> None:
        with pytest.raises(ValueError):
            SecurityOverlaySpec().preset = "explore"  # type: ignore[misc]
