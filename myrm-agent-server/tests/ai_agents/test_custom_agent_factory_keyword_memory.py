"""Custom subagents get a memory manager on an install without an embedding model.

[INPUT]
app.ai_agents.custom_agent_factory::CustomAgentFactory.build (POS: subagent construction, memory section)

[OUTPUT]
A subagent whose isolation policy allows memory receives a keyword-mode manager when the
retrieval settings carry no embedding.

[POS]
Regression guard for the memory gate of the subagent factory: embedding is optional, so its
absence never removes memory from a subagent.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig

from app.ai_agents.custom_agent_factory import CustomAgentFactory


@pytest.mark.asyncio
async def test_subagent_receives_a_keyword_mode_memory_manager_without_an_embedding(monkeypatch) -> None:
    profile = SimpleNamespace(
        display_name="Keyword Researcher",
        skills=[],
        enabled_builtin_tools=(),
        max_iterations=8,
        memory_policy=None,
        metadata={},
    )
    factory = CustomAgentFactory(agent_id="custom-keyword", agent_profile=profile)
    factory._initialized = True

    manager = SimpleNamespace(approval_required=False)
    create_manager = AsyncMock(return_value=manager)
    received: dict[str, object] = {}

    async def fake_create_skill_agent(**kwargs: object) -> SimpleNamespace:
        received["memory_manager"] = kwargs.get("memory_manager")
        return SimpleNamespace()

    import myrm_agent_harness.api as api_module

    monkeypatch.setattr(api_module, "create_skill_agent", fake_create_skill_agent)
    monkeypatch.setattr("app.core.memory.adapters.setup.create_memory_manager", create_manager)
    monkeypatch.setattr(
        "app.services.agent.platform_config.load_platform_retrieval_configs",
        AsyncMock(return_value=(None, None)),
    )
    monkeypatch.setattr(
        "app.services.memory.extract_retry.resolve_chat_extraction_llm.get_platform_dedup_llm",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("app.platform_utils.get_storage_provider", lambda: SimpleNamespace())

    parent = SimpleNamespace(
        llm=SimpleNamespace(),
        executor=None,
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-keyword"},
    )
    config = SubagentConfig(
        display_name="Researcher",
        system_prompt="You research.",
        memory_isolation=MemoryIsolationPolicy.COLLABORATIVE_SESSION,
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    create_manager.assert_awaited_once()
    assert create_manager.await_args.kwargs["embedding_config"] is None
    assert received["memory_manager"] is manager
