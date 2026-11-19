"""Tests that skill_market_tool is NOT created by get_meta_tools (server/user_tools SSOT)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.meta_tools import get_meta_tools
from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.tool_management.registry import ToolRegistry


@pytest.fixture
def skill_backend() -> MagicMock:
    return MagicMock()


class TestSkillMarketNotInGetMetaTools:
    def test_skill_market_not_returned_by_get_meta_tools(
        self,
        skill_backend: MagicMock,
    ) -> None:
        registry = ToolRegistry()
        tools = get_meta_tools(
            [],
            skill_backend,
            registry=registry,
            file_access_mode=FileAccessMode.NONE,
            enable_shell_tools=False,
            enable_answer_tool=False,
        )

        returned_names = {t.name for t in tools}
        assert "skill_market_tool" not in returned_names
        assert "skill_manage_tool" not in returned_names
