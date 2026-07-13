"""Apply / capture helpers for BuiltExecutionUnit ↔ GeneralAgent wrapper.

[INPUT]
- execution_cache.types::BuiltExecutionUnit (POS: 可复用构建单元)
- app.ai_agents.general_agent.agent::GeneralAgent (POS: 业务 Agent 包装层)

[OUTPUT]
- capture_built_unit, apply_built_unit, detach_wrapper_refs

[POS]
execution_cache 单元操作。在 GeneralAgent 与 BuiltExecutionUnit 间迁移重资源引用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agent.execution_cache.types import BuiltExecutionUnit

if TYPE_CHECKING:
    from myrm_agent_harness.api import SkillAgent

    from app.ai_agents.general_agent.agent import GeneralAgent


def capture_built_unit(agent_wrapper: GeneralAgent, skill_agent: SkillAgent) -> BuiltExecutionUnit:
    return BuiltExecutionUnit(
        skill_agent=skill_agent,
        browser_session=agent_wrapper._browser_session,
        desktop_session=getattr(agent_wrapper, "_desktop_session", None),
        checkpoint_helper=agent_wrapper._checkpoint_helper,
        current_thread_id=agent_wrapper._current_thread_id,
    )


def apply_built_unit(agent_wrapper: GeneralAgent, unit: BuiltExecutionUnit) -> None:
    agent_wrapper.agent = unit.skill_agent
    agent_wrapper._browser_session = unit.browser_session
    if hasattr(agent_wrapper, "_desktop_session"):
        agent_wrapper._desktop_session = unit.desktop_session
    agent_wrapper._checkpoint_helper = unit.checkpoint_helper
    agent_wrapper._current_thread_id = unit.current_thread_id


def detach_wrapper_refs(agent_wrapper: GeneralAgent) -> None:
    """Drop wrapper references without closing pooled resources."""
    agent_wrapper.agent = None
    agent_wrapper._browser_session = None
    if hasattr(agent_wrapper, "_desktop_session"):
        agent_wrapper._desktop_session = None
    agent_wrapper._checkpoint_helper = None
