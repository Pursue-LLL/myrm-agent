"""Live E2E: pattern discovery with a real LLM (BASIC_* from .env.test).

Verifies the end-to-end value chain that the memory guardian revives on
demand: a real ``ChatLiteLLM`` built from the platform-style model config
runs the harness ``run_pattern_discovery`` strategy through
``with_structured_output`` and produces validated ``DiscoveredPattern`` s.

Only the harness manager boundary is stubbed (as in harness unit tests) so
no embedding service or local Qdrant is required; the LLM call, structured
JSON output parsing and PatternReport assembly are fully real.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.llms import ChatLiteLLM
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
    run_pattern_discovery,
)
from myrm_agent_harness.toolkits.memory.types import SemanticMemory

from tests.api.agent.utils import get_base_model_config

pytestmark = pytest.mark.e2e


def _make_mature_manager() -> AsyncMock:
    """Manager stub satisfying the discovery maturity gate (avoid embedding/Qdrant)."""
    manager = AsyncMock()
    manager.user_id = "test-user"
    manager.namespaces = ["test-ns"]
    manager.has_vector = True
    manager.has_relational = True
    manager.has_graph = False

    memories = [
        SemanticMemory(
            content=(
                "user consistently starts the workday with a review of the PR queue "
                "and schedules deep work before noon"
            ),
            tags=["habit", "routine"],
        ),
        SemanticMemory(
            content=(
                "user prefers TypeScript for new services and has abandoned Python "
                "for backend work over the last several weeks"
            ),
            tags=["preference", "stack"],
        ),
        SemanticMemory(
            content="user tracks open questions in a ticket that recurs across Monday reviews",
            tags=["unresolved"],
        ),
        SemanticMemory(
            content=("user asks for a short summary every time a long thread grows beyond 20 messages"),
            tags=["communication"],
        ),
    ]
    # Pad to pass the >=50 maturity gate without real storage.
    for i in range(56):
        memories.append(
            SemanticMemory(
                content=f"reference note {i}: design rationale about incremental rollouts",
                tags=["reference"],
            )
        )
    for i, mem in enumerate(memories):
        mem.created_at = datetime.now(UTC) - timedelta(days=i)

    manager.count_memories = AsyncMock(side_effect=lambda mt: 60 if str(mt) == "semantic" else 0)
    manager.list_memories = AsyncMock(return_value=memories)
    manager.get_profile_attribute = AsyncMock(side_effect=lambda key: "5" if "consolidation" in key else None)
    manager.set_profile_attribute = AsyncMock()
    manager.search = AsyncMock(
        return_value=[
            SimpleNamespace(
                memory=SemanticMemory(
                    content="consolidation insight: user works in short focused sessions",
                    tags=["consolidation-insight"],
                )
            )
        ]
    )
    manager.add_event = AsyncMock()
    manager.store = AsyncMock(return_value=SimpleNamespace(id="stored-rule"))
    return manager


@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="Live E2E requires BASIC_API_KEY",
)
async def test_pattern_discovery_with_real_llm_produces_patterns() -> None:
    """A real LLM over sufficiently mature memories yields validated patterns."""
    cfg = get_base_model_config()
    llm = ChatLiteLLM(
        model=str(cfg["model"]),
        api_key=str(cfg.get("api_key") or ""),
        api_base=str(cfg.get("base_url") or "").strip() or None,
        temperature=0,
        max_tokens=4096,
    )

    report = await run_pattern_discovery(_make_mature_manager(), llm)

    assert report.skipped is False, report.skip_reason
    assert report.memory_count >= 50
    assert len(report.patterns) > 0, "real LLM should surface at least one behavioral pattern"
    first = report.patterns[0]
    assert first.title.strip()
    assert first.description.strip()
    assert first.evidence_summary.strip()
    assert first.confidence >= 0.5


@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="Live E2E requires BASIC_API_KEY",
)
async def test_pattern_discovery_skips_when_gate_not_met() -> None:
    """Immature memory count keeps the harness gate — no LLM call occurs."""
    manager = _make_mature_manager()
    manager.count_memories = AsyncMock(return_value=10)

    cfg = get_base_model_config()
    llm = ChatLiteLLM(
        model=str(cfg["model"]),
        api_key=str(cfg.get("api_key") or ""),
        api_base=str(cfg.get("base_url") or "").strip() or None,
        temperature=0,
        max_tokens=4096,
    )

    report = await run_pattern_discovery(manager, llm)

    assert report.skipped is True
    assert "not yet mature" in report.skip_reason