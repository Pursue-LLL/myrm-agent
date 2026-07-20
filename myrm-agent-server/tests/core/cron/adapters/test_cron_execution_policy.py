"""Tests for cron lifecycle guard and tools policy."""

from __future__ import annotations

import pytest

from app.core.cron.adapters.lifecycle_guard import (
    assert_cron_job_lifecycle_safe,
    contains_myrm_lifecycle_command,
)
from app.core.cron.adapters.tools_policy import (
    intersect_cron_enabled_builtin_tools,
    normalize_cron_tools_allowed,
)
from app.services.agent.builtin_tool_ids import InvalidBuiltinToolIdsError


class TestLifecycleGuard:
    def test_detects_myrm_restart(self) -> None:
        assert contains_myrm_lifecycle_command("./myrm restart --chrome") is True
        assert contains_myrm_lifecycle_command("Please run myrm stop before deploy") is True

    def test_allows_normal_prompt(self) -> None:
        assert contains_myrm_lifecycle_command("Summarize today's AI news.") is False

    def test_assert_rejects_restart_in_prompt(self) -> None:
        with pytest.raises(ValueError, match="lifecycle commands"):
            assert_cron_job_lifecycle_safe(prompt="Run ./myrm restart nightly", command=None)

    def test_assert_rejects_restart_in_command(self) -> None:
        with pytest.raises(ValueError, match="lifecycle commands"):
            assert_cron_job_lifecycle_safe(prompt=None, command="myrm restart")


class TestToolsPolicy:
    def test_normalize_empty_means_unrestricted(self) -> None:
        assert normalize_cron_tools_allowed(None) is None
        assert normalize_cron_tools_allowed([]) is None

    def test_normalize_strips_cron_and_validates(self) -> None:
        assert normalize_cron_tools_allowed(["web_search", "cron"]) == ("web_search",)

    def test_normalize_rejects_unknown(self) -> None:
        with pytest.raises(InvalidBuiltinToolIdsError):
            normalize_cron_tools_allowed(["not_a_real_tool"])

    def test_intersect_restricts_agent_tools(self) -> None:
        agent_tools = ["web_search", "memory", "wiki", "cron"]
        result = intersect_cron_enabled_builtin_tools(agent_tools, ("web_search",))
        assert result == ["web_search"]

    def test_intersect_none_keeps_agent_tools_without_cron(self) -> None:
        agent_tools = ["web_search", "memory", "cron"]
        result = intersect_cron_enabled_builtin_tools(agent_tools, None)
        assert result == ["web_search", "memory"]
