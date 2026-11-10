"""Subagent presets of MyrmAgent (Business Layer).

Loads the preset YAML files in app/config/subagents/ into ``SubagentConfig`` objects.

Configuration Architecture:
- Framework layer (myrm-agent-harness): Provides loading mechanism (pure functions)
- Business layer (myrm-agent-server): Provides configuration content and policy

Configuration Priority:
1. custom/*.yaml overrides core/*.yaml
2. Per-agent values defined in each YAML ``config:`` block
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.agent.sub_agents.config_loader import load_subagent_configs_from_directory
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

SUBAGENT_CONFIG_DIR = Path(__file__).parent.parent / "config" / "subagents"

# User-facing catalog. The ids are deliberately explicit: an internal cron verifier preset must
# never leak into the Agent editor just because it lives in the same YAML directory.
USER_SELECTABLE_SUBAGENT_IDS: tuple[str, ...] = (
    "structure-planner",
    "layout-designer",
    "format-verifier",
    "browser",
    "explore",
)


def load_subagent_presets() -> dict[str, SubagentConfig]:
    """Load every preset YAML: ``custom/`` entries override ``core/`` entries of the same id.

    ``core/`` ships with the app; ``custom/`` is optional and skipped when absent.
    """
    presets = load_subagent_configs_from_directory(SUBAGENT_CONFIG_DIR / "core")
    custom_dir = SUBAGENT_CONFIG_DIR / "custom"
    if custom_dir.is_dir():
        presets.update(load_subagent_configs_from_directory(custom_dir))
    return presets


def load_user_selectable_subagent_configs() -> dict[str, SubagentConfig]:
    """Return the business-owned catalog exposed in the Agent editor.

    Reads the same core/custom YAML sources as the catalog, so a custom override is
    reflected in the picker without a second catalog implementation.
    """
    configs = load_subagent_presets()
    return {type_id: configs[type_id] for type_id in USER_SELECTABLE_SUBAGENT_IDS if type_id in configs}


def required_builtin_tools(config: SubagentConfig) -> tuple[str, ...]:
    """Built-in tool toggles a preset needs in the parent Agent to be effective.

    Browser presets receive the parent's browser_* tools through the normal child/parent tool
    intersection; exposing the preset while Browser is off would build a child with no tools.
    """
    if any(tool_name.startswith("browser_") for tool_name in config.tools):
        return ("browser",)
    return ()
