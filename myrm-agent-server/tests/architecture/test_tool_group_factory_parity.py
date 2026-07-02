"""Architecture test: factory active tool groups ⊆ TOOL_GROUP_MAP."""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.tool_registry import TOOL_GROUP_MAP, TOOL_GROUP_NAMES

# Mirrors general_agent/factory.py _flag_to_group keys (server product groups).
_FACTORY_ACTIVE_TOOL_GROUPS: tuple[str, ...] = (
    "web",
    "browser",
    "file_ops",
    "shell",
    "computer_use",
    "memory",
    "kanban",
    "canvas",
    "wiki",
    "planning",
    "task_tracking",
    "answer_tool",
)


@pytest.mark.architecture
def test_factory_groups_are_registered_in_tool_group_map() -> None:
    missing = [group for group in _FACTORY_ACTIVE_TOOL_GROUPS if group not in TOOL_GROUP_MAP]
    assert missing == [], f"TOOL_GROUP_MAP missing factory groups: {missing}"


@pytest.mark.architecture
def test_tool_group_names_matches_map_keys() -> None:
    assert TOOL_GROUP_NAMES == frozenset(TOOL_GROUP_MAP.keys())


@pytest.mark.architecture
def test_media_groups_include_server_tools() -> None:
    assert "image_tool" in TOOL_GROUP_MAP["image_generation"]
    assert "video_tool" in TOOL_GROUP_MAP["video_generation"]
    assert "tts_generate" in TOOL_GROUP_MAP["tts"]


@pytest.mark.architecture
def test_browser_group_includes_script_and_human_tools() -> None:
    browser_tools = TOOL_GROUP_MAP["browser"]
    assert "browser_execute_script_tool" in browser_tools
    assert "browser_ask_human_tool" in browser_tools
