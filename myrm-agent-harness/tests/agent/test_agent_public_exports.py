"""Sub-agent names advertised by the lazy ``agent`` facade must resolve to their defining objects.

[INPUT]
- myrm_agent_harness.agent: the lazy public facade
- agent.sub_agents.types / core.events.types: where the names are defined

[OUTPUT]
- Regression guard for facade entries that point at a module which does not define the name.

[POS]
Unit tests mirroring src/myrm_agent_harness/agent/__init__.py (sub-agent domain entries).
"""

from __future__ import annotations

import pytest

import myrm_agent_harness.agent as agent_pkg
from myrm_agent_harness.agent.sub_agents import types as sub_agent_types
from myrm_agent_harness.core.events.types import AgentEventType

_SUBAGENT_FACADE_TARGETS: dict[str, object] = {
    "SubagentConfig": sub_agent_types.SubagentConfig,
    "SubAgentStatus": sub_agent_types.SubAgentStatus,
    "SubAgentResult": sub_agent_types.SubAgentResult,
    "AgentEventType": AgentEventType,
}


@pytest.mark.parametrize("name", sorted(_SUBAGENT_FACADE_TARGETS))
def test_subagent_facade_name_resolves_to_defining_object(name: str) -> None:
    assert getattr(agent_pkg, name) is _SUBAGENT_FACADE_TARGETS[name]


def test_subagent_facade_names_are_advertised_in_all() -> None:
    assert set(_SUBAGENT_FACADE_TARGETS) <= set(agent_pkg.__all__)
