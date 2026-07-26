"""Unit tests for _apply_session_preset in converter.py.

Verifies the three-tier security preset (hitl / accept_edits / explore)
overlay logic — the only new converter code for #1 Chat Session Permission Preset.
"""

import pytest
from pydantic import ValidationError

from app.services.agent.params.converter import _PRESET_OVERLAYS, _apply_session_preset
from app.services.agent.params.models import AgentRequest

# ---------------------------------------------------------------------------
# _apply_session_preset: pure dict merge
# ---------------------------------------------------------------------------


class TestApplySessionPreset:
    """_apply_session_preset overlay merge logic."""

    def test_none_preset_returns_base_unchanged(self) -> None:
        base: dict[str, object] = {"permissions": {"*": "ask"}, "autoModeEnabled": False}
        result = _apply_session_preset(base, None)
        assert result is base

    def test_hitl_preset_returns_base_unchanged(self) -> None:
        base: dict[str, object] = {"permissions": {"*": "ask"}}
        result = _apply_session_preset(base, "hitl")
        assert result is base

    def test_empty_string_preset_returns_base_unchanged(self) -> None:
        base: dict[str, object] = {"permissions": {"*": "ask"}}
        result = _apply_session_preset(base, "")
        assert result is base

    def test_accept_edits_merges_overlay(self) -> None:
        base: dict[str, object] = {"yoloModeEnabled": False, "permissions": {"*": "ask"}}
        result = _apply_session_preset(base, "accept_edits")
        assert result is not base
        assert result["yoloModeEnabled"] is False
        assert result["autoModeEnabled"] is True
        assert isinstance(result["permissions"], dict)
        assert result["permissions"]["*"] == "allow"
        assert result["permissions"]["shell_exec"] == "ask"

    def test_explore_merges_overlay(self) -> None:
        base: dict[str, object] = {"yoloModeEnabled": False, "permissions": {"*": "ask"}}
        result = _apply_session_preset(base, "explore")
        assert result is not base
        assert isinstance(result["permissions"], dict)
        assert result["permissions"]["file_write"] == "deny"
        assert result["permissions"]["file_edit"] == "deny"
        assert result["permissions"]["shell_exec"] == "deny"
        assert result["permissions"]["delegate_agent"] == "allow"
        assert "autoModeEnabled" not in result

    def test_base_none_with_accept_edits_creates_new_dict(self) -> None:
        result = _apply_session_preset(None, "accept_edits")
        assert result is not None
        assert result["autoModeEnabled"] is True
        assert isinstance(result["permissions"], dict)

    def test_base_none_with_explore_creates_new_dict(self) -> None:
        result = _apply_session_preset(None, "explore")
        assert result is not None
        permissions = result["permissions"]
        assert isinstance(permissions, dict)
        assert permissions["file_write"] == "deny"

    def test_base_none_with_hitl_returns_none(self) -> None:
        result = _apply_session_preset(None, "hitl")
        assert result is None

    def test_unknown_preset_returns_base(self) -> None:
        base: dict[str, object] = {"permissions": {"*": "ask"}}
        result = _apply_session_preset(base, "nonexistent")
        assert result is base

    def test_overlay_does_not_mutate_original_base(self) -> None:
        base: dict[str, object] = {"permissions": {"*": "ask"}, "extra": True}
        original_base = dict(base)
        _apply_session_preset(base, "accept_edits")
        assert base == original_base


# ---------------------------------------------------------------------------
# _PRESET_OVERLAYS structure validation
# ---------------------------------------------------------------------------


class TestPresetOverlaysStructure:
    """Validate the static overlay dictionaries are well-formed."""

    def test_accept_edits_overlay_has_required_keys(self) -> None:
        overlay = _PRESET_OVERLAYS["accept_edits"]
        assert "permissions" in overlay
        assert "autoModeEnabled" in overlay
        assert overlay["autoModeEnabled"] is True

    def test_explore_overlay_denies_all_writes(self) -> None:
        overlay = _PRESET_OVERLAYS["explore"]
        permissions = overlay["permissions"]
        assert isinstance(permissions, dict)
        write_ops = ["file_write", "file_edit", "file_delete", "shell_exec", "code_interpreter"]
        for op in write_ops:
            assert permissions[op] == "deny", f"{op} should be deny in explore"

    def test_explore_overlay_allows_read_operations(self) -> None:
        overlay = _PRESET_OVERLAYS["explore"]
        permissions = overlay["permissions"]
        assert isinstance(permissions, dict)
        assert permissions["*"] == "allow"
        assert permissions["delegate_agent"] == "allow"

    def test_explore_overlay_does_not_enable_auto_mode(self) -> None:
        overlay = _PRESET_OVERLAYS["explore"]
        assert "autoModeEnabled" not in overlay


# ---------------------------------------------------------------------------
# AgentRequest.security_preset field validation
# ---------------------------------------------------------------------------


class TestAgentRequestSecurityPreset:
    """Verify the Pydantic model accepts/rejects security_preset values."""

    @pytest.mark.parametrize("preset", ["hitl", "accept_edits", "explore", None])
    def test_valid_presets_accepted(self, preset: str | None) -> None:
        req = AgentRequest(message_id="m1", query="test", security_preset=preset)
        assert req.security_preset == preset

    def test_invalid_preset_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRequest(message_id="m1", query="test", security_preset="invalid")

    def test_default_preset_is_none(self) -> None:
        req = AgentRequest(message_id="m1", query="test")
        assert req.security_preset is None
