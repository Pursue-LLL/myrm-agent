"""Subagent configuration registration for MyrmAgent (Business Layer).

Called at application startup to load and register subagent configurations
from YAML files in app/config/subagents/ directory.

Configuration Architecture:
- Framework layer (myrm-agent-harness): Provides loading mechanism (pure functions)
- Business layer (myrm-agent-server): Provides configuration content and policy

Configuration Priority:
1. custom/*.yaml overrides core/*.yaml
2. Per-agent values defined in each YAML ``config:`` block
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.agent.sub_agents.config_loader import load_subagent_configs_from_directory
from myrm_agent_harness.agent.sub_agents.registry import register_subagent_configs

logger = logging.getLogger(__name__)


def register_default_subagent_configs() -> None:
    """Register MyrmAgent's default subagent configurations (Business Layer).

    Architecture:
    1. Business layer explicitly provides configuration directory path
    2. Calls framework layer's pure loading functions
    3. Applies business layer's global configuration policy
    4. Registers final configurations to framework layer's global registry

    Configuration Sources:
    - app/config/subagents/core/    : Core configs (search, browser, analysis, coding)
    - app/config/subagents/custom/  : User-defined configs (override core)

    Priority: custom YAML > core YAML (per-agent tuning in each file's ``config:`` block).

    Error Handling: If loading fails, continues with empty registry and logs error.
    """
    try:
        # 1. Business layer explicitly provides configuration path
        config_dir = Path(__file__).parent.parent / "config" / "subagents"

        # 2. Load configurations from YAML files (Framework layer pure functions)
        core_configs = load_subagent_configs_from_directory(config_dir / "core")
        custom_configs = load_subagent_configs_from_directory(config_dir / "custom")

        # 3. Merge with priority: custom > core
        configs = {**core_configs, **custom_configs}

        # 4. Register to framework layer's global registry (YAML is source of truth)
        register_subagent_configs(configs)

        logger.info("Loaded %d subagent configuration(s) from YAML", len(configs))

        if not configs:
            logger.warning("No subagent configurations loaded - delegate_task will have no available types")

    except Exception as e:
        logger.error("Failed to load subagent configurations: %s", e, exc_info=True)
        logger.warning("Continuing with empty subagent registry")
