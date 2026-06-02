"""Unit tests for permissions module

Tests the security permission system including:
- Security mode switching (safe/ask/allow_all)
- Permission evaluation using framework layer
- Mode persistence
- Error handling
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from myrm_agent_harness.agent.security.types import PermissionAction

from app.api.events.permissions import (
    SecurityMode,
    _action_to_permission,
    _build_security_config_for_mode,
    _infer_risk_level,
    get_current_security_config,
    set_security_mode,
)


class TestSecurityModeBuilding:
    """Test security config building for different modes"""

    def test_safe_mode_denies_dangerous_operations(self):
        config = _build_security_config_for_mode(SecurityMode.SAFE)

        # Should have restrictive ruleset
        assert config.ruleset is not None
        assert len(config.ruleset) > 0

        # Verify denial rules exist for dangerous operations
        rules_dict = {(r.permission, r.pattern): r.action for r in config.ruleset}
        assert rules_dict.get(("shell_exec", "*")) == PermissionAction.DENY
        assert rules_dict.get(("code_interpreter", "*")) == PermissionAction.DENY
        assert rules_dict.get(("file_write", "*")) == PermissionAction.DENY

    def test_allow_all_mode_permits_everything(self):
        config = _build_security_config_for_mode(SecurityMode.ALLOW_ALL)

        # Should have permissive ruleset
        assert config.ruleset is not None
        assert len(config.ruleset) == 1
        assert config.ruleset[0].action == PermissionAction.ALLOW
        assert config.ruleset[0].permission == "*"

    def test_ask_mode_uses_default_ruleset(self):
        config = _build_security_config_for_mode(SecurityMode.ASK)

        # Should use framework's DEFAULT_RULESET
        assert config.ruleset is not None
        # DEFAULT_RULESET has shell_exec and code_interpreter as ASK
        rules_dict = {(r.permission, r.pattern): r.action for r in config.ruleset}
        assert rules_dict.get(("shell_exec", "*")) == PermissionAction.ASK


class TestSecurityModeSwitching:
    """Test mode switching and persistence"""

    def test_set_security_mode_updates_config(self):
        # Switch to SAFE mode
        set_security_mode(SecurityMode.SAFE)
        config = get_current_security_config()

        # Verify config is updated
        rules_dict = {(r.permission, r.pattern): r.action for r in config.ruleset}
        assert rules_dict.get(("shell_exec", "*")) == PermissionAction.DENY

    @patch("app.api.events.permissions._persist_mode")
    def test_mode_persistence_is_called(self, mock_persist):
        set_security_mode(SecurityMode.ALLOW_ALL)
        mock_persist.assert_called_once_with(SecurityMode.ALLOW_ALL)


class TestActionMapping:
    """Test action to permission type mapping"""

    def test_tool_call_maps_to_shell_exec(self):
        assert _action_to_permission("tool_call") == "shell_exec"

    def test_command_maps_to_shell_exec(self):
        assert _action_to_permission("command") == "shell_exec"

    def test_file_write_maps_correctly(self):
        assert _action_to_permission("file_write") == "file_write"

    def test_file_delete_maps_to_file_write(self):
        assert _action_to_permission("file_delete") == "file_write"

    def test_unknown_action_returns_itself(self):
        assert _action_to_permission("unknown_action") == "unknown_action"


class TestRiskLevelInference:
    """Test risk level inference logic"""

    def test_deny_action_is_critical(self):
        risk = _infer_risk_level("file_write", PermissionAction.DENY)
        assert risk == "critical"

    def test_ask_action_for_shell_is_high(self):
        risk = _infer_risk_level("shell_exec", PermissionAction.ASK)
        assert risk == "high"

    def test_ask_action_for_code_interpreter_is_high(self):
        risk = _infer_risk_level("code_interpreter", PermissionAction.ASK)
        assert risk == "high"

    def test_ask_action_for_others_is_medium(self):
        risk = _infer_risk_level("file_read", PermissionAction.ASK)
        assert risk == "medium"

    def test_allow_action_is_low(self):
        risk = _infer_risk_level("file_read", PermissionAction.ALLOW)
        assert risk == "low"


class TestModePersistence:
    """Test mode persistence to file"""

    @patch("app.api.events.permissions._PERMISSION_MODE_FILE")
    def test_persist_mode_creates_parent_dir(self, mock_file):
        from app.api.events.permissions import _persist_mode

        mock_path = MagicMock()
        mock_file.parent = mock_path
        mock_file.write_text = Mock()

        _persist_mode(SecurityMode.SAFE)

        mock_path.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_file.write_text.assert_called_once_with(SecurityMode.SAFE)

    @patch("app.api.events.permissions._PERMISSION_MODE_FILE")
    def test_load_persisted_mode_returns_default_if_missing(self, mock_file):
        from app.api.events.permissions import _load_persisted_mode

        mock_file.exists.return_value = False

        mode = _load_persisted_mode()
        assert mode == SecurityMode.ASK  # Default

    @patch("app.api.events.permissions._PERMISSION_MODE_FILE")
    def test_load_persisted_mode_reads_file(self, mock_file):
        from app.api.events.permissions import _load_persisted_mode

        mock_file.exists.return_value = True
        mock_file.read_text.return_value = "allow_all"

        mode = _load_persisted_mode()
        assert mode == SecurityMode.ALLOW_ALL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
