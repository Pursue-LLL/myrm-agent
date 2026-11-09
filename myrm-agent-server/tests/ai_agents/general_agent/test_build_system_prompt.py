"""The system prompt carries the desktop control rules exactly when computer use tools are mounted.

[INPUT]
- app/ai_agents/general_agent/factory/prompt.py::build_system_prompt (POS: unit under test, executed for real)

[OUTPUT]
- Tests that the desktop control rules follow the computer use mount and are the same English text for every locale.

[POS]
The rules are a tool-call protocol injected by the mount plan; this pins the wiring between the plan and the prompt.
"""

from __future__ import annotations

import pytest

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.ai_agents.general_agent.factory.prompt import build_system_prompt
from app.ai_agents.general_agent.mount_resolver import ResolvedMountPlan
from app.ai_agents.prompts.shared_rules import DESKTOP_CONTROL_RULES
from app.core.types.business import ModelConfig


def _build(*, computer_use: bool, locale: str | None) -> str:
    wrapper = AgentFactory.create_general_agent(
        GeneralAgentParams(
            model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
            query="assemble the prompt",
            chat_id="system-prompt-chat",
            enable_browser=False,
            prompt_mode="full",
        )
    )
    plan = ResolvedMountPlan(mount_browser=False, mount_computer_use=computer_use, mount_widget_capability=False)
    return build_system_prompt(wrapper, mount_plan=plan, channel_notify_tool_loaded=False, prompt_locale=locale)


@pytest.mark.parametrize("locale", [None, "zh-CN"])
def test_the_desktop_control_rules_are_appended_exactly_when_computer_use_is_mounted(locale: str | None) -> None:
    assert DESKTOP_CONTROL_RULES in _build(computer_use=True, locale=locale)
    assert DESKTOP_CONTROL_RULES not in _build(computer_use=False, locale=locale)
