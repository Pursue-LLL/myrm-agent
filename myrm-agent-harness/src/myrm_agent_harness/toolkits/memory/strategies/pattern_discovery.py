"""Cross-cycle pattern discovery — surface behavioral trends users haven't noticed.

[INPUT]
- memory.manager::MemoryManager (POS: unified memory manager facade)
- memory.protocols.graph::GraphStoreProtocol (POS: graph store for claim collection)
- utils.coercion::parse_int (POS: defensive numeric coercion utilities)
- strategies.bookkeeping::{read_bookkeeping, write_bookkeeping} (POS: Direct persistence of maintenance counters, hashes and timestamps)
- strategies.consolidation_models::CONSOLIDATION_INSIGHT_TAG (POS: markers of consolidation's own output)
- strategies.pattern_discovery_models::* (POS: Domain models and result DTO for pattern discovery)
- strategies.pattern_discovery_prompts::* (POS: Prompts for cross-cycle pattern discovery)

[OUTPUT]
- run_pattern_discovery: Analyze memories and insights to surface cross-cycle patterns; returns a PatternReport.
- should_run_pattern_discovery: Gate check based on memory maturity.
- increment_consolidation_count: Track consolidation runs for gate check.
- get_recent_patterns: Retrieve patterns for Heartbeat SituationSection injection.

[POS]
Cross-cycle pattern discovery strategy. Runs weekly (server-layer scheduling),
analyzes accumulated memories, consolidation insights, and claim graph to find
behavioral patterns the user may not be aware of. Framework-layer pure strategy;
scheduling and persistence are server-layer responsibilities.

Closed-loop pipeline: high-confidence ESTABLISHED patterns are also promoted to
ProceduralRule (pending user approval) so the agent can apply learned behavioral
preferences automatically in future conversations.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel

from myrm_agent_harness.toolkits.memory.strategies.bookkeeping import read_bookkeeping, write_bookkeeping
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import CONSOLIDATION_INSIGHT_TAG
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery_models import (
    DiscoveredPattern,
    PatternDiscoveryResponse,
    PatternDurability,
    PatternReport,
)
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery_prompts import (
    _SYSTEM_PROMPT,
    _build_discovery_prompt,
)
from myrm_agent_harness.utils.coercion import parse_int

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager
    from myrm_agent_harness.toolkits.memory.types import AnyMemory

logger = logging.getLogger(__name__)

_PROFILE_KEY_CONSOLIDATION_COUNT = "_system.consolidation_count"
_PROFILE_KEY_MEMORY_SET_HASH = "_system.pattern_discovery_memory_hash"
_MIN_MEMORY_COUNT = 50
_MIN_CONSOLIDATION_COUNT = 3

# Gate thresholds for promoting a pattern to a ProceduralRule.
# Only "established" patterns with high confidence become actionable rules.
_RULE_PROMOTION_MIN_CONFIDENCE = 0.8


async def should_run_pattern_discovery(manager: MemoryManager) -> bool:
    """Gate check: only run if memory system is mature enough.

    Conditions (all must be true):
    1. At least _MIN_MEMORY_COUNT memories exist
    2. Consolidation has run at least _MIN_CONSOLIDATION_COUNT times
    """
    if not manager.has_relational or not manager.has_vector:
        return False

    from myrm_agent_harness.toolkits.memory.types import MemoryType

    total = 0
    for mt in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
        with contextlib.suppress(Exception):
            total += await manager.count_memories(mt)

    if total < _MIN_MEMORY_COUNT:
        return False

    # The counter is a plain profile row that any writer can overwrite; a malformed value counts as zero.
    raw_count = await read_bookkeeping(manager, _PROFILE_KEY_CONSOLIDATION_COUNT)
    consolidation_count = parse_int(raw_count, 0, min_val=0)
    return consolidation_count >= _MIN_CONSOLIDATION_COUNT


async def increment_consolidation_count(manager: MemoryManager) -> None:
    """Increment the persistent consolidation counter after a successful consolidation."""
    if not manager.has_relational:
        return
    # A malformed stored value restarts the count, and the write below replaces it.
    raw = await read_bookkeeping(manager, _PROFILE_KEY_CONSOLIDATION_COUNT)
    current = parse_int(raw, 0, min_val=0)
    await write_bookkeeping(manager, _PROFILE_KEY_CONSOLIDATION_COUNT, str(current + 1))


async def _collect_insights(manager: MemoryManager, limit: int = 30) -> list[str]:
    """Collect the insights consolidation stored as semantic memories (tagged ``CONSOLIDATION_INSIGHT_TAG``)."""
    try:
        results = await manager.search(
            "consolidation insight pattern observation",
            limit=limit,
            track_access=False,
        )
        return [r.memory.content for r in results if CONSOLIDATION_INSIGHT_TAG in getattr(r.memory, "tags", [])]
    except Exception as exc:
        logger.warning("Pattern discovery: failed to collect insights: %s", exc)
        return []


async def _collect_claims(manager: MemoryManager, limit: int = 30) -> list[str]:
    """Collect high-level claims from the claim graph if available."""
    if not manager.has_graph:
        return []
    try:
        graph = manager._graph
        if graph is None:
            return []
        nodes = await graph.find_nodes(labels=["Claim"], filters={}, limit=limit)
        return [str(n.properties.get("content", "")) for n in nodes if n.properties.get("content")]
    except Exception as exc:
        logger.warning("Pattern discovery: failed to collect claims: %s", exc)
        return []


def _compute_memory_set_hash(memories: Sequence[AnyMemory]) -> str:
    """Deterministic hash of the memory ID set for change detection."""
    ids = sorted(m.id for m in memories)
    return hashlib.sha256("|".join(ids).encode()).hexdigest()[:16]


async def run_pattern_discovery(
    manager: MemoryManager,
    llm: BaseChatModel,
) -> PatternReport:
    """Execute a pattern discovery cycle.

    1. Gate check (memory count + consolidation count)
    2. Collect recent memories; skip if memory set unchanged since last run
    3. Collect consolidation insights, claims
    4. LLM analysis → structured patterns
    5. Persist patterns as episodic events + record the memory-set hash
    """
    start = datetime.now(UTC)

    if not await should_run_pattern_discovery(manager):
        return PatternReport(skipped=True, skip_reason="memory system not yet mature enough")

    from myrm_agent_harness.toolkits.memory.types import MemoryType

    all_memories: list[AnyMemory] = []
    for mt in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
        try:
            mems = await manager.list_memories(mt, limit=200)
            all_memories.extend(mems)
        except Exception as exc:
            logger.warning("Pattern discovery: failed to list %s: %s", mt.value, exc)

    all_memories.sort(key=lambda m: m.created_at, reverse=True)
    memory_count = len(all_memories)

    current_hash = _compute_memory_set_hash(all_memories)
    if manager.has_relational:
        prev_hash = await read_bookkeeping(manager, _PROFILE_KEY_MEMORY_SET_HASH)
        if prev_hash and prev_hash == current_hash:
            logger.info("Pattern discovery: memory set unchanged, skipping LLM call")
            return PatternReport(
                memory_count=memory_count,
                skipped=True,
                skip_reason="memory set unchanged since last discovery",
            )

    insights = await _collect_insights(manager)
    claims = await _collect_claims(manager)

    today = start.strftime("%Y-%m-%d")
    user_prompt = _build_discovery_prompt(all_memories, insights, claims, today)

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        structured_llm = llm.with_structured_output(PatternDiscoveryResponse)
        raw_response = await structured_llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
        )
        # A pydantic schema normally yields an instance and a JSON-mode parser a dict; anything else is a provider fault.
        if isinstance(raw_response, dict):
            response = PatternDiscoveryResponse.model_validate(raw_response)
        elif isinstance(raw_response, PatternDiscoveryResponse):
            response = raw_response
        else:
            raise TypeError(f"Unexpected response type from structured LLM: {type(raw_response)}")
    except Exception as exc:
        logger.warning("Pattern discovery LLM call failed: %s", exc)
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        return PatternReport(
            memory_count=memory_count,
            insight_count=len(insights),
            duration_ms=elapsed,
            skipped=True,
            skip_reason=f"LLM call failed: {exc}",
        )

    valid_patterns = [p for p in response.patterns if p.confidence >= 0.5][:5]

    if valid_patterns:
        await _persist_patterns(manager, valid_patterns, response.meta_observation)

    if manager.has_relational:
        with contextlib.suppress(Exception):
            await write_bookkeeping(manager, _PROFILE_KEY_MEMORY_SET_HASH, current_hash)

    elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
    report = PatternReport(
        patterns=tuple(valid_patterns),
        meta_observation=response.meta_observation,
        memory_count=memory_count,
        insight_count=len(insights),
        duration_ms=elapsed,
    )

    logger.info(
        "Pattern discovery complete: patterns=%d memory_count=%d insights=%d (%.0fms)",
        len(valid_patterns),
        memory_count,
        len(insights),
        elapsed,
    )
    return report


def _is_promotable_to_rule(pattern: DiscoveredPattern) -> bool:
    """Return True if a pattern meets the threshold for ProceduralRule promotion.

    Promotion criteria (all must be satisfied):
    - durability == ESTABLISHED: pattern has been observed across 3+ cycles
    - confidence >= 0.8: LLM is highly confident in the pattern
    - actionable_suggestion is non-empty: there is a concrete action to encode
    - pattern type is habit/preference (description + actionable_suggestion are action-oriented)

    Patterns about "knowledge evolution", "unresolved threads", or "blind spots"
    typically lack a concrete trigger→action mapping and are excluded via the
    actionable_suggestion gate.
    """
    return (
        pattern.durability == PatternDurability.ESTABLISHED
        and pattern.confidence >= _RULE_PROMOTION_MIN_CONFIDENCE
        and bool(pattern.actionable_suggestion.strip())
    )


async def _promote_patterns_to_rules(
    manager: MemoryManager,
    patterns: list[DiscoveredPattern],
) -> int:
    """Promote qualifying patterns to ProceduralRule (pending approval).

    Uses manager.store() without _bypass_approval so the write_service routes
    the rule through the standard Pending review queue when approval_required=True.
    Returns the count of rules successfully queued for promotion.
    """
    if not manager.has_relational:
        return 0

    from myrm_agent_harness.toolkits.memory.types import ProceduralMemory, RuleSource

    promotable = [p for p in patterns if _is_promotable_to_rule(p)]
    if not promotable:
        return 0

    promoted = 0
    for pattern in promotable:
        try:
            rule = ProceduralMemory(
                content=pattern.title,
                trigger=pattern.description,
                action=pattern.actionable_suggestion,
                reasoning=pattern.evidence_summary,
                source=RuleSource.AGENT_SELF,
                priority=10,
            )
            await manager.store(rule)
            promoted += 1
            logger.info(
                "Pattern promoted to ProceduralRule (pending approval): %r (confidence=%.2f)",
                pattern.title,
                pattern.confidence,
            )
        except Exception as exc:
            logger.warning(
                "Failed to promote pattern %r to ProceduralRule: %s",
                pattern.title,
                exc,
            )

    return promoted


async def _persist_patterns(
    manager: MemoryManager,
    patterns: list[DiscoveredPattern],
    meta_observation: str,
) -> None:
    """Store discovered patterns as episodic memory events for auditability and Heartbeat injection.

    Also promotes high-confidence ESTABLISHED patterns to ProceduralRule via the
    standard Pending approval queue, closing the loop between pattern discovery and
    actionable agent behavior.
    """
    if not manager.has_vector:
        return

    summary_parts = []
    for p in patterns:
        suggestion = f" Suggestion: {p.actionable_suggestion}" if p.actionable_suggestion else ""
        summary_parts.append(f"[{p.durability.value}] {p.title}: {p.description}{suggestion}")

    if meta_observation:
        summary_parts.append(f"Overall: {meta_observation}")

    content = "\n".join(summary_parts)
    try:
        await manager.add_event(
            content=content,
            event_type="pattern_discovery",
            related_entities=["memory_system", "behavioral_patterns"],
        )
    except Exception as exc:
        logger.warning("Failed to persist pattern discovery event: %s", exc)

    promoted = await _promote_patterns_to_rules(manager, patterns)
    if promoted:
        logger.info("Pattern discovery: %d pattern(s) queued for ProceduralRule promotion", promoted)


async def get_recent_patterns(manager: MemoryManager, limit: int = 5) -> list[str]:
    """Retrieve recently discovered patterns for Heartbeat injection.

    Filters episodic events by event_type=pattern_discovery via vector scroll,
    avoiding unreliable semantic search.
    """
    if not manager.has_vector:
        return []
    try:
        vector = manager._vector
        if vector is None:
            return []
        docs, _ = await vector.scroll(
            manager._config.episodic_collection,
            limit=limit,
            filters={
                "event_type": "pattern_discovery",
                "primary_namespace": manager.namespaces,
            },
        )
        return [d.content for d in docs if d.content]
    except Exception:
        return []
