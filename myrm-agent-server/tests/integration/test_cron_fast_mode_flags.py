"""Fast search mode must not enable cron eager even if agent profile lists cron."""

from __future__ import annotations

from app.services.agent.profile_resolver import resolve_builtin_tool_flags


def test_fast_mode_builtin_list_excludes_cron_eager() -> None:
    fast_builtin = ["answer_tool"]
    flags = resolve_builtin_tool_flags(fast_builtin)
    assert flags["enable_cron_eager"] is False


def test_fast_mode_ignores_agent_cron_in_enabled_list() -> None:
    """converter.py:841 forces fast_builtin=['answer_tool'] — cron from profile is not used."""
    agent_tools_with_cron = ["web_search", "memory", "cron"]
    fast_flags = resolve_builtin_tool_flags(["answer_tool"])
    full_flags = resolve_builtin_tool_flags(agent_tools_with_cron)
    assert fast_flags["enable_cron_eager"] is False
    assert full_flags["enable_cron_eager"] is True
