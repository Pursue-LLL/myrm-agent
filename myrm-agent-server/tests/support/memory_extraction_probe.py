"""@input: myrm_agent_harness post-turn memory extraction (auto_extract_memories, build_extraction_messages, persist_extracted_memories)
@output: ExtractionProbe, install_real_extraction_probe()
@pos: [T] pytest-only probe — runs the real post-turn memory extraction in agent E2E tests and records what reaches the LLM and the store.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from myrm_agent_harness.agent._internals import memory_extraction

# Bound at import time: tests/api/agent/conftest.py swaps the module attribute for a no-op around every
# test, so the real function is only reachable through this early binding.
from myrm_agent_harness.api.hooks import auto_extract_memories as _real_auto_extract_memories
from myrm_agent_harness.toolkits.memory.strategies.extractor import ExtractedMemory


@dataclass
class ExtractionProbe:
    """What the real extraction saw (prompts) and wrote (memories) during a test."""

    prompts: list[list[dict[str, str]]] = field(default_factory=list)
    persisted: list[tuple[list[str], int]] = field(default_factory=list)

    @property
    def extracted_contents(self) -> list[str]:
        return [content for contents, _ in self.persisted for content in contents]

    @property
    def stored_count(self) -> int:
        return sum(stored for _, stored in self.persisted)

    def prompt_text(self) -> str:
        return "\n".join(turn["content"] for prompt in self.prompts for turn in prompt)

    def saw_prompt_containing(self, text: str) -> bool:
        return text in self.prompt_text()


def install_real_extraction_probe(monkeypatch: pytest.MonkeyPatch) -> ExtractionProbe:
    """Re-enable the real post-turn extraction for this test and record its inputs and outputs."""
    probe = ExtractionProbe()
    build_messages = memory_extraction.build_extraction_messages
    persist = memory_extraction.persist_extracted_memories

    def _record_prompt(*args: object, **kwargs: object) -> list[dict[str, str]]:
        messages = build_messages(*args, **kwargs)  # type: ignore[arg-type]
        probe.prompts.append(messages)
        return messages

    async def _record_persist(memories: list[ExtractedMemory], *args: object, **kwargs: object) -> int:
        stored = await persist(memories, *args, **kwargs)  # type: ignore[arg-type]
        probe.persisted.append(([memory.content for memory in memories], stored))
        return stored

    monkeypatch.setattr(memory_extraction, "auto_extract_memories", _real_auto_extract_memories)
    monkeypatch.setattr(memory_extraction, "build_extraction_messages", _record_prompt)
    monkeypatch.setattr(memory_extraction, "persist_extracted_memories", _record_persist)
    return probe
