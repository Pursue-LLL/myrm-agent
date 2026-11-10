"""The system prompt carries the desktop control rules exactly when computer use tools are mounted, whichever model runs.

[INPUT]
- app/ai_agents/general_agent/factory/prompt.py::build_system_prompt (POS: unit under test, executed for real)

[OUTPUT]
- Tests that the desktop control rules follow the computer use mount and are the same English text for every locale.
- Tests that a small model or a small context window leaves the prompt mode, engine params and prompt of an agent as
  they are for a strong model.

[POS]
The rules are a tool-call protocol injected by the mount plan; this pins the wiring between the plan and the prompt.
An agent behaves as its own settings say; the model that runs it never reshapes it.
"""

from __future__ import annotations

import pytest

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.ai_agents.general_agent.agent import GeneralAgent
from app.ai_agents.general_agent.factory.prompt import build_system_prompt
from app.ai_agents.general_agent.mount_resolver import ResolvedMountPlan
from app.ai_agents.prompts.shared_rules import DESKTOP_CONTROL_RULES
from app.core.types.business import ModelConfig

_STRONG_MODEL = ModelConfig(model="gpt-4o", api_key="test-key")
_SMALL_MODELS = [
    ModelConfig(model="gpt-4o-mini", api_key="test-key"),
    ModelConfig(model="gemini-2.0-flash", api_key="test-key"),
    ModelConfig(model="qwen2.5:7b", api_key="test-key"),
    ModelConfig(model="llama3-8b", api_key="test-key"),
    ModelConfig(model="gpt-4o", api_key="test-key", max_context_tokens=8_192),
    ModelConfig(model="gpt-4o", api_key="test-key", max_context_tokens=32_768),
]


def _create_wrapper(model_cfg: ModelConfig) -> GeneralAgent:
    return AgentFactory.create_general_agent(
        GeneralAgentParams(
            model_cfg=model_cfg,
            query="assemble the prompt",
            chat_id="system-prompt-chat",
            enable_browser=False,
            prompt_mode="full",
        )
    )


def _build(*, computer_use: bool, locale: str | None, model_cfg: ModelConfig = _STRONG_MODEL) -> str:
    wrapper = _create_wrapper(model_cfg)
    plan = ResolvedMountPlan(mount_browser=False, mount_computer_use=computer_use, mount_widget_capability=False)
    return build_system_prompt(wrapper, mount_plan=plan, channel_notify_tool_loaded=False, prompt_locale=locale)


@pytest.mark.parametrize("locale", [None, "zh-CN"])
def test_the_desktop_control_rules_are_appended_exactly_when_computer_use_is_mounted(locale: str | None) -> None:
    assert DESKTOP_CONTROL_RULES in _build(computer_use=True, locale=locale)
    assert DESKTOP_CONTROL_RULES not in _build(computer_use=False, locale=locale)


@pytest.mark.parametrize(
    "model_cfg",
    _SMALL_MODELS,
    ids=[f"{cfg.model}-{cfg.max_context_tokens}" for cfg in _SMALL_MODELS],
)
@pytest.mark.parametrize("locale", [None, "zh-CN"])
def test_a_small_model_gets_the_same_agent_as_a_strong_one(model_cfg: ModelConfig, locale: str | None) -> None:
    reference = _create_wrapper(_STRONG_MODEL)
    wrapper = _create_wrapper(model_cfg)

    assert wrapper.prompt_mode == "full"
    assert wrapper.engine_params == reference.engine_params
    assert _build(computer_use=True, locale=locale, model_cfg=model_cfg) == _build(computer_use=True, locale=locale)
