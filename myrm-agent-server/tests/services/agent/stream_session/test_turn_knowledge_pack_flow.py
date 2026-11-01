"""Knowledge pack through the turn flow: prewarm cache, per-turn retrieval, run context and Human tail.

[INPUT]
- app.services.agent.execution_cache.prewarm.coordinator::TurnPrewarmCoordinator (POS: focus prewarm + send-path join, real)
- app.services.agent.stream_session.orchestrator_turn_setup::build_turn_extra_context (POS: run context of one turn, real)
- app.services.agent.stream_session.memory_brief::build_memory_brief_snapshot (POS: cached memory brief, real)
- myrm_agent_harness proactive_pack_middleware (POS: Human-tail injection of the pack, real)

[OUTPUT]
- Tests that the pack follows each turn's question, never rides in the cached brief, and reaches the end of the final question.

[POS]
Flow-level contract between the server's per-turn retrieval and the harness middleware that renders it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage
from myrm_agent_harness.toolkits.memory.config import RecallMode

from app.ai_agents.agent_middlewares import PROACTIVE_PACK_CONTEXT_KEY, proactive_pack_middleware
from app.services.agent.execution_cache.prewarm import coordinator as coordinator_module
from app.services.agent.execution_cache.prewarm.coordinator import TurnPrewarmCoordinator
from app.services.agent.stream_session import orchestrator_turn_setup as setup
from tests.support.knowledge_pack_vaults import make_vault

if TYPE_CHECKING:
    from app.ai_agents import GeneralAgentParams
    from app.services.agent.params import AgentRequest

CHAT_ID = "chat-pack-flow"
_PAGES = {
    "Hotel Limits": "---\ntype: concept\n---\n## Compiled Truth\nZephyr budget limit: hotel stays in Berlin are capped at 120 per night.\n",
    "Flight Rules": "---\ntype: concept\n---\n## Compiled Truth\nQuartz flight policy: economy class only, booked two weeks ahead.\n",
}


def _params(query: str, **overrides: object) -> GeneralAgentParams:
    fields: dict[str, object] = {
        "chat_id": CHAT_ID,
        "agent_id": "default",
        "query": query,
        "enable_memory": True,
        "incognito_mode": False,
        "embedding_config": object(),
        "memory_conversation_id": CHAT_ID,
        "memory_channel_id": None,
        "channel_name": None,
        "memory_task_id": None,
        "memory_policy": None,
        "memory_require_confirmation": False,
        "memory_shared_context_ids": ["ctx-finance"],
        "memory_shared_context_names": {"ctx-finance": "Finance"},
    }
    fields.update(overrides)
    return cast("GeneralAgentParams", SimpleNamespace(**fields))


def _request(**overrides: object) -> AgentRequest:
    fields: dict[str, object] = {"chat_id": CHAT_ID, "action_mode": "fast", "resume_value": None}
    fields.update(overrides)
    return cast("AgentRequest", SimpleNamespace(**fields))


class _Flow:
    """A real prewarm coordinator and memory brief builder over a real indexed vault."""

    def __init__(self, coordinator: TurnPrewarmCoordinator, memory_manager: MagicMock) -> None:
        self.coordinator = coordinator
        self.memory_manager = memory_manager

    async def focus_prewarm(self) -> None:
        """What opening an empty chat does: the brief is built before any question exists."""
        await self.coordinator.ensure_warming(_params(""), action_mode="fast")
        await asyncio.gather(*self.coordinator._inflight_brief.values())

    async def turn(self, query: str, **param_overrides: object) -> dict[str, object]:
        return await setup.build_turn_extra_context(_request(), _params(query, **param_overrides), base=None, goal_provider=None)


@pytest.fixture
def flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Flow]:
    vault = make_vault(tmp_path, "finance", _PAGES, indexed=True)
    monkeypatch.setattr("app.services.wiki.vault.resolve_shared_wiki_vault_paths", lambda ids, *, must_exist: (vault,))
    monkeypatch.setattr(
        "app.services.wiki.vault.resolve_shared_wiki_vault_labels",
        lambda ids, *, context_name_map: {str(vault): context_name_map[ids[0]]},
    )

    memory_manager = MagicMock()
    memory_manager.get_context = AsyncMock(return_value={"global_profile": {"name": "Ada"}})
    memory_manager.get_learned_context = AsyncMock(return_value={})
    monkeypatch.setattr(
        "app.services.agent.stream_session.memory_brief.create_memory_manager", AsyncMock(return_value=memory_manager)
    )
    monkeypatch.setattr(
        "app.services.agent.stream_session.memory_brief.resolve_context_binding",
        lambda **_: SimpleNamespace(namespaces=("ns-1",)),
    )

    coordinator = TurnPrewarmCoordinator()
    monkeypatch.setattr(coordinator_module, "AgentFactory", MagicMock())
    monkeypatch.setattr(coordinator_module, "compute_execution_fingerprint", lambda wrapper: "fp-1")
    monkeypatch.setattr(coordinator_module, "get_turn_prewarm_coordinator", lambda: coordinator)

    from app.core.channel_bridge import config_loader
    from app.services.agent import runtime_context
    from app.services.memory import ephemeral_delta_hydration

    async def runtime_context_of(*, execution_mode: object, base: dict[str, object] | None = None) -> dict[str, object]:
        return {**(base or {}), "execution_mode": execution_mode}

    monkeypatch.setattr(runtime_context, "build_agent_runtime_context", runtime_context_of)
    monkeypatch.setattr(runtime_context, "resolve_stream_execution_mode", lambda: "desktop")
    monkeypatch.setattr(config_loader, "load_user_configs", AsyncMock(return_value=None))
    monkeypatch.setattr(ephemeral_delta_hydration, "ensure_chat_ephemeral_deltas_hydrated", MagicMock())
    yield _Flow(coordinator, memory_manager)


def _titles(context: dict[str, object]) -> list[str]:
    pack = cast("dict[str, list[dict[str, str]]]", context[PROACTIVE_PACK_CONTEXT_KEY])
    return [snippet["article_title"] for snippet in pack["snippets"]]


async def test_the_first_question_after_a_focus_prewarm_gets_its_pack(flow: _Flow) -> None:
    await flow.focus_prewarm()

    context = await flow.turn("what is the zephyr budget limit for hotels")

    assert _titles(context) == ["Hotel Limits"]
    assert context["memory_brief_status"] == {"state": "ready", "source": "preflight"}


async def test_each_question_gets_its_own_pack_while_the_brief_is_reused(flow: _Flow) -> None:
    await flow.focus_prewarm()

    first = await flow.turn("what is the zephyr budget limit for hotels")
    second = await flow.turn("what is the quartz flight policy")

    assert _titles(first) == ["Hotel Limits"]
    assert _titles(second) == ["Flight Rules"]
    assert flow.memory_manager.get_context.await_count == 1
    assert (
        cast("dict[str, object]", second["memory_brief_snapshot"])["snapshot_id"]
        == (cast("dict[str, object]", first["memory_brief_snapshot"])["snapshot_id"])
    )


async def test_the_cached_brief_carries_no_pack(flow: _Flow) -> None:
    await flow.focus_prewarm()

    context = await flow.turn("what is the zephyr budget limit for hotels")

    snapshot = cast("dict[str, object]", context["memory_brief_snapshot"])
    preview = cast("dict[str, object]", context["memory_brief_preview"])
    assert "proactive_knowledge_pack" not in snapshot
    assert "proactive_knowledge_pack" not in cast("dict[str, object]", snapshot["memory_ctx"])
    assert "proactive_knowledge_pack" not in preview


@pytest.mark.parametrize(
    "overrides",
    [pytest.param({"enable_memory": False}, id="memory-off"), pytest.param({"incognito_mode": True}, id="incognito")],
)
async def test_turns_with_memory_off_or_incognito_get_no_pack(flow: _Flow, overrides: dict[str, object]) -> None:
    context = await flow.turn("what is the zephyr budget limit for hotels", **overrides)

    assert PROACTIVE_PACK_CONTEXT_KEY not in context


async def test_a_resumed_turn_keeps_the_pack_out_of_its_context(flow: _Flow) -> None:
    context = await setup.build_turn_extra_context(
        _request(resume_value={"action": "completed"}),
        _params("what is the zephyr budget limit for hotels"),
        base=None,
        goal_provider=None,
    )

    assert PROACTIVE_PACK_CONTEXT_KEY not in context


async def test_the_run_context_puts_the_pack_at_the_end_of_the_final_question(flow: _Flow) -> None:
    await flow.focus_prewarm()
    context = await flow.turn("what is the zephyr budget limit for hotels")
    seen: list[ModelRequest] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        seen.append(request)
        return ModelResponse(result=[])

    request = ModelRequest(
        messages=[HumanMessage(content="what is the zephyr budget limit for hotels")],
        model=MagicMock(),
        runtime=SimpleNamespace(context=context),
    )
    manager = SimpleNamespace(recall_mode=RecallMode.HYBRID)
    with patch("myrm_agent_harness.agent.skill_agent.context.get_memory_manager", return_value=manager):
        await proactive_pack_middleware.awrap_model_call(request, handler)

    tail = str(seen[0].messages[0].content)
    assert tail.startswith("what is the zephyr budget limit for hotels\n\n[SECURITY NOTICE")
    assert "[Finance | Hotel Limits]" in tail
    assert "120 per night" in tail
