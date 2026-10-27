"""Request-scoped security overlays layered over the persisted securityConfig.

[INPUT]
- app.remote_access.tool_policy::merge_remote_security_overlay (POS: remote-exposed tool deny overlay)
- app.core.channel_bridge.learn_handler::elevate_skill_manage_permission (POS: /learn turn skill_manage ASK elevation)

[OUTPUT]
- PRESET_OVERLAYS / apply_session_preset: chat-session security preset overlays (accept_edits, explore)
- SecurityOverlaySpec: the overlay inputs of one request; ``apply`` layers them over a persisted securityConfig

[POS]
The persisted securityConfig is reloaded before every stream turn so a Settings change takes effect mid-session.
The overlays that belong to the request (session preset, remote-exposed admission, /learn authoring) are kept as
data on the agent and re-applied on top of every reload, so a saved config can never loosen them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

PRESET_OVERLAYS: dict[str, dict[str, object]] = {
    "accept_edits": {
        "permissions": {
            "*": "allow",
            "shell_exec": "ask",
            "code_interpreter": "ask",
            "browser_evaluate": "deny",
            "browser_upload": "ask",
            "browser_download": "ask",
            "browser_fill": "ask",
            "skill_manage": "ask",
            "cron_manage": "ask",
            "mcp_invoke": "ask",
            "spawn_subagent": "allow",
            "invoke_external_agent": "ask",
        },
        "autoModeEnabled": True,
    },
    "explore": {
        "permissions": {
            "*": "allow",
            "file_write": "deny",
            "file_edit": "deny",
            "file_delete": "deny",
            "shell_exec": "deny",
            "code_interpreter": "deny",
            "browser_evaluate": "deny",
            "browser_fill": "deny",
            "browser_upload": "deny",
            "browser_download": "deny",
            "skill_manage": "deny",
            "cron_manage": "deny",
            "mcp_invoke": "ask",
            "spawn_subagent": "allow",
            "invoke_external_agent": "deny",
        },
    },
}


def apply_session_preset(
    base: dict[str, object] | None,
    preset: str | None,
) -> dict[str, object] | None:
    """Merge a chat-session security preset overlay onto the base config dict.

    When *preset* is ``None`` or ``"hitl"``, the base config is returned
    unchanged (HITL is the default — every tool call requires approval).

    The ``permissions`` key is merged at the individual permission level
    (not replaced wholesale) so that base deny rules are preserved unless
    the preset explicitly overrides them.
    """
    if not preset or preset == "hitl":
        return base
    overlay = PRESET_OVERLAYS.get(preset)
    if overlay is None:
        return base
    if base is None:
        return dict(overlay)
    merged = dict(base)
    for key, value in overlay.items():
        if key == "permissions" and isinstance(value, dict):
            base_perms = merged.get("permissions")
            merged_perms = dict(base_perms) if isinstance(base_perms, dict) else {}
            merged_perms.update(value)
            merged["permissions"] = merged_perms
        else:
            merged[key] = value
    return merged


class SecurityOverlaySpec(BaseModel):
    """The security overlays of one request, as plain data that survives serialization."""

    model_config = ConfigDict(frozen=True)

    preset: str | None = None
    trust_zone: str | None = None
    admission_path: str | None = None
    learn_authoring: bool = False

    def apply(self, base: dict[str, object] | None) -> dict[str, object] | None:
        """Layer the request overlays over *base* in the order: preset, remote admission, /learn authoring."""
        from app.core.channel_bridge.learn_handler import elevate_skill_manage_permission
        from app.remote_access.tool_policy import merge_remote_security_overlay

        config = apply_session_preset(base, self.preset)
        config = merge_remote_security_overlay(
            config,
            trust_zone=self.trust_zone,
            admission_path=self.admission_path,
        )
        if self.learn_authoring:
            config = elevate_skill_manage_permission(config)
        return config


__all__ = ["PRESET_OVERLAYS", "SecurityOverlaySpec", "apply_session_preset"]
