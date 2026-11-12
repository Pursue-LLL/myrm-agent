"""Real end-to-end check that a consolidation cycle reports exactly the insights its store took.

Nothing on the critical path is faked: a real model analyses memories held by a real embedded Qdrant plus SQLite
store (embeddings from a real endpoint), the cycle runs through the entry the idle chain calls
(``run_maintenance_cycle(force=True)``), the store takes or turns away each insight the model proposes, and the
server's wiki bridge publishes the digest through the real raw gate. Only the vault directory is redirected to a
temporary one, so the user's wiki is never touched.

Whatever the model proposes, the insights the store holds, the maintenance report lists and the wiki digest lists
are one and the same list, and each of them derives from every chat of the group it was drawn from.
"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import CONSOLIDATION_INSIGHT_TAG
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
from myrm_agent_harness.toolkits.wiki import WikiConfig

from app.services.wiki.consolidation_bridge import make_consolidation_wiki_bridge
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver

pytestmark = [pytest.mark.e2e, pytest.mark.integration]

_AGENT_ID = "e2e"

# One namespace, so the model analyses a single group. The two money facts invite a derived total; the store turns such
# an insight away because no memory states it, and the three lists must agree either way.
_SEEDS: tuple[tuple[str, str], ...] = (
    ("chat-tea-1", "I drink green tea every morning at seven"),
    ("chat-tea-2", "I gave up coffee because it makes me anxious and drink oolong tea in the afternoon"),
    ("chat-tea-3", "I bought a clay teapot last month for brewing oolong"),
    ("chat-rent", "My monthly rent is 4500 yuan"),
    ("chat-bills", "My monthly utilities cost 300 yuan"),
)
_DIGEST_LINE = re.compile(r"^\d+\. (.+)$", re.MULTILINE)


@pytest.fixture
def llm() -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    model = os.environ["BASIC_MODEL"]
    return ChatOpenAI(
        model=model.partition("/")[2] or model,
        base_url=os.environ["BASIC_BASE_URL"],
        api_key=os.environ["BASIC_API_KEY"],
        temperature=0,
        max_tokens=2048,
        timeout=120,
    )


@pytest.fixture
def vault(tmp_path: Path, llm: BaseChatModel, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The temporary wiki vault the bridge publishes into."""
    path = tmp_path / "vault"
    archiver = MemoryToWikiArchiver(llm=llm, wiki_dir=path, config=WikiConfig())
    monkeypatch.setattr("app.services.wiki.vault.get_wiki_archiver", lambda *_args, **_kwargs: archiver)
    return path


@pytest.fixture
async def manager(tmp_path: Path, llm: BaseChatModel) -> AsyncIterator[MemoryManager]:
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
        dedup_llm=llm,
        on_consolidation_complete=make_consolidation_wiki_bridge(agent_id=_AGENT_ID, llm=llm),
    )
    try:
        yield memory
    finally:
        await memory.close()


def _digest_insights(vault: Path) -> list[str]:
    digests = sorted((vault / "raw").rglob(f"consolidation_{_AGENT_ID}_*.md"))
    assert len(digests) == 1, f"expected one consolidation digest in the vault, found {digests}"
    return _DIGEST_LINE.findall(digests[0].read_text(encoding="utf-8"))


@pytest.mark.timeout(600)
async def test_the_store_the_report_and_the_wiki_digest_list_the_same_insights(manager: MemoryManager, vault: Path) -> None:
    await manager.store_batch(
        [SemanticMemory(content=text, source_chat_id=chat_id) for chat_id, text in _SEEDS], _bypass_approval=True
    )

    report = await manager.run_maintenance_cycle(force=True)

    assert not report.skipped, report.skip_reason
    assert report.consolidation_errors == 0
    stored = await manager.list_memories(MemoryType.SEMANTIC, tag_filter=CONSOLIDATION_INSIGHT_TAG)
    stored_texts = sorted(memory.content for memory in stored)
    assert stored_texts, "the model proposed no insight the store took, so this cycle proves nothing"

    assert sorted(report.insights) == stored_texts
    assert sorted(_digest_insights(vault)) == stored_texts
    seeded_chats = sorted(chat_id for chat_id, _ in _SEEDS)
    for insight in stored:
        assert sorted(insight.source_chat_ids) == seeded_chats
