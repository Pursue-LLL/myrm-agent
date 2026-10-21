"""Persist-time gate for external_cli enabled_builtin_tools.

[INPUT]
- app.config.external_cli_deploy::is_external_cli_deploy_supported (POS: LOCAL/TAURI deploy gate)
- app.core.channel_bridge.config_loader::load_user_configs (POS: merged UserConfig bundle loader)
- app.ai_agents.general_agent.external_agents::resolve_external_agent_backends (POS: external CLI backend resolution)

[OUTPUT]
- ExternalCliBackendUnavailableError: raised when external_cli cannot run
- assert_external_cli_tools_allowed: validate tool list before agent persist

[POS]
Server-side validation ensuring external_cli toggle is only persisted when a CLI backend
is resolvable (Settings config or local auto-detect), matching runtime mount preconditions.
"""

from __future__ import annotations

from collections.abc import Sequence


class ExternalCliBackendUnavailableError(ValueError):
    """external_cli was requested but no CLI backend is available in this deployment."""


async def _load_external_agents_config() -> list[dict[str, object]] | None:
    from app.core.channel_bridge.config_loader import load_user_configs

    configs = await load_user_configs()
    if configs is None or configs.external_agents_dict is None:
        return None
    agents_raw = configs.external_agents_dict.get("agents")
    if not isinstance(agents_raw, list):
        return None
    parsed: list[dict[str, object]] = []
    for item in agents_raw:
        if isinstance(item, dict):
            parsed.append(item)
    return parsed or None


async def external_cli_backend_available() -> bool:
    """Return True when runtime would resolve at least one external CLI backend."""
    from app.ai_agents.general_agent.external_agents import resolve_external_agent_backends

    configs = await _load_external_agents_config()
    resolved = await resolve_external_agent_backends(configs)
    return bool(resolved)


async def assert_external_cli_tools_allowed(tools: Sequence[str] | None) -> None:
    """Reject persist when external_cli is enabled but no backend can be resolved."""
    if not tools or "external_cli" not in tools:
        return

    from app.config.external_cli_deploy import is_external_cli_deploy_supported

    if not is_external_cli_deploy_supported():
        msg = "external_cli is not supported in this deployment mode"
        raise ExternalCliBackendUnavailableError(msg)

    if not await external_cli_backend_available():
        msg = (
            "external_cli requires an enabled CLI backend in Settings → Developer → External Agents, "
            "or a locally installed Claude Code, Codex, or Gemini CLI"
        )
        raise ExternalCliBackendUnavailableError(msg)


__all__ = [
    "ExternalCliBackendUnavailableError",
    "assert_external_cli_tools_allowed",
    "external_cli_backend_available",
]
