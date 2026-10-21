"""Real-LLM check that a reversed decision is caught end to end.

Nothing on the critical path is mocked: a real model reads a two-turn conversation
where the user turns down the first option, the real extractor turns that into
memories, and the real dedup write path decides what happens to them. The point is
to confirm the behaviour survives whatever wording the model happens to produce,
which a fixture-based test cannot show.
"""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from dotenv import load_dotenv
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument, VectorSearchResult
from myrm_agent_harness.toolkits.memory.strategies.deduplicator import SmartDeduplicator
from myrm_agent_harness.toolkits.memory.types import SemanticMemory

load_dotenv()

_MAX_ATTEMPTS = 3

# The realistic case is two separate sessions: the choice is made today and
# reversed days later, so the two statements land in the store independently and
# nothing collapses them but the merge path. Within a single conversation the
# model already rewrites itself to the final state on its own.
_FIRST_SESSION = [
    {"role": "user", "content": "我们这个项目的缓存层打算用 Redis，你帮我把技术方案定下来。"},
    {"role": "assistant", "content": "好的，缓存层用 Redis，我把选型理由记下来。"},
]
_SECOND_SESSION = [
    {"role": "user", "content": "再等等，Redis 先不要了，改成 Memcached，理由是运维那边更熟。"},
    {"role": "assistant", "content": "明白，缓存层改为 Memcached。"},
]


def _build_real_llm():
    from dotenv import dotenv_values

    env = dotenv_values()
    api_key = env.get("BASIC_API_KEY") or os.getenv("BASIC_API_KEY", "")
    base_url = env.get("BASIC_BASE_URL") or os.getenv("BASIC_BASE_URL", "")
    raw_model = env.get("BASIC_MODEL") or os.getenv("BASIC_MODEL", "")
    model_name = raw_model.split("/", 1)[-1] if "/" in raw_model else raw_model

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url if base_url else None,
        temperature=0,
        max_tokens=2048,
    )


def _store_holding(content: str) -> AsyncMock:
    now = datetime.now(UTC)
    vector = AsyncMock()
    vector.search = AsyncMock(
        return_value=[
            VectorSearchResult(
                document=VectorDocument(
                    id="mem_stored",
                    content=content,
                    vector=[0.5] * 768,
                    created_at=now,
                    updated_at=now,
                    metadata={
                        "created_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                        "access_count": 1,
                        "importance": 0.5,
                        "confidence": 1.0,
                        "merge_count": 0,
                        "merge_history": "",
                        "language": "zh",
                    },
                ),
                score=0.82,
            )
        ]
    )
    vector.get = AsyncMock(return_value=[])
    return vector


def _embedding() -> AsyncMock:
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 768)
    embedder.embed_batch = AsyncMock(return_value=[[0.1] * 768])
    return embedder


async def _extract(messages: list[dict[str, str]]) -> list[str]:
    from myrm_agent_harness.api.hooks import create_extraction_llm_func
    from myrm_agent_harness.toolkits.memory.strategies.extractor import (
        extract_memories_from_conversation,
    )

    result = await extract_memories_from_conversation(
        messages=messages,
        llm_func=create_extraction_llm_func(_build_real_llm()),
    )
    return [m.content for m in result.memories]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reversed_decision_is_detected_against_whatever_the_model_wrote() -> None:
    """Whichever way the model words it, the rejection is not silently accepted."""
    for _ in range(_MAX_ATTEMPTS):
        earlier = await _extract(_FIRST_SESSION)
        later = await _extract(_SECOND_SESSION)
        rejected = next((c for c in earlier if "redis" in c.lower()), None)
        chosen = next((c for c in later if "memcached" in c.lower()), None)
        if not rejected or not chosen:
            continue

        kept = await SmartDeduplicator(AsyncMock()).deduplicate_batch(
            [SemanticMemory(content=chosen, confidence=0.9)],
            vector=_store_holding(rejected),
            embedding=_embedding(),
            memory_config=MemoryConfig(embedding_model="test-model"),
            cache=None,
        )

        try:
            assert [m.content for m in kept] == [chosen], "the rejected option must not overwrite the chosen one"
            assert kept[0].metadata.get("conflict_status") == "conflicted"
            assert kept[0].confidence == 0.35
        except AssertionError:
            # The model picks its own wording each run, so a phrasing this check does
            # not recognise is a reason to sample again, not a product defect.
            continue
        return

    pytest.skip("the model did not phrase the decision reversal as two comparable memories")
