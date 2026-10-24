"""Vertical Persona Presets and Sub-Bot Sandbox Tester package.

[INPUT]
- Subagent role definitions, test requests, agent-to-agent interaction flow steps.

[OUTPUT]
- VerticalRolePreset catalog, sandbox test runner, agent flow inspector with loop detection.

[POS]
- Harness orchestration layer for enterprise-ready specialist agent personas.
"""

from myrm_agent_harness.agent.sub_agents.vertical_presets.presets_catalog import (
    BUILTIN_PRESETS,
    PresetsCatalog,
)
from myrm_agent_harness.agent.sub_agents.vertical_presets.sandbox_tester import (
    AgentFlowInspector,
    SubBotSandboxTester,
)
from myrm_agent_harness.agent.sub_agents.vertical_presets.types import (
    AgentFlowStep,
    AgentFlowTrace,
    ReasoningEffort,
    SubBotTestRequest,
    SubBotTestResult,
    VerticalRoleCategory,
    VerticalRolePreset,
)

__all__ = [
    "AgentFlowInspector",
    "AgentFlowStep",
    "AgentFlowTrace",
    "BUILTIN_PRESETS",
    "PresetsCatalog",
    "ReasoningEffort",
    "SubBotSandboxTester",
    "SubBotTestRequest",
    "SubBotTestResult",
    "VerticalRoleCategory",
    "VerticalRolePreset",
]
