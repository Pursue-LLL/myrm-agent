"""Materializes JIT subagent configurations from ephemeral dictionary data.

Parses frontend-provided dict[str, object] into SubagentConfig objects
ready to be injected into the DatabaseSubagentCatalog.

[INPUT]
- ai_agents.custom_agent_factory::EphemeralAgentFactory (POS: Business-layer factory that constructs ephemeral user agents)
- myrm_agent_harness.agent.sub_agents.types::SubagentConfig (POS: Subagent subsystem core type definitions. Defines all subagent-related data types, enums, and protocols.)

[OUTPUT]
- materialize_jit_configs(): Converts frontend ephemeral subagent dictionaries into validated Harness SubagentConfig objects.

[POS]
Single-machine business adapter. Translates user-agent blueprint data into Harness subagent configuration without leaking frontend or database concerns into Harness.
"""

import logging
from collections.abc import Mapping, Sequence

from myrm_agent_harness.agent.sub_agents.types import ControlScope, MemoryIsolationPolicy, SubagentConfig

from app.ai_agents.custom_agent_factory import EphemeralAgentFactory

logger = logging.getLogger(__name__)


def _string_field(data: Mapping[str, object], key: str, default: str = "") -> str:
    value = data.get(key)
    return value if isinstance(value, str) else default


def _optional_string_field(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) else None


def _int_field(data: Mapping[str, object], key: str, default: int) -> int:
    value = data.get(key)
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _tools_field(data: Mapping[str, object]) -> tuple[str, ...]:
    value = data.get("tools")
    if isinstance(value, str) or not isinstance(value, Sequence):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _memory_policy(data: Mapping[str, object]) -> MemoryIsolationPolicy:
    raw_value = _string_field(data, "memory_isolation", MemoryIsolationPolicy.COLLABORATIVE_SESSION.value)
    try:
        return MemoryIsolationPolicy(raw_value)
    except ValueError:
        return MemoryIsolationPolicy.COLLABORATIVE_SESSION


def _control_scope(data: Mapping[str, object]) -> ControlScope:
    raw_value = _string_field(data, "control_scope", ControlScope.LEAF.value)
    try:
        return ControlScope(raw_value)
    except ValueError as error:
        allowed = ", ".join(scope.value for scope in ControlScope)
        raise ValueError(f"Invalid control_scope value '{raw_value}'. Allowed: {allowed}") from error


def materialize_jit_configs(
    raw_configs: Mapping[str, object] | None,
) -> dict[str, SubagentConfig]:
    """Parse ephemeral subagents dictionary into SubagentConfig instances.

    Args:
        raw_configs: Dictionary from frontend, e.g.,
            {
                "researcher": {
                    "display_name": "Researcher",
                    "system_prompt": "You are a researcher.",
                    "model": "gpt-4o",
                    "tools": ["web_search", "read_file"]
                }
            }

    Returns:
        Dictionary of validated SubagentConfig instances mapping type_id -> config.
    """
    if not raw_configs:
        return {}

    configs: dict[str, SubagentConfig] = {}

    for type_id, data in raw_configs.items():
        if not isinstance(data, Mapping):
            logger.warning(f"Skipping invalid ephemeral subagent config for '{type_id}'")
            continue

        try:
            tools = _tools_field(data)
            memory_policy = _memory_policy(data)
            control_scope = _control_scope(data)
            factory = EphemeralAgentFactory(agent_id=type_id)

            context_mode_str = _string_field(data, "context_mode", "isolated")
            context_mode = "fork" if context_mode_str == "fork" else "isolated"
            max_fork_tokens = data.get("max_fork_tokens")
            if max_fork_tokens is not None:
                try:
                    max_fork_tokens = int(max_fork_tokens)
                except (TypeError, ValueError):
                    max_fork_tokens = None
            max_spawn_depth = 0
            if control_scope == ControlScope.ORCHESTRATOR:
                max_spawn_depth = max(1, _int_field(data, "max_spawn_depth", 1))

            configs[type_id] = SubagentConfig(
                system_prompt=_string_field(data, "system_prompt"),
                description=_string_field(data, "description"),
                display_name=_string_field(data, "display_name", type_id),
                theme_color=_string_field(data, "theme_color"),
                model=_optional_string_field(data, "model"),
                tools=tools,
                max_turns=_int_field(data, "max_turns", 25),
                max_children_per_agent=_int_field(data, "max_children_per_agent", 5),
                max_descendants_per_run=_int_field(data, "max_descendants_per_run", 20),
                max_batch_size=_int_field(data, "max_batch_size", 5),
                control_scope=control_scope,
                memory_isolation=memory_policy,
                context_mode=context_mode,
                max_fork_tokens=max_fork_tokens,
                max_spawn_depth=max_spawn_depth,
                agent_factory=factory,
            )
        except Exception as e:
            logger.warning(f"Failed to materialize ephemeral subagent '{type_id}': {e}")
            continue

    return configs
