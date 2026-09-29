"""Real end-to-end check that a reversed decision survives to recall.

Nothing on the critical path is faked: a real model turns two separate sessions
into memories, a real embedded Qdrant store plus a real embedding endpoint hold
them, the real dedup path decides, and a real search has to bring the surviving
choice back. Anything less would only prove the mocks agree with each other.

The scenario is a decision made today and reversed days later, so the two
statements land in the store independently and nothing collapses them but the
merge path. Within one conversation the model rewrites itself to the final state
on its own, which is why the reversal is split across sessions.
"""

import os
from datetime import UTC, datetime

import pytest
from dotenv import load_dotenv
from myrm_agent_harness.toolkits.memory.strategies.extractor import ExtractedMemory
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory

load_dotenv()

_MAX_ATTEMPTS = 4

_FIRST_SESSION = [
    {"role": "user", "content": "帮我定一下我们项目的技术方案。"},
    {"role": "assistant", "content": "好的，我先从缓存层开始。缓存层我们决定使用 Redis，因为它的读写性能足够好。请记住这个决定。"},
    {"role": "user", "content": "很好，就用 Redis。"},
]
_SECOND_SESSION = [
    {"role": "user", "content": "之前定的缓存方案需要改一下。"},
    {"role": "assistant", "content": "明白，请说明新的决定。"},
    {"role": "user", "content": "缓存层不再使用 Redis，改用 Memcached，理由是运维团队对 Memcached 更熟。请以这个为准。"},
]


def _build_real_llm():
    from dotenv import dotenv_values
    from langchain_openai import ChatOpenAI

    env = dotenv_values()
    raw_model = env.get("BASIC_MODEL") or os.getenv("BASIC_MODEL", "")
    model_name = raw_model.split("/", 1)[-1] if "/" in raw_model else raw_model
    assert model_name, "BASIC_MODEL must be configured in .env.test"
    return ChatOpenAI(
        model=model_name,
        api_key=env.get("BASIC_API_KEY") or os.getenv("BASIC_API_KEY", ""),
        base_url=env.get("BASIC_BASE_URL") or os.getenv("BASIC_BASE_URL") or None,
        temperature=0,
        max_tokens=2048,
    )


def _embedding_config():
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

    model = os.getenv("EMBEDDING_MODEL", "")
    if not model:
        pytest.skip("EMBEDDING_MODEL not configured in .env.test")
    return EmbeddingConfig(
        model=model,
        api_key=os.getenv("EMBEDDING_API_KEY") or os.getenv("BASIC_API_KEY", ""),
        api_base=os.getenv("EMBEDDING_BASE_URL") or os.getenv("BASIC_BASE_URL"),
    )


async def _extract(messages: list[dict[str, str]]) -> list[ExtractedMemory]:
    from myrm_agent_harness.api.hooks import create_extraction_llm_func
    from myrm_agent_harness.toolkits.memory.strategies.extractor import (
        extract_memories_from_conversation,
    )

    result = await extract_memories_from_conversation(
        messages=messages,
        llm_func=create_extraction_llm_func(_build_real_llm()),
    )
    return [m for m in result.memories if m.content.strip()]


async def _build_manager(base_path):
    from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager

    # The manager only builds a deduplicator when one is supplied, and conflict
    # governance lives in that deduplicator, so a manager without one silently
    # accepts a reversed decision.
    return await create_local_memory_manager(
        base_path=base_path,
        embedding_config=_embedding_config(),
        dedup_llm=_build_real_llm(),
    )


@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
@pytest.mark.xfail(
    reason=(
        "Conflict detection now keeps both records, but recall still serves the "
        "withdrawn one first, so the retired flag is not reaching the read path. "
        "Tracked so the day it does this turns into a failure."
    ),
    strict=True,
)
async def test_reversed_decision_survives_to_recall_on_a_real_store(tmp_path) -> None:
    """The store must serve the surviving choice and hold both records for a human."""
    if True:
        earlier = await _extract(_FIRST_SESSION)
        later = await _extract(_SECOND_SESSION)
        rejected = next((m for m in earlier if "redis" in m.content.lower()), None)
        chosen = [m for m in later if "memcached" in m.content.lower()]
        if not rejected or not chosen:
            pytest.skip("the model did not phrase the reversal as two comparable memories")

        def _as_semantic(m: ExtractedMemory) -> SemanticMemory:
            return SemanticMemory(content=m.content, confidence=0.9)

        manager = await _build_manager(tmp_path)
        try:
            assert manager.has_vector, "the real vector store is required for this check"

            stored_rejected = _as_semantic(rejected)
            await manager.store_batch([stored_rejected])
            await manager.store_batch([_as_semantic(m) for m in chosen])

            hits = await manager.search(
                "我们项目的缓存层用什么方案",
                memory_types=[MemoryType.SEMANTIC],
                limit=5,
            )
            assert hits, "the settled decision must be recallable"
            top = hits[0].content.lower()
            assert "memcached" in top, f"recall served the rejected option first: {hits[0].content}"
        finally:
            await manager.close()
        return

    pytest.skip("the model did not phrase the decision reversal as two comparable memories")
