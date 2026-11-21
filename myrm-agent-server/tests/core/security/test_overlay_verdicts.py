"""The verdicts of the whole stack: saved config, request overlays, agent config and local mode.

Every combination is built the way a chat turn builds it (``SecurityOverlaySpec.apply`` over the saved config, then
``build_channel_security_config`` with the agent's own config) and the engine is asked about one call of each tool.
An overlay's restriction cannot be bypassed by what is saved, and a saved or agent denial cannot be reopened by an
overlay, by the defaults an agent config carries, or by the local-mode browser relaxation.
"""

from __future__ import annotations

import itertools

from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.engine import evaluate_tool_call, file_write_disabled
from myrm_agent_harness.agent.security.types import PermissionAction, SecurityConfig
from myrm_agent_harness.core.security.tool_registry import resolve_permission_type

from app.core.security.session_overlay import SecurityOverlaySpec

DENY, ALLOW = PermissionAction.DENY, PermissionAction.ALLOW

_WORKSPACE = "/tmp/overlay-verdicts-workspace"

# label -> (tool name, tool input); the permission of each call is resolved by the real tool registry.
_CALLS: dict[str, tuple[str, dict[str, object]]] = {
    "file_write": ("file_write_tool", {"file_path": f"{_WORKSPACE}/a.txt", "content": "x"}),
    "code_exec": ("bash_code_execute_tool", {"code": "print(1)"}),
    "skill_manage": ("skill_manage_tool", {}),
    "cron_manage": ("cron_manage_tool", {}),
    "external_agent": ("invoke_acp_agent_tool", {}),
    "wiki_apply": ("wiki_apply_tool", {}),
    "desktop": ("desktop_interact_tool", {}),
    "notify": ("channel_notify_tool", {}),
    "mcp_write": ("mcp__notion__create_page", {}),
    "web_search": ("web_search_tool", {"query": "x"}),
    "browser_fill": ("browser_interact_tool", {"action": "fill"}),
    "browser_upload": ("browser_interact_tool", {"action": "upload_file"}),
    "browser_download": ("browser_manage_tool", {"action": "download_url"}),
}

_SAVED: dict[str, dict[str, object] | None] = {
    "none": None,
    "asks": {"permissions": {"shell_exec": "ask", "mcp_invoke": "ask"}},
    "denials": {"permissions": {"file_write": "deny", "web_search_tool": "deny", "code_interpreter": "deny"}},
    "allow_list": {"permissions": {"*": "deny", "file_read": "allow", "web_search_tool": "allow"}},
    "wildcard_ask": {"permissions": {"*": "ask", "file_read": "allow"}},
    "wildcard_allow": {"permissions": {"code_interpreter": "ask", "skill_manage": "ask", "*": "allow"}},
}

_OVERLAYS: dict[str, SecurityOverlaySpec] = {
    "none": SecurityOverlaySpec(),
    "accept_edits": SecurityOverlaySpec(preset="accept_edits"),
    "explore": SecurityOverlaySpec(preset="explore"),
    "remote": SecurityOverlaySpec(trust_zone="remote_exposed", admission_path="tunnel"),
}

_AGENTS: dict[str, dict[str, object] | None] = {
    "none": None,
    "without_rules": {"networkAllowlist": ["example.com"]},
    "with_asks": {"permissions": {"shell_exec": "ask", "mcp_invoke": "ask", "knowledge_write": "ask"}},
    "denies_web": {"permissions": {"web_search_tool": "deny"}},
}

_DENIED_BY_READ_ONLY = (
    "file_write",
    "code_exec",
    "skill_manage",
    "cron_manage",
    "external_agent",
    "wiki_apply",
    "desktop",
    "notify",
    "browser_fill",
    "browser_upload",
    "browser_download",
)
_DENIED_BY_REMOTE = (
    "code_exec",
    "skill_manage",
    "external_agent",
    "desktop",
    "browser_fill",
    "browser_upload",
    "browser_download",
)
_NEVER_ALLOWED_BY_ACCEPT_EDITS = (
    "code_exec",
    "skill_manage",
    "cron_manage",
    "external_agent",
    "mcp_write",
    "browser_fill",
    "browser_upload",
    "browser_download",
)
_SAVED_DENIALS = ("file_write", "web_search", "code_exec")


def _verdicts(config: SecurityConfig) -> dict[str, PermissionAction]:
    verdicts: dict[str, PermissionAction] = {}
    for label, (tool, tool_input) in _CALLS.items():
        permission = resolve_permission_type(tool, tool_input)
        verdicts[label], _ = evaluate_tool_call(permission, tool_input, config, workspace_root=_WORKSPACE, tool_name=tool)
    return verdicts


def _broken_promises(saved: str, overlay: str, agent: str, *, local: bool) -> list[str]:
    user_config = _OVERLAYS[overlay].apply(_SAVED[saved])
    config = build_channel_security_config("web_chat", user_config, agent_security_raw=_AGENTS[agent], local_mode=local)
    verdicts = _verdicts(config)
    broken: list[str] = []
    if overlay == "explore":
        broken += [f"read-only {label}" for label in _DENIED_BY_READ_ONLY if verdicts[label] is not DENY]
        if verdicts["mcp_write"] is ALLOW:
            broken.append("read-only mcp_write")
        if not file_write_disabled(config):
            broken.append("read-only does not disable file_write")
    if overlay == "remote":
        broken += [f"remote {label}" for label in _DENIED_BY_REMOTE if verdicts[label] is not DENY]
    if overlay == "accept_edits":
        broken += [f"accept_edits {label}" for label in _NEVER_ALLOWED_BY_ACCEPT_EDITS if verdicts[label] is ALLOW]
    if saved == "denials":
        broken += [f"saved denial {label}" for label in _SAVED_DENIALS if verdicts[label] is not DENY]
    if agent == "denies_web" and verdicts["web_search"] is not DENY:
        broken.append("agent denial web_search")
    return broken


def test_every_combination_keeps_what_the_overlays_and_the_saved_denials_promise() -> None:
    report = [
        f"saved={saved} overlay={overlay} agent={agent} local={local}: {', '.join(broken)}"
        for saved, overlay, agent, local in itertools.product(_SAVED, _OVERLAYS, _AGENTS, (False, True))
        if (broken := _broken_promises(saved, overlay, agent, local=local))
    ]
    assert not report, "\n".join(report)
