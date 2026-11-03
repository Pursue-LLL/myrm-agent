"""How ``create_skill_agent`` turns an ``LLMConfig`` and a privacy-routing config into the chat models it hands the agent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.agent._factory.builder import create_skill_agent
from myrm_agent_harness.agent.types import AgentRuntimeSpec
from myrm_agent_harness.core.config.llm import LLMConfig
from myrm_agent_harness.core.security.types import PrivacyRoutingConfig
from myrm_agent_harness.toolkits.llms import create_chat_model
from myrm_agent_harness.toolkits.llms.core.llm import TransportChatModel
from myrm_agent_harness.toolkits.llms.routing import PrivacyRoutingModel

_SPEC = AgentRuntimeSpec(agent_id="agent-llm-construction", name="llm-construction", system_prompt="test")


async def _llm_given_to_the_agent(**kwargs: object) -> object:
    with patch("myrm_agent_harness.agent.skill_agent.SkillAgent") as skill_agent:
        skill_agent.return_value = MagicMock()
        await create_skill_agent(spec=_SPEC, executor=MagicMock(), **kwargs)  # type: ignore[arg-type]
    return skill_agent.call_args.kwargs["llm"]


@pytest.mark.asyncio
async def test_an_llm_config_becomes_a_chat_model_carrying_every_setting() -> None:
    config = LLMConfig(
        model="openai/gpt-4o",
        api_key="sk-test",
        base_url="https://gateway.example/v1",
        temperature=0.3,
        streaming=False,
        model_kwargs={"max_tokens": 321},
        egress_proxy="http://127.0.0.1:7890",
    )

    with patch("myrm_agent_harness.toolkits.llms.create_chat_model", return_value="chat-model") as factory:
        llm = await _llm_given_to_the_agent(llm_config=config)

    assert llm == "chat-model"
    factory.assert_called_once_with(
        model="openai/gpt-4o",
        api_key="sk-test",
        base_url="https://gateway.example/v1",
        streaming=False,
        max_tokens=321,
        temperature=0.3,
        egress_proxy="http://127.0.0.1:7890",
    )


@pytest.mark.asyncio
async def test_settings_the_config_does_not_set_are_left_to_the_factory_defaults() -> None:
    with patch("myrm_agent_harness.toolkits.llms.create_chat_model", return_value="chat-model") as factory:
        await _llm_given_to_the_agent(llm_config=LLMConfig(model="openai/gpt-4o", api_key="sk-test"))

    sent = factory.call_args.kwargs
    assert "temperature" not in sent
    assert "egress_proxy" not in sent
    assert sent["streaming"] is True
    assert sent["base_url"] is None


@pytest.mark.asyncio
async def test_a_real_llm_config_yields_a_transport_chat_model_for_the_model_it_names() -> None:
    llm = await _llm_given_to_the_agent(llm_config=LLMConfig(model="anthropic/claude-sonnet-4-5", api_key="sk-test"))

    assert isinstance(llm, TransportChatModel)
    assert llm.model == "anthropic/claude-sonnet-4-5"


@pytest.mark.asyncio
async def test_neither_a_model_nor_a_config_is_a_clear_error() -> None:
    with pytest.raises(ValueError, match="Must provide either 'llm_config' or 'llm'"):
        await create_skill_agent(spec=_SPEC, executor=MagicMock())


@pytest.mark.asyncio
async def test_privacy_routing_adds_a_local_model_next_to_the_cloud_one() -> None:
    cloud = create_chat_model(model="openai/gpt-4o", api_key="sk-test")
    routing = PrivacyRoutingConfig(
        local_model="ollama/llama3.1", local_base_url="http://localhost:11434", local_api_key="local-key"
    )

    with patch("myrm_agent_harness.toolkits.llms.create_chat_model", wraps=create_chat_model) as factory:
        llm = await _llm_given_to_the_agent(llm=cloud, privacy_routing_config=routing)

    assert isinstance(llm, PrivacyRoutingModel)
    assert llm.cloud_llm is cloud
    assert isinstance(llm.local_llm, TransportChatModel)
    assert llm.local_llm.model == "ollama/llama3.1"
    assert llm.routing_config is routing
    factory.assert_called_once_with(
        model="ollama/llama3.1",
        base_url="http://localhost:11434",
        api_key="local-key",
        temperature=0.2,
        streaming=True,
    )


@pytest.mark.asyncio
async def test_a_local_model_without_a_key_is_built_with_an_empty_one_not_the_cloud_key() -> None:
    cloud = create_chat_model(model="openai/gpt-4o", api_key="sk-cloud")
    routing = PrivacyRoutingConfig(local_model="ollama/llama3.1")

    with patch("myrm_agent_harness.toolkits.llms.create_chat_model", wraps=create_chat_model) as factory:
        await _llm_given_to_the_agent(llm=cloud, privacy_routing_config=routing)

    assert factory.call_args.kwargs["api_key"] == ""


@pytest.mark.asyncio
async def test_without_a_local_model_the_cloud_model_is_used_as_given() -> None:
    cloud = create_chat_model(model="openai/gpt-4o", api_key="sk-test")

    llm = await _llm_given_to_the_agent(llm=cloud, privacy_routing_config=PrivacyRoutingConfig())

    assert llm is cloud
