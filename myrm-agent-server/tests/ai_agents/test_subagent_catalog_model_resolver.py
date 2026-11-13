"""A preset that names a model runs on that model, not on the delegating agent's.

The harness hands a model resolver its routing hints as keywords and, when the resolver raises, runs the sub-agent on
the delegating agent's model with only a log line. These tests resolve the model the way the harness does, through the
resolver the catalog injects.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.sub_agents.builder import resolve_llm
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig
from myrm_agent_harness.toolkits.llms import llm_manager

from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

PRESET_ID = "researcher-preset"
PRESET_MODEL = "openai/gpt-4o-mini"
PARENT_LLM = SimpleNamespace(name="parent-llm")
PRESET_LLM = SimpleNamespace(name="preset-llm")


@pytest.fixture
def provider_lookup(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """The user's provider config and the model construction, stubbed at the two places the resolver reaches out to."""
    configs = SimpleNamespace(providers_dict={"providers": []})
    resolve_model_config = MagicMock(return_value=SimpleNamespace(api_keys=["key"]))
    monkeypatch.setattr("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=configs))
    monkeypatch.setattr("app.core.channel_bridge.model_resolver.resolve_model_config", resolve_model_config)
    monkeypatch.setattr(llm_manager, "get_llm_from_config", AsyncMock(return_value=PRESET_LLM))
    return resolve_model_config


def _catalog_with_preset(monkeypatch: pytest.MonkeyPatch, preset: SubagentConfig) -> DatabaseSubagentCatalog:
    monkeypatch.setattr("app.ai_agents.subagent_catalog.load_subagent_presets", lambda: {PRESET_ID: preset})
    return DatabaseSubagentCatalog(bound_agent_ids=[PRESET_ID])


@pytest.mark.asyncio
async def test_a_preset_that_names_a_model_is_resolved_to_that_model_when_the_harness_builds_the_agent(
    monkeypatch: pytest.MonkeyPatch, provider_lookup: MagicMock
) -> None:
    catalog = _catalog_with_preset(monkeypatch, SubagentConfig(system_prompt="Research.", model=PRESET_MODEL))

    config = await catalog.resolve(PRESET_ID)
    assert config is not None
    llm = await resolve_llm(config, SimpleNamespace(llm=PARENT_LLM), complexity_tier="standard", task_description="Find sources")

    assert llm is PRESET_LLM
    assert provider_lookup.call_args.kwargs["model_override"] == PRESET_MODEL


@pytest.mark.asyncio
async def test_a_preset_without_a_model_keeps_the_delegating_agents_model(
    monkeypatch: pytest.MonkeyPatch, provider_lookup: MagicMock
) -> None:
    catalog = _catalog_with_preset(monkeypatch, SubagentConfig(system_prompt="Research."))

    config = await catalog.resolve(PRESET_ID)
    assert config is not None
    llm = await resolve_llm(config, SimpleNamespace(llm=PARENT_LLM))

    assert llm is PARENT_LLM
    provider_lookup.assert_not_called()
