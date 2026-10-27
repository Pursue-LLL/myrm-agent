"""Tests for SecurityPolicyExtension — custom PII fields passthrough and per-turn store sync."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from myrm_agent_harness.agent.security.engine import evaluate_tool_call
from myrm_agent_harness.agent.security.types import PermissionAction

from app.ai_agents.extensions.security_policy_extension import (
    SecurityPolicyExtension,
    sync_wrapper_security_from_store,
)
from app.core.security.session_overlay import SecurityOverlaySpec


class TestCustomPiiFieldsInit:
    """Verify custom PII fields are correctly stored as tuples."""

    def test_custom_fields_converted_to_tuples(self):
        ext = SecurityPolicyExtension(
            privacy_enabled=True,
            privacy_s2_action="warn",
            privacy_s3_action="redact",
            channel_name="test",
            security_config_raw={},
            agent_security_raw={},
            declared_capabilities=[],
            declared_allowed_roots=[],
            privacy_custom_keywords_s2=["secret", "internal"],
            privacy_custom_keywords_s3=["topsecret"],
            privacy_custom_patterns_s2=[r"PROJ-\d{4}"],
            privacy_custom_patterns_s3=[r"EMP-\d{6}"],
            privacy_sensitive_tools_s2=["shell_exec"],
            privacy_sensitive_tools_s3=["browser_navigate_tool"],
        )
        assert ext.privacy_custom_keywords_s2 == ("secret", "internal")
        assert ext.privacy_custom_keywords_s3 == ("topsecret",)
        assert ext.privacy_custom_patterns_s2 == (r"PROJ-\d{4}",)
        assert ext.privacy_custom_patterns_s3 == (r"EMP-\d{6}",)
        assert ext.privacy_sensitive_tools_s2 == ("shell_exec",)
        assert ext.privacy_sensitive_tools_s3 == ("browser_navigate_tool",)

    def test_none_defaults_to_empty_tuples(self):
        ext = SecurityPolicyExtension(
            privacy_enabled=False,
            privacy_s2_action="warn",
            privacy_s3_action="redact",
            channel_name="test",
            security_config_raw={},
            agent_security_raw={},
            declared_capabilities=[],
            declared_allowed_roots=[],
        )
        assert ext.privacy_custom_keywords_s2 == ()
        assert ext.privacy_custom_keywords_s3 == ()
        assert ext.privacy_custom_patterns_s2 == ()
        assert ext.privacy_custom_patterns_s3 == ()
        assert ext.privacy_sensitive_tools_s2 == ()
        assert ext.privacy_sensitive_tools_s3 == ()

    def test_empty_list_yields_empty_tuple(self):
        ext = SecurityPolicyExtension(
            privacy_enabled=True,
            privacy_s2_action="warn",
            privacy_s3_action="redact",
            channel_name="test",
            security_config_raw={},
            agent_security_raw={},
            declared_capabilities=[],
            declared_allowed_roots=[],
            privacy_custom_keywords_s2=[],
            privacy_custom_patterns_s3=[],
        )
        assert ext.privacy_custom_keywords_s2 == ()
        assert ext.privacy_custom_patterns_s3 == ()


class TestAgentRequestCustomPiiFields:
    """Verify AgentRequest model accepts custom PII fields."""

    def test_agent_request_defaults_none(self):
        from app.services.agent.params.models import AgentRequest

        req = AgentRequest(messages=[], model="test", messageId="test-id")
        assert req.privacy_custom_keywords_s2 is None
        assert req.privacy_custom_keywords_s3 is None
        assert req.privacy_custom_patterns_s2 is None
        assert req.privacy_custom_patterns_s3 is None
        assert req.privacy_sensitive_tools_s2 is None
        assert req.privacy_sensitive_tools_s3 is None

    def test_agent_request_with_custom_fields(self):
        from app.services.agent.params.models import AgentRequest

        req = AgentRequest(
            messages=[],
            model="test",
            messageId="test-id",
            privacy_enabled=True,
            privacy_custom_keywords_s2=["secret"],
            privacy_custom_keywords_s3=["classified"],
            privacy_custom_patterns_s2=[r"\d{3}-\d{2}-\d{4}"],
            privacy_custom_patterns_s3=[r"EMP-\d+"],
            privacy_sensitive_tools_s2=["shell_exec"],
            privacy_sensitive_tools_s3=["browser_navigate_tool"],
        )
        assert req.privacy_custom_keywords_s2 == ["secret"]
        assert req.privacy_custom_keywords_s3 == ["classified"]
        assert req.privacy_custom_patterns_s2 == [r"\d{3}-\d{2}-\d{4}"]
        assert req.privacy_custom_patterns_s3 == [r"EMP-\d+"]
        assert req.privacy_sensitive_tools_s2 == ["shell_exec"]
        assert req.privacy_sensitive_tools_s3 == ["browser_navigate_tool"]


class TestExtensionName:
    def test_name(self):
        ext = SecurityPolicyExtension(
            privacy_enabled=False,
            privacy_s2_action="warn",
            privacy_s3_action="redact",
            channel_name="test",
            security_config_raw={},
            agent_security_raw={},
            declared_capabilities=[],
            declared_allowed_roots=[],
        )
        assert ext.name == "SecurityPolicyExtension"


class TestAgentYoloSecurityMerge:
    """Per-agent yoloModeEnabled must merge over user security_config for web_chat streams."""

    def test_agent_yolo_enabled_when_user_yolo_off(self) -> None:
        ext = SecurityPolicyExtension(
            privacy_enabled=False,
            privacy_s2_action="warn",
            privacy_s3_action="redact",
            channel_name="web_chat",
            security_config_raw={"yoloModeEnabled": False},
            agent_security_raw={
                "yoloModeEnabled": True,
                "yolo_mode_enabled_at": 1_700_000_000.0,
            },
            declared_capabilities=[],
            declared_allowed_roots=[],
        )
        built = ext._build_security_config()
        assert built.yolo_mode_enabled is True

    def test_remote_overlay_strips_user_yolo_agent_yolo_still_wins(self) -> None:
        from app.remote_access.tool_policy import merge_remote_security_overlay

        user_raw = merge_remote_security_overlay(
            {"yoloModeEnabled": True},
            trust_zone="remote_exposed",
            admission_path="/api/v1/agents/agent-stream",
        )
        assert user_raw is not None
        assert user_raw.get("yoloModeEnabled") is False

        ext = SecurityPolicyExtension(
            privacy_enabled=False,
            privacy_s2_action="warn",
            privacy_s3_action="redact",
            channel_name="web_chat",
            security_config_raw=user_raw,
            agent_security_raw={
                "yoloModeEnabled": True,
                "yolo_mode_enabled_at": 1_700_000_000.0,
            },
            declared_capabilities=[],
            declared_allowed_roots=[],
        )
        built = ext._build_security_config()
        assert built.yolo_mode_enabled is True


_SAVED_PERMISSIVE: dict[str, object] = {
    "yoloModeEnabled": False,
    "permissions": {"*": "allow", "file_edit": "allow", "invoke_external_agent": "allow"},
}


def _enforced_action(raw: dict[str, object] | None, tool: str, tool_input: dict[str, object]) -> PermissionAction:
    ext = SecurityPolicyExtension(
        privacy_enabled=False,
        privacy_s2_action="warn",
        privacy_s3_action="redact",
        channel_name="web_chat",
        security_config_raw=raw or {},
        agent_security_raw={},
        declared_capabilities=[],
        declared_allowed_roots=[],
    )
    action, _ = evaluate_tool_call(tool, tool_input, ext._build_security_config())
    return action


async def _sync(wrapper: SimpleNamespace, stored: dict[str, object] | None) -> None:
    loaded = SimpleNamespace(security_config_dict=stored)
    with patch("app.core.channel_bridge.config_loader.load_user_configs", new=AsyncMock(return_value=loaded)):
        await sync_wrapper_security_from_store(wrapper)  # type: ignore[arg-type]


class TestPerTurnStoreSyncKeepsRequestOverlays:
    """A saved securityConfig is reloaded every turn; it must not loosen the request's own overlays."""

    _EDIT = {"path": "/tmp/probe.txt", "old_string": "a", "new_string": "b"}

    async def test_explore_preset_still_denies_edits_after_sync(self) -> None:
        wrapper = SimpleNamespace(security_config_raw=None, security_overlay=SecurityOverlaySpec(preset="explore"))
        await _sync(wrapper, _SAVED_PERMISSIVE)
        assert _enforced_action(wrapper.security_config_raw, "file_edit", self._EDIT) is PermissionAction.DENY

    async def test_remote_exposed_request_still_denies_external_agents_after_sync(self) -> None:
        overlay = SecurityOverlaySpec(trust_zone="remote_exposed", admission_path="tunnel")
        wrapper = SimpleNamespace(security_config_raw=None, security_overlay=overlay)
        await _sync(wrapper, _SAVED_PERMISSIVE)
        assert _enforced_action(wrapper.security_config_raw, "invoke_external_agent", {}) is PermissionAction.DENY

    async def test_remote_exposed_request_keeps_yolo_off_when_settings_turn_it_on_mid_session(self) -> None:
        overlay = SecurityOverlaySpec(trust_zone="remote_exposed", admission_path="tunnel")
        wrapper = SimpleNamespace(security_config_raw=None, security_overlay=overlay)
        await _sync(wrapper, {"yoloModeEnabled": True})
        assert wrapper.security_config_raw is not None
        assert wrapper.security_config_raw["yoloModeEnabled"] is False

    async def test_settings_change_still_applies_mid_session(self) -> None:
        wrapper = SimpleNamespace(security_config_raw=None, security_overlay=SecurityOverlaySpec(preset="accept_edits"))
        await _sync(wrapper, {"yoloModeEnabled": True, "permissions": {"shell_exec": "deny"}})
        assert wrapper.security_config_raw is not None
        assert wrapper.security_config_raw["yoloModeEnabled"] is True

    async def test_wrapper_without_overlay_takes_the_stored_config_as_is(self) -> None:
        wrapper = SimpleNamespace(security_config_raw=None, security_overlay=None)
        await _sync(wrapper, _SAVED_PERMISSIVE)
        assert wrapper.security_config_raw == _SAVED_PERMISSIVE

    async def test_nothing_saved_leaves_the_build_time_config_untouched(self) -> None:
        built: dict[str, object] = {"permissions": {"file_edit": "deny"}}
        wrapper = SimpleNamespace(security_config_raw=built, security_overlay=SecurityOverlaySpec(preset="explore"))
        await _sync(wrapper, None)
        assert wrapper.security_config_raw is built
