"""Integration tests verifying the distillation guards inside the extraction pipeline."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.memory.strategies.extractor import extract_memories_from_conversation
from myrm_agent_harness.toolkits.memory.types import MemoryType

DRIFT_CONVERSATION = [
    {"role": "user", "content": "I prefer blue gradient buttons in my frontend.", "id": "u1"},
    {"role": "assistant", "content": "I suggest you also add heavy box-shadow and blur effects.", "id": "a1"},
    {"role": "user", "content": "No shadows please. My project strictly runs on Bun and Node 22.", "id": "u2"},
]

# One fact the user stated, and one that only the assistant suggested, neither citing evidence.
_DRIFT_RESPONSE = (
    "["
    '{"memory_type": "semantic", "content": "User prefers blue gradient buttons", "confidence": 0.95, "importance": 0.8},'
    '{"memory_type": "semantic", "content": "User prefers heavy box-shadow", "confidence": 0.9, "importance": 0.7}'
    "]"
)


async def drifting_llm(system_prompt: str, user_prompt: str) -> str:
    return _DRIFT_RESPONSE


@pytest.mark.asyncio
class TestDistillationGuardsAsyncIntegration:
    """Integration tests verifying guards inside extraction pipeline."""

    async def test_extract_memories_guard_integration(self) -> None:
        """extract_memories_from_conversation drops unconfirmed messages and attaches evidence."""
        messages = [
            {"role": "user", "content": "never use sudo for package installs", "id": "msg_edict_1"},
            {"role": "user", "content": "Alert: Database latency high", "name": "AlertBot", "id": "msg_bot_1"},
        ]

        async def llm(system_prompt: str, user_prompt: str) -> str:
            assert "Database latency" not in user_prompt
            return (
                '[{"memory_type": "procedural", "content": "Never use sudo for package installs",'
                ' "confidence": 0.9, "importance": 0.8, "trigger": "installing packages",'
                ' "action": "Do not use sudo"}]'
            )

        res = await extract_memories_from_conversation(messages, llm_func=llm)
        assert len(res.memories) == 1
        procedural = res.memories[0]
        assert procedural.memory_type == MemoryType.PROCEDURAL
        assert "sudo" in procedural.content
        assert len(procedural.evidence) == 1
        assert procedural.evidence[0].message_id == "msg_edict_1"

    async def test_memory_extractor_direct_extract_guard(self) -> None:
        """MemoryExtractor.extract directly drops assistant and bot turns before invoking LLM."""
        from myrm_agent_harness.toolkits.memory.strategies.extractor import MemoryExtractor

        called = False

        async def inspecting_llm(system_prompt: str, user_prompt: str) -> str:
            nonlocal called
            called = True
            assert "Jenkins" not in user_prompt
            assert "Rust" not in user_prompt
            assert "PostgreSQL" in user_prompt
            return "[]"

        extractor = MemoryExtractor(llm_func=inspecting_llm)
        messages = [
            {"role": "assistant", "content": "I recommend Rust for maximum speed."},
            {"role": "user", "name": "Jenkins-CI", "content": "Build #42 passed successfully."},
            {"role": "user", "content": "I prefer PostgreSQL over MySQL for transactional storage."},
        ]

        res = await extractor.extract(messages)
        assert called is True
        assert len(res.memories) == 0

    async def test_extract_memories_all_rejected_returns_empty(self) -> None:
        """When all input messages are rejected by distillation guards, returns empty result cleanly."""
        messages = [
            {"role": "assistant", "content": "I am an AI assistant and I think we should rewrite in Rust."},
            {"role": "user", "content": "CI build failed", "name": "JenkinsBot"},
        ]

        async def dummy_llm(system_prompt: str, user_prompt: str) -> str:
            return "[]"

        res = await extract_memories_from_conversation(messages, llm_func=dummy_llm)
        assert len(res.memories) == 0

    async def test_extracted_facts_cite_a_user_turn_never_the_assistant(self) -> None:
        """An extracted fact is anchored to a user turn, even when the assistant spoke in between."""
        res = await extract_memories_from_conversation(DRIFT_CONVERSATION, llm_func=drifting_llm)

        assert len(res.memories) > 0
        for mem in res.memories:
            assert len(mem.evidence) > 0
            assert mem.evidence[0].author_id != "assistant"

    @pytest.mark.xfail(
        strict=True,
        reason="A fact that cites no evidence is anchored to the last user turn instead of being dropped, so a fact "
        "only the assistant suggested is extracted, citing a user turn that says the opposite.",
    )
    async def test_a_fact_only_the_assistant_suggested_is_not_extracted(self) -> None:
        res = await extract_memories_from_conversation(DRIFT_CONVERSATION, llm_func=drifting_llm)

        assert [mem.content for mem in res.memories] == ["User prefers blue gradient buttons"]

    async def test_extract_memories_filters_hallucinated_evidence_memories(self) -> None:
        """extract_memories_from_conversation drops memories whose evidence quotes are fabricated."""
        messages = [
            {"role": "user", "content": "I like dark mode themes.", "id": "m1"},
        ]

        async def hallucinating_llm(system_prompt: str, user_prompt: str) -> str:
            # LLM synthesizes a fact but fabricates a quote snippet that user never said
            return """[
                {
                    "memory_type": "semantic",
                    "content": "User likes skydiving",
                    "confidence": 0.9,
                    "importance": 0.8,
                    "evidence": [
                        {
                            "source_id": "conv_1",
                            "message_id": "m1",
                            "quote_snippet": "I regularly jump out of airplanes on weekends"
                        }
                    ]
                }
            ]"""

        res = await extract_memories_from_conversation(messages, llm_func=hallucinating_llm)
        # Fabricated quote should be filtered out by filter_memories_with_evidence
        assert len(res.memories) == 0
