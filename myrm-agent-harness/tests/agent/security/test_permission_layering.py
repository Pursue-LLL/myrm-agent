"""A request overlay is laid over a saved permission map without undoing a saved denial."""

from __future__ import annotations

from myrm_agent_harness.agent.security.config import from_config, layer_permissions, read_only_permissions
from myrm_agent_harness.agent.security.engine import evaluate
from myrm_agent_harness.agent.security.types import DEFAULT_RULESET, PermissionAction, SecurityConfig

ALLOW, DENY = PermissionAction.ALLOW, PermissionAction.DENY

_Permissions = dict[str, str | dict[str, str]]

_WILDCARD_ALLOW: _Permissions = {"*": "allow", "shell_exec": "ask"}


def _verdict(permissions: _Permissions, permission: str, target: str = "*") -> PermissionAction:
    """What the engine decides once *permissions* are laid over the default rules."""
    return evaluate(permission, target, DEFAULT_RULESET, from_config(permissions)).action


class TestLayerPermissions:
    def test_a_key_the_overlay_names_replaces_a_saved_value_that_is_not_a_denial(self) -> None:
        assert layer_permissions({"shell_exec": "allow"}, {"shell_exec": "deny"}) == {"shell_exec": "deny"}
        assert layer_permissions({"shell_exec": "ask"}, {"shell_exec": "allow"}) == {"shell_exec": "allow"}

    def test_a_saved_denial_is_never_loosened_by_a_key_the_overlay_names(self) -> None:
        assert layer_permissions({"shell_exec": "deny"}, {"shell_exec": "ask"}) == {"shell_exec": "deny"}
        layered: _Permissions = layer_permissions({"spawn_subagent": "deny"}, {"*": "allow", "spawn_subagent": "allow"})
        assert _verdict(layered, "spawn_subagent") is DENY

    def test_an_overlay_names_a_saved_pattern_map_it_replaces_whole(self) -> None:
        saved: _Permissions = {"file_write": {"*": "allow", "*.pem": "deny"}}
        assert layer_permissions(saved, {"file_write": "deny"}) == {"file_write": "deny"}

    def test_a_saved_denial_the_overlay_does_not_name_outranks_the_overlay_wildcard(self) -> None:
        layered = layer_permissions({"file_edit": "deny"}, _WILDCARD_ALLOW)
        assert _verdict(layered, "file_edit") is DENY
        assert _verdict(layered, "mcp_invoke") is ALLOW

    def test_a_saved_ask_still_yields_to_the_overlay_wildcard(self) -> None:
        layered = layer_permissions({"mcp_invoke": "ask", "file_edit": "deny"}, _WILDCARD_ALLOW)
        assert _verdict(layered, "mcp_invoke") is ALLOW

    def test_a_saved_pattern_map_holding_a_denial_is_kept_final_too(self) -> None:
        saved: _Permissions = {"file_write": {"*": "allow", "*.pem": "deny"}}
        layered = layer_permissions(saved, _WILDCARD_ALLOW)
        assert _verdict(layered, "file_write", "server.pem") is DENY
        assert _verdict(layered, "file_write", "notes.txt") is ALLOW

    def test_a_saved_allow_list_keeps_its_shape_under_an_overlay_without_a_wildcard(self) -> None:
        saved: _Permissions = {"*": "deny", "file_read": "allow"}
        layered = layer_permissions(saved, {"spawn_subagent": "deny"})
        assert _verdict(layered, "file_read") is ALLOW
        assert _verdict(layered, "web_search") is DENY

    def test_an_overlay_wildcard_replaces_a_saved_wildcard(self) -> None:
        layered = layer_permissions({"*": "deny", "file_read": "allow"}, _WILDCARD_ALLOW)
        assert _verdict(layered, "web_search") is ALLOW

    def test_the_inputs_are_left_alone(self) -> None:
        saved: _Permissions = {"file_edit": "deny", "mcp_invoke": "ask"}
        overlay: _Permissions = dict(_WILDCARD_ALLOW)
        layer_permissions(saved, overlay)
        assert saved == {"file_edit": "deny", "mcp_invoke": "ask"}
        assert overlay == _WILDCARD_ALLOW

    def test_an_empty_saved_map_gives_a_copy_of_the_overlay(self) -> None:
        layered = layer_permissions({}, _WILDCARD_ALLOW)
        assert layered == _WILDCARD_ALLOW
        assert layered is not _WILDCARD_ALLOW


class TestReadOnlyPermissions:
    def test_it_denies_everything_the_readonly_profile_denies(self) -> None:
        profile = {rule.permission for rule in SecurityConfig.readonly().ruleset if rule.action is DENY}
        denied = {permission for permission, action in read_only_permissions().items() if action == DENY.value}
        assert profile <= denied

    def test_it_denies_the_state_changing_types_the_profile_leaves_to_its_wildcard(self) -> None:
        permissions = read_only_permissions()
        assert permissions["knowledge_write"] == DENY.value
        assert permissions["desktop_control"] == DENY.value

    def test_it_leaves_read_tools_and_subagents_available(self) -> None:
        permissions = read_only_permissions()
        assert permissions["*"] == ALLOW.value
        assert permissions["spawn_subagent"] == ALLOW.value
