"""Derive harness canonical tool groups from GeneralAgent enable flags.

[INPUT]
- GeneralAgent boolean flags and media params (POS: product-layer entitlement)

[OUTPUT]
- derive_active_tool_groups: list of TOOL_GROUP_MAP keys for Gap SSOT + skill filtering
- ACTIVE_TOOL_GROUP_KEYS: stable key tuple for architecture tests

[POS]
Server SSOT mapping user entitlement → harness ``active_tool_groups`` passed to
``sync_discover_capability_tool`` and ``AgentRuntimeSpec.tool_groups``.
"""

from __future__ import annotations

from typing import Protocol


class ActiveToolGroupSource(Protocol):
    enable_web_search: bool
    enable_browser: bool
    enable_file_ops: bool
    enable_code_execute: bool
    enable_computer_use: bool
    enable_memory: bool
    enable_kanban: bool
    enable_canvas: bool
    enable_wiki: bool
    enable_answer_tool: bool
    enable_render_ui: bool
    image_generation_params: object | None
    video_generation_params: object | None
    tts_params: object | None


ACTIVE_TOOL_GROUP_KEYS: tuple[str, ...] = (
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
    "answer_tool",
    "render_ui",
    "image_generation",
    "video_generation",
    "tts",
)


def derive_active_tool_groups(
    agent: ActiveToolGroupSource,
    *,
    enable_planning: bool,
) -> list[str]:
    """Map GeneralAgent flags to harness TOOL_GROUP_MAP group names."""
    flag_to_group: list[tuple[str, bool]] = [
        ("web", agent.enable_web_search),
        ("browser", agent.enable_browser),
        ("file_ops", agent.enable_file_ops),
        ("shell", agent.enable_code_execute),
        ("computer_use", agent.enable_computer_use),
        ("memory", agent.enable_memory),
        ("kanban", agent.enable_kanban),
        ("canvas", agent.enable_canvas),
        ("wiki", agent.enable_wiki),
        ("planning", enable_planning),
        ("answer_tool", agent.enable_answer_tool),
        ("render_ui", agent.enable_render_ui),
        ("image_generation", agent.image_generation_params is not None),
        ("video_generation", agent.video_generation_params is not None),
        ("tts", agent.tts_params is not None),
    ]
    return [group for group, enabled in flag_to_group if enabled]
