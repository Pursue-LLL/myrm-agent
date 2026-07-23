"""Derive harness canonical tool groups from GeneralAgent enable flags.

[INPUT]
- GeneralAgent boolean flags and media params (POS: product-layer entitlement)

[OUTPUT]
- derive_active_tool_groups: list of TOOL_GROUP_MAP keys for Gap SSOT + skill filtering
- derive_active_tool_groups_from_params: frozenset adapter for GeneralAgentParams gap preflight
- ACTIVE_TOOL_GROUP_KEYS: stable key tuple for architecture tests
- Catalog parity: test_active_tool_groups asserts gap registry keys match TOGGLABLE_BUILTIN_TOOL_IDS (baseline excluded)

[POS]
Server SSOT mapping user entitlement → harness ``active_tool_groups`` passed to
``sync_discover_capability_tool`` and ``AgentRuntimeSpec.tool_groups``.
``render_ui`` reflects profile entitlement only; Turn1 mount is gated separately in
``tool_setup._should_mount_render_ui_tools`` (WEB_CHAT + web/tauri surface).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Protocol


class ActiveToolGroupSource(Protocol):
    enable_web_search: bool
    enable_web_crawl: bool
    enable_browser: bool
    enable_file_ops: bool
    enable_shell_tools: bool
    enable_computer_use: bool
    enable_memory: bool
    incognito_mode: bool
    enable_conversation_search: bool
    enable_kanban: bool
    enable_wiki: bool
    enable_answer_tool: bool
    enable_render_ui: bool
    enable_structured_clarify: bool
    enable_external_cli: bool
    enable_cron_eager: bool
    image_generation_params: object | None
    video_generation_params: object | None
    tts_params: object | None


ACTIVE_TOOL_GROUP_KEYS: tuple[str, ...] = (
    "web",
    "web_crawl",
    "browser",
    "file_ops",
    "shell",
    "computer_use",
    "memory",
    "conversation_history",
    "kanban",
    "wiki",
    "planning",
    "answer_tool",
    "render_ui",
    "structured_clarify",
    "cron",
    "image_generation",
    "video_generation",
    "tts",
    "external_cli",
)


def derive_active_tool_groups(
    agent: ActiveToolGroupSource,
    *,
    enable_planning: bool,
) -> list[str]:
    """Map GeneralAgent flags to harness TOOL_GROUP_MAP group names."""
    flag_to_group: list[tuple[str, bool]] = [
        ("web", agent.enable_web_search),
        ("web_crawl", agent.enable_web_crawl),
        ("browser", agent.enable_browser),
        ("file_ops", agent.enable_file_ops),
        ("shell", agent.enable_shell_tools),
        ("computer_use", agent.enable_computer_use),
        ("memory", agent.enable_memory and not agent.incognito_mode),
        (
            "conversation_history",
            agent.enable_memory
            and not agent.incognito_mode
            and agent.enable_conversation_search,
        ),
        ("kanban", agent.enable_kanban),
        ("wiki", agent.enable_wiki),
        ("planning", enable_planning),
        ("answer_tool", agent.enable_answer_tool),
        ("render_ui", agent.enable_render_ui),
        ("structured_clarify", agent.enable_structured_clarify),
        ("cron", agent.enable_cron_eager),
        ("image_generation", agent.image_generation_params is not None),
        ("video_generation", agent.video_generation_params is not None),
        ("tts", agent.tts_params is not None),
        ("external_cli", agent.enable_external_cli),
    ]
    return [group for group, enabled in flag_to_group if enabled]


def derive_active_tool_groups_from_params(params: object) -> frozenset[str]:
    """Map ``GeneralAgentParams`` entitlement flags to harness group names for gap preflight."""
    adapter = SimpleNamespace(
        enable_web_search=bool(getattr(params, "enable_web_search", False)),
        enable_web_crawl=bool(getattr(params, "enable_web_crawl", False)),
        enable_browser=bool(getattr(params, "enable_browser", False)),
        enable_file_ops=bool(getattr(params, "enable_file_ops", True)),
        enable_shell_tools=bool(getattr(params, "enable_shell_tools", True)),
        enable_computer_use=bool(getattr(params, "enable_computer_use", False)),
        enable_memory=bool(getattr(params, "enable_memory", True)),
        incognito_mode=bool(getattr(params, "incognito_mode", False)),
        enable_conversation_search=bool(getattr(params, "enable_conversation_search", False)),
        enable_kanban=bool(getattr(params, "enable_kanban", False)),
        enable_wiki=bool(getattr(params, "enable_wiki", False)),
        enable_answer_tool=bool(getattr(params, "enable_answer_tool", False)),
        enable_render_ui=bool(getattr(params, "enable_render_ui", False)),
        enable_structured_clarify=bool(getattr(params, "enable_structured_clarify", False)),
        enable_external_cli=bool(getattr(params, "enable_external_cli", False)),
        enable_cron_eager=bool(getattr(params, "enable_cron_eager", False)),
        image_generation_params=getattr(params, "image_generation", None),
        video_generation_params=getattr(params, "video_generation", None),
        tts_params=getattr(params, "tts", None),
    )
    groups = derive_active_tool_groups(
        adapter,
        enable_planning=bool(getattr(params, "enable_planning", False)),
    )
    return frozenset(groups)
