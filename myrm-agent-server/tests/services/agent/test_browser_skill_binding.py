"""Tests for browser-automation peripheral skill auto-binding."""

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.browser_skill_binding import (
    BROWSER_AUTOMATION_SKILL_ID,
    apply_browser_automation_skill_binding,
)

_MODEL_CFG = ModelConfig(model="test/model", api_key="test-key")


def test_apply_browser_automation_skill_when_enabled() -> None:
    ids, configs = apply_browser_automation_skill_binding(
        ["deep-research"],
        {"deep-research": {"is_core": True}},
        enable_browser=True,
    )
    assert BROWSER_AUTOMATION_SKILL_ID in ids
    assert configs is not None
    assert configs[BROWSER_AUTOMATION_SKILL_ID]["is_core"] is False


def test_apply_browser_automation_skill_skipped_when_disabled() -> None:
    ids, configs = apply_browser_automation_skill_binding(
        ["deep-research"],
        {"deep-research": {"is_core": True}},
        enable_browser=False,
    )
    assert ids == ["deep-research"]
    assert configs == {"deep-research": {"is_core": True}}


def test_apply_browser_automation_skill_idempotent() -> None:
    ids, configs = apply_browser_automation_skill_binding(
        [BROWSER_AUTOMATION_SKILL_ID],
        {BROWSER_AUTOMATION_SKILL_ID: {"is_core": False}},
        enable_browser=True,
    )
    assert ids.count(BROWSER_AUTOMATION_SKILL_ID) == 1
    assert configs is not None
    assert configs[BROWSER_AUTOMATION_SKILL_ID]["is_core"] is False


def test_agent_factory_binds_browser_skill_for_cron_path() -> None:
    """Regression: skill binding must run in AgentFactory (Cron/Channel/Kanban paths)."""
    agent = AgentFactory.create_general_agent(
        GeneralAgentParams(
            query="export daily report",
            model_cfg=_MODEL_CFG,
            enable_browser=True,
            channel_name="cron",
            prompt_mode="full",
            agent_skill_ids=["deep-research"],
            agent_skill_configs={"deep-research": {"is_core": True}},
        )
    )
    assert BROWSER_AUTOMATION_SKILL_ID in agent.skill_ids
    assert agent.skill_configs is not None
    assert agent.skill_configs[BROWSER_AUTOMATION_SKILL_ID]["is_core"] is False


def test_agent_factory_skips_browser_skill_in_search_prompt_mode() -> None:
    agent = AgentFactory.create_general_agent(
        GeneralAgentParams(
            query="quick search",
            model_cfg=_MODEL_CFG,
            enable_browser=True,
            prompt_mode="search",
            agent_skill_ids=[],
            agent_skill_configs=None,
        )
    )
    assert BROWSER_AUTOMATION_SKILL_ID not in agent.skill_ids
