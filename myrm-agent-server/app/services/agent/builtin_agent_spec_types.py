"""Built-in agent spec types and tool-set constants.

[INPUT]
app.services.agent.builtin_tool_ids::DEFAULT_ENABLED_BUILTIN_TOOLS (POS: enabled_builtin_tools SSOT)

[OUTPUT]
_BuiltInAgentSpec, _TOOL_* presets for builtin agent data modules.

[POS]
builtin_agent_specs 子模块：类型与工具集常量 SSOT。
"""

from dataclasses import dataclass, field

from app.services.agent.builtin_tool_ids import DEFAULT_ENABLED_BUILTIN_TOOLS


def _extend_default_tools(*extra: str) -> tuple[str, ...]:
    """Append extra togglable tool IDs after DEFAULT_ENABLED_BUILTIN_TOOLS (deduped, stable order)."""
    ordered = list(DEFAULT_ENABLED_BUILTIN_TOOLS)
    seen = set(ordered)
    for tool_id in extra:
        if tool_id not in seen:
            ordered.append(tool_id)
            seen.add(tool_id)
    return tuple(ordered)


_TOOL_MINIMAL: tuple[str, ...] = DEFAULT_ENABLED_BUILTIN_TOOLS
_TOOL_DEFAULT: tuple[str, ...] = _extend_default_tools("external_cli")
_TOOL_CODING: tuple[str, ...] = _TOOL_DEFAULT
_TOOL_RESEARCH: tuple[str, ...] = _extend_default_tools("answer_tool")
_TOOL_DESIGN: tuple[str, ...] = _extend_default_tools("image_generation")


@dataclass(frozen=True)
class _BuiltInAgentSpec:
    """Built-in agent specification (business layer definition)."""

    id: str
    name: str
    description: str
    icon_id: str
    personality_style: str
    system_prompt: str
    default_skill_ids: tuple[str, ...] = ()
    enabled_builtin_tools: tuple[str, ...] | None = None
    prompt_mode: str = "full"
    engine_params: dict[str, object] | None = field(default=None, compare=False)
    memory_policy: dict[str, object] | None = field(default=None, compare=False)
    suggestion_prompts: tuple[str, ...] = ()

