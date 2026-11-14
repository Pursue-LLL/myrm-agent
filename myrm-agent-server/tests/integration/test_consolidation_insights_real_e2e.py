"""Real end-to-end checks of the insights a consolidation cycle stores, reports and publishes.

Nothing on the critical path is faked: a real model analyses memories held by a real embedded Qdrant plus SQLite
store (embeddings from a real endpoint), the cycle runs through the entry the idle chain calls
(``run_maintenance_cycle(force=True)``), the store takes or turns away each insight the model proposes, and the
server's wiki bridge publishes the digest through the real raw gate. Only the vault directory is redirected to a
temporary one, so the user's wiki is never touched.

Whatever the model proposes, the insights the store holds, the maintenance report lists and the wiki digest lists are
one and the same list, and each of them derives from every chat of the group it was drawn from. A user can delete a
chat while a cycle waits for the model; the store then turns the insights derived from it away, and a failing wiki
hook never hides what the store took.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.runnables import Runnable, RunnableLambda
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.strategies.chat_fence import DELETED_CHAT_REJECTION
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    CONSOLIDATION_INSIGHT_TAG,
    ConsolidationResponse,
)
from myrm_agent_harness.toolkits.memory.types import MemoryScope, MemoryType, SemanticMemory
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
from myrm_agent_harness.toolkits.wiki import WikiConfig
from pydantic import BaseModel

from app.services.wiki.consolidation_bridge import make_consolidation_wiki_bridge
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from tests.support.live_chat_model import live_chat_model

pytestmark = [pytest.mark.e2e, pytest.mark.integration]

_AGENT_ID = "e2e"
_AGENT_NAMESPACE = f"agent:{_AGENT_ID}"
_STRATEGIES_LOGGER = "myrm_agent_harness.toolkits.memory.strategies"
# A reasoning model spends its output budget on hidden reasoning before the answer; the product gives thinking models
# this headroom, and a smaller cap truncates the answer the cycle must parse.
_OUTPUT_TOKEN_BUDGET = 16384

type Seeds = Sequence[tuple[str, str]]

# One group of facts (all in the agent namespace). The two money facts invite a derived total; the store turns such an
# insight away because no memory states it, and the three lists must agree either way.
_SEEDS: Seeds = (
    ("chat-tea-1", "I drink green tea every morning at seven"),
    ("chat-tea-2", "I gave up coffee because it makes me anxious and drink oolong tea in the afternoon"),
    ("chat-tea-3", "I bought a clay teapot last month for brewing oolong"),
    ("chat-rent", "My monthly rent is 4500 yuan"),
    ("chat-bills", "My monthly utilities cost 300 yuan"),
)
# A second group, in the global namespace: the model analyses it in a call of its own.
_GLOBAL_SCOPE = MemoryScope(primary_namespace="global", namespaces=["global"])
_BOOKS: Seeds = (
    ("chat-book-1", "I read science fiction novels in bed every night before sleeping"),
    ("chat-book-2", "I finished a long space opera last week and started its sequel straight away"),
    ("chat-book-3", "I prefer paper books to e-readers because screens keep me awake"),
)
_DIGEST_LINE = re.compile(r"^\d+\. (.+)$", re.MULTILINE)


class _ChatDeletingModel:
    """The real model, with a chat deleted right after its ``after``-th consolidation answer arrives.

    A user can delete a chat at any moment, including while a cycle waits for the model; the cycle has analysed the
    chat's memories by then and applies its answers afterwards. Every other call (the staleness and recurrence
    reviews call ``ainvoke`` directly) goes to the real model untouched.
    """

    def __init__(self, model: BaseChatModel, *, after: int, chat_id: str) -> None:
        self._model = model
        self._after = after
        self._chat_id = chat_id
        self._answers = 0
        self.manager: MemoryManager | None = None

    def __getattr__(self, name: str) -> object:
        return getattr(self._model, name)

    def with_structured_output(self, schema: type[BaseModel]) -> Runnable[LanguageModelInput, dict | BaseModel]:
        structured = self._model.with_structured_output(schema)
        if schema is not ConsolidationResponse:
            return structured

        async def answer(messages: LanguageModelInput) -> dict | BaseModel:
            result = await structured.ainvoke(messages)
            self._answers += 1
            if self._answers == self._after:
                assert self.manager is not None, "bind the manager before the cycle runs"
                await self.manager.purge_by_source_chat_id(self._chat_id)
            return result

        return RunnableLambda(answer)


@pytest.fixture
async def llm() -> AsyncIterator[BaseChatModel]:
    model = os.environ["BASIC_MODEL"]
    async with live_chat_model(
        model=model.partition("/")[2] or model,
        base_url=os.environ["BASIC_BASE_URL"],
        api_key=os.environ["BASIC_API_KEY"],
        temperature=0,
        max_tokens=_OUTPUT_TOKEN_BUDGET,
        timeout=120,
    ) as chat:
        yield chat


@pytest.fixture
def vault(tmp_path: Path, llm: BaseChatModel, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The temporary wiki vault the bridge publishes into."""
    path = tmp_path / "vault"
    archiver = MemoryToWikiArchiver(llm=llm, wiki_dir=path, config=WikiConfig())
    monkeypatch.setattr("app.services.wiki.vault.get_wiki_archiver", lambda *_args, **_kwargs: archiver)
    return path


@asynccontextmanager
async def _open_manager(
    tmp_path: Path, llm: BaseChatModel, *, consolidation_llm: _ChatDeletingModel | None = None
) -> AsyncIterator[MemoryManager]:
    """A real manager wired as the agent surface wires it: the wiki bridge is the completion hook."""
    memory = await create_local_memory_manager(
        tmp_path / "memory",
        # Patient retries outwait a per-minute request quota instead of failing the cycle.
        EmbeddingConfig(
            model=os.environ["VOYAGE_EMBEDDING_MODEL"],
            api_key=os.environ["VOYAGE_API_KEY"],
            max_retries=8,
            retry_wait_min=10,
            retry_wait_max=30,
        ),
        # The deleted-chat fence is keyed by user and chat id and outlives a manager within the process.
        user_id=f"user-{uuid4().hex}",
        dedup_llm=llm,
        consolidation_llm=consolidation_llm,
        namespaces=[_AGENT_NAMESPACE, "global"],
        agent_id=_AGENT_ID,
        on_consolidation_complete=make_consolidation_wiki_bridge(agent_id=_AGENT_ID, llm=llm),
    )
    if consolidation_llm is not None:
        consolidation_llm.manager = memory
    try:
        yield memory
    finally:
        await memory.close()


def _semantic_memories(seeds: Seeds, scope: MemoryScope | None = None) -> list[SemanticMemory]:
    memories = [SemanticMemory(content=text, source_chat_id=chat_id) for chat_id, text in seeds]
    if scope is not None:
        for memory in memories:
            memory.scope = scope.model_copy(deep=True)
    return memories


async def _seed_two_groups(manager: MemoryManager) -> None:
    """The agent group first, the global group second: groups are analysed in the order their memories arrived."""
    await manager.store_batch([*_semantic_memories(_SEEDS), *_semantic_memories(_BOOKS, _GLOBAL_SCOPE)], _bypass_approval=True)


async def _stored_insights(manager: MemoryManager) -> list[SemanticMemory]:
    return await manager.list_memories(MemoryType.SEMANTIC, tag_filter=CONSOLIDATION_INSIGHT_TAG)


def _digest_files(vault: Path) -> list[Path]:
    return sorted((vault / "raw").rglob(f"consolidation_{_AGENT_ID}_*.md"))


def _digest_insights(vault: Path) -> list[str]:
    digests = _digest_files(vault)
    assert len(digests) == 1, f"expected one consolidation digest in the vault, found {digests}"
    return _DIGEST_LINE.findall(digests[0].read_text(encoding="utf-8"))


def _chat_ids(seeds: Seeds) -> list[str]:
    return sorted(chat_id for chat_id, _ in seeds)


@pytest.mark.timeout(600)
async def test_the_insights_of_a_cycle_agree_everywhere_and_follow_their_chats(
    tmp_path: Path, llm: BaseChatModel, vault: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=_STRATEGIES_LOGGER)
    async with _open_manager(tmp_path, llm) as manager:
        await manager.store_batch(_semantic_memories(_SEEDS), _bypass_approval=True)

        report = await manager.run_maintenance_cycle(force=True)

        assert not report.skipped, report.skip_reason
        assert report.consolidation_errors == 0
        stored = await _stored_insights(manager)
        stored_texts = sorted(memory.content for memory in stored)
        assert stored_texts, "the model proposed no insight the store took, so this cycle proves nothing"
        assert sorted(report.insights) == stored_texts
        assert sorted(_digest_insights(vault)) == stored_texts
        for insight in stored:
            assert sorted(insight.source_chat_ids) == _chat_ids(_SEEDS)

        # A cycle straight after is turned away by the soft lock: nothing is stored, reported or published twice.
        again = await manager.run_maintenance_cycle(force=True)

        assert "Consolidation skipped: soft lock" in caplog.text
        assert again.consolidation_errors == 0
        assert again.insights == ()
        assert sorted(memory.content for memory in await _stored_insights(manager)) == stored_texts
        assert sorted(_digest_insights(vault)) == stored_texts

        # An insight derives from every chat of its group, so deleting any one of them deletes it.
        await manager.purge_by_source_chat_id("chat-tea-3")

        assert await _stored_insights(manager) == []


@pytest.mark.timeout(600)
async def test_an_insight_derived_from_a_chat_deleted_mid_cycle_is_neither_stored_reported_nor_published(
    tmp_path: Path, llm: BaseChatModel, vault: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=_STRATEGIES_LOGGER)
    deleting_model = _ChatDeletingModel(llm, after=1, chat_id="chat-tea-3")
    async with _open_manager(tmp_path, llm, consolidation_llm=deleting_model) as manager:
        await manager.store_batch(_semantic_memories(_SEEDS), _bypass_approval=True)

        report = await manager.run_maintenance_cycle(force=True)

        assert report.consolidation_errors == 0
        assert DELETED_CHAT_REJECTION in caplog.text, "the model proposed no insight, so the fence refused nothing"
        assert report.insights == ()
        assert await _stored_insights(manager) == []
        assert _digest_files(vault) == []


@pytest.mark.timeout(600)
async def test_every_groups_insights_are_stored_reported_and_published_with_their_own_chats(
    tmp_path: Path, llm: BaseChatModel, vault: Path
) -> None:
    async with _open_manager(tmp_path, llm) as manager:
        await _seed_two_groups(manager)

        report = await manager.run_maintenance_cycle(force=True)

        assert report.consolidation_errors == 0
        stored = await _stored_insights(manager)
        for namespace, seeds in ((_AGENT_NAMESPACE, _SEEDS), ("global", _BOOKS)):
            own = [insight for insight in stored if insight.scope.primary_namespace == namespace]
            assert own, f"the model proposed no insight the store took for the {namespace} group"
            for insight in own:
                assert sorted(insight.source_chat_ids) == _chat_ids(seeds)
        stored_texts = sorted(memory.content for memory in stored)
        assert sorted(report.insights) == stored_texts
        assert sorted(_digest_insights(vault)) == stored_texts


@pytest.mark.timeout(600)
async def test_a_deleted_chat_costs_only_the_insights_of_its_own_group(
    tmp_path: Path, llm: BaseChatModel, vault: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=_STRATEGIES_LOGGER)
    # The global group is analysed second, so its answer is the second one.
    deleting_model = _ChatDeletingModel(llm, after=2, chat_id="chat-book-1")
    async with _open_manager(tmp_path, llm, consolidation_llm=deleting_model) as manager:
        await _seed_two_groups(manager)

        report = await manager.run_maintenance_cycle(force=True)

        assert report.consolidation_errors == 0
        assert DELETED_CHAT_REJECTION in caplog.text, "the model proposed no insight for the global group"
        stored = await _stored_insights(manager)
        stored_texts = sorted(memory.content for memory in stored)
        assert stored_texts, "the model proposed no insight the store took for the agent group"
        for insight in stored:
            assert insight.scope.primary_namespace == _AGENT_NAMESPACE
            assert sorted(insight.source_chat_ids) == _chat_ids(_SEEDS)
        assert sorted(report.insights) == stored_texts
        assert sorted(_digest_insights(vault)) == stored_texts


@pytest.mark.timeout(600)
async def test_a_failing_wiki_hook_leaves_the_insights_the_store_took_reported(
    tmp_path: Path, llm: BaseChatModel, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> MemoryToWikiArchiver:
        raise RuntimeError("wiki vault unavailable")

    monkeypatch.setattr("app.services.wiki.vault.get_wiki_archiver", unavailable)
    caplog.set_level(logging.INFO, logger=_STRATEGIES_LOGGER)
    async with _open_manager(tmp_path, llm) as manager:
        await manager.store_batch(_semantic_memories(_SEEDS), _bypass_approval=True)

        report = await manager.run_maintenance_cycle(force=True)

        assert report.consolidation_errors == 0
        stored_texts = sorted(memory.content for memory in await _stored_insights(manager))
        assert stored_texts, "the model proposed no insight the store took, so this cycle proves nothing"
        assert sorted(report.insights) == stored_texts
        assert "Consolidation complete hook failed (non-fatal): wiki vault unavailable" in caplog.text
