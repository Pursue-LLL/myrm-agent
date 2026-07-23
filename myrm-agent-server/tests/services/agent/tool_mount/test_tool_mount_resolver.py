"""Tests for tool_mount.resolve_agent_mount and apply_ptc_meta_mount."""

from __future__ import annotations

from app.services.agent.profile_resolver import resolve_builtin_tool_flags
from app.services.agent.tool_mount import ExecutionSurface, apply_ptc_meta_mount, resolve_agent_mount


class TestResolveAgentMount:
    def test_web_fast_disables_meta_file_and_shell(self) -> None:
        mounted = resolve_agent_mount(
            ExecutionSurface.WEB_FAST,
            resolve_builtin_tool_flags(["answer_tool"]),
        )
        assert mounted["enable_file_ops"] is False
        assert mounted["enable_shell_tools"] is False
        assert mounted["enable_answer_tool"] is True

    def test_web_chat_forces_general_baseline(self) -> None:
        mounted = resolve_agent_mount(
            ExecutionSurface.WEB_CHAT,
            resolve_builtin_tool_flags(["web_search"]),
        )
        assert mounted["enable_file_ops"] is True
        assert mounted["enable_shell_tools"] is True

    def test_cron_restricted_via_tools_policy(self) -> None:
        from app.core.cron.adapters.tools_policy import (
            intersect_cron_enabled_builtin_tools,
            resolve_cron_runtime_tool_flags,
        )

        intersected = intersect_cron_enabled_builtin_tools(
            ["web_search", "memory"],
            ("file_ops",),
        )
        flags = resolve_cron_runtime_tool_flags(intersected, ("file_ops",))
        assert flags["enable_file_ops"] is True
        assert flags["enable_shell_tools"] is False

    def test_cron_unrestricted_applies_baseline(self) -> None:
        mounted = resolve_agent_mount(
            ExecutionSurface.CRON,
            resolve_builtin_tool_flags(["web_search"]),
            cron_job_tools_allowed=None,
        )
        assert mounted["enable_file_ops"] is True
        assert mounted["enable_shell_tools"] is True

    def test_cron_restricted_returns_profile_flags_unchanged(self) -> None:
        base = resolve_builtin_tool_flags(["web_search"])
        from app.services.agent.profile_resolver import BuiltinToolFlags

        restricted = BuiltinToolFlags(
            **{
                **base,
                "enable_file_ops": True,
                "enable_shell_tools": False,
            }
        )
        mounted = resolve_agent_mount(
            ExecutionSurface.CRON,
            restricted,
            cron_job_tools_allowed=("file_ops",),
        )
        assert mounted is restricted
        assert mounted["enable_file_ops"] is True
        assert mounted["enable_shell_tools"] is False


class TestApplyPtcMetaMount:
    def test_ptc_forces_file_and_shell_when_shell_already_on(self) -> None:
        file_ops, shell = apply_ptc_meta_mount(False, True, has_mcp=True)
        assert file_ops is True
        assert shell is True

    def test_ptc_respects_explicit_shell_off(self) -> None:
        file_ops, shell = apply_ptc_meta_mount(True, False, has_mcp=True)
        assert file_ops is True
        assert shell is False

    def test_no_mcp_is_noop(self) -> None:
        file_ops, shell = apply_ptc_meta_mount(True, True, has_mcp=False)
        assert file_ops is True
        assert shell is True

    def test_ptc_noop_when_file_and_shell_already_on(self) -> None:
        file_ops, shell = apply_ptc_meta_mount(True, True, has_mcp=True)
        assert file_ops is True
        assert shell is True
