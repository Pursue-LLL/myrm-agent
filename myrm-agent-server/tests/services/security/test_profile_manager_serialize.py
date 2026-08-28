"""Tests for security profile config serialization."""

from types import SimpleNamespace

from app.services.security.profile_manager import _serialize_config, _to_dict


class TestSerializeConfig:
    def test_legacy_delegate_agent_fans_out_on_save(self) -> None:
        result = _serialize_config(
            {
                "permissions": {"delegate_agent": "allow", "shell_exec": "deny"},
                "autoModeEnabled": False,
            }
        )
        permissions = result["permissions"]
        assert isinstance(permissions, dict)
        assert permissions["spawn_subagent"] == "allow"
        assert permissions["invoke_external_agent"] == "allow"
        assert "delegate_agent" not in permissions


class TestProfileReadPath:
    def test_legacy_delegate_agent_fans_out_on_read(self) -> None:
        profile = SimpleNamespace(
            id="profile-1",
            profile_key="legacy-custom",
            display_name="Legacy Custom",
            description="",
            config_json={
                "permissions": {"delegate_agent": "deny", "shell_exec": "ask"},
                "autoModeEnabled": False,
            },
            is_builtin=False,
            is_active=False,
            created_at=None,
            updated_at=None,
        )
        result = _to_dict(profile)  # type: ignore[arg-type]
        config_json = result["config_json"]
        assert isinstance(config_json, dict)
        permissions = config_json["permissions"]
        assert isinstance(permissions, dict)
        assert permissions["spawn_subagent"] == "deny"
        assert permissions["invoke_external_agent"] == "deny"
        assert "delegate_agent" not in permissions
