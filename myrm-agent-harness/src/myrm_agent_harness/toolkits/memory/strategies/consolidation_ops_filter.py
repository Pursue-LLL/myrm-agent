"""Pre-apply checks of the operations a consolidation model proposed.

[INPUT]
- strategies.consolidation_closure::{Facts, facts_of} (POS: the numbers and identifiers a text states)
- strategies.consolidation_models::{ConsolidationOp, CorrectOp, MergeOp} (POS: consolidation operations)
- strategies.named_entity_guard::NamedEntityGuard (POS: deterministic critical-entity guard with self-healing)
- memory.types::AnyMemory (POS: memory records)

[OUTPUT]
- FilteredOperations: the operations that passed, with how many the entity guard repaired and the checks turned away
- filter_and_guard_operations: Rubric, id, closure and named-entity gate over the model's proposed operations

[POS]
Everything about a proposal that can be decided without reading the store: the rubric score, that every memory it
names is one the model was shown (short ids are resolved to full ids here, so no later step depends on the prompt's
numbering), that it states no number or identifier absent from the texts it was derived from, that no critical
technical entity was lost (a merge that lost one is repaired deterministically), and that at most one operation, the
first the model proposed, acts on a memory. The apply step later checks what the store holds by then.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.strategies.consolidation_closure import Facts, facts_of
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import ConsolidationOp, CorrectOp, MergeOp
from myrm_agent_harness.toolkits.memory.strategies.named_entity_guard import NamedEntityGuard

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.types import AnyMemory

logger = logging.getLogger(__name__)

_MIN_RUBRIC_SCORE = 0.7


@dataclass(frozen=True, slots=True)
class FilteredOperations:
    operations: list[ConsolidationOp]
    guard_patched: int = 0
    rejected: int = 0


def _named_ids(op: ConsolidationOp) -> list[str]:
    return op.source_ids if isinstance(op, MergeOp) else [op.memory_id]


def _candidate_text(op: ConsolidationOp) -> str:
    if isinstance(op, MergeOp):
        return op.merged_content
    if isinstance(op, CorrectOp):
        return op.corrected_content
    return op.new_content


def _resolved(op: ConsolidationOp, id_map: dict[str, str], texts: dict[str, str]) -> ConsolidationOp | None:
    """``op`` naming full ids, or ``None`` when it names a memory the model was not shown or has too few sources."""
    named = list(dict.fromkeys(id_map.get(name, name) for name in _named_ids(op)))
    if unknown := [name for name in named if name not in texts]:
        logger.warning(
            "Consolidation op %s rejected: it names memories outside the analyzed set: %s", op.action, unknown
        )
        return None
    if not isinstance(op, MergeOp):
        return op.model_copy(update={"memory_id": named[0]})
    if len(named) < 2:
        logger.warning("MergeOp rejected: fewer than two distinct source memories (%s)", op.source_ids)
        return None
    return op.model_copy(update={"source_ids": named})


def _guarded(
    op: ConsolidationOp, sources: Sequence[str], guard: NamedEntityGuard
) -> tuple[ConsolidationOp, bool] | None:
    """``op`` once the entity guard accepts its text, repaired when a merge lost critical entities.

    ``None`` when the guard rejects it.
    """
    candidate = _candidate_text(op)
    verdict = guard.verify_consolidation(
        source_texts=sources, consolidated_text=candidate, op_action=op.action, reasoning=op.reasoning
    )
    if verdict.is_valid:
        return op, False
    if isinstance(op, MergeOp) and verdict.missing_entities:
        patched = guard.patch_with_missing_entities(candidate, verdict.missing_entities)
        repaired = guard.verify_consolidation(
            source_texts=sources, consolidated_text=patched, op_action=op.action, reasoning=op.reasoning
        )
        if repaired.is_valid:
            logger.info(
                "Consolidation MergeOp auto-patched with %d missing technical entities: %s",
                len(verdict.missing_entities),
                verdict.rejection_code,
            )
            return op.model_copy(update={"merged_content": patched}), True
    logger.warning(
        "Consolidation op %s rejected by NamedEntityGuard (%s). Reason: %s",
        op.action,
        verdict.rejection_code,
        verdict.reason,
    )
    return None


def _review(
    op: ConsolidationOp, id_map: dict[str, str], texts: dict[str, str], window_facts: Facts, guard: NamedEntityGuard
) -> tuple[ConsolidationOp, bool] | None:
    """``op`` as it may proceed (full ids, repaired text) and whether the guard repaired it.

    ``None`` when a check refuses it.
    """
    score = op.accuracy_score * 0.4 + op.anti_fragmentation_score * 0.3 + op.redundancy_score * 0.3
    if score < _MIN_RUBRIC_SCORE:
        logger.info("Consolidation op %s rejected by Rubric (Score: %.2f). Reason: %s", op.action, score, op.reasoning)
        return None
    resolved = _resolved(op, id_map, texts)
    if resolved is None:
        return None
    named = _named_ids(resolved)
    sources = [texts[name] for name in named]
    # A merge is derived from its sources; a correction, rewrite or insight may draw on anything the model read.
    reference = facts_of(*sources) if isinstance(resolved, MergeOp) else window_facts
    unsupported = facts_of(_candidate_text(resolved)).beyond(reference)
    if not unsupported.is_empty:
        logger.info(
            "Consolidation op %s rejected by closure: %d number(s) and %d identifier(s) appear in no source text (%s)",
            resolved.action,
            len(unsupported.numbers),
            len(unsupported.identifiers),
            named,
        )
        return None
    return _guarded(resolved, sources, guard)


def _claim(op: ConsolidationOp, handled: set[str]) -> bool:
    """Keep ``op`` unless an earlier kept operation already handled a memory it names.

    The model plans every operation against the memories as they were read, so a later one on a memory that an
    earlier operation merged, corrected or rewrote would act on content that no longer exists.
    """
    targets = set(_named_ids(op))
    if targets & handled:
        logger.info("Consolidation op %s dropped: a memory it names was already handled this cycle", op.action)
        return False
    handled.update(targets)
    return True


def filter_and_guard_operations(
    raw_ops: Sequence[ConsolidationOp], memories: Sequence[AnyMemory], id_map: dict[str, str]
) -> FilteredOperations:
    """Keep the operations that pass every check needing no store access: at most one per memory, the first proposed."""
    if not raw_ops:
        return FilteredOperations([])
    texts = {memory.id: memory.content for memory in memories}
    window_facts = facts_of(*texts.values())
    guard = NamedEntityGuard()
    kept: list[ConsolidationOp] = []
    handled: set[str] = set()
    patched = rejected = 0
    for raw in raw_ops:
        reviewed = _review(raw, id_map, texts, window_facts, guard)
        if reviewed is None or not _claim(reviewed[0], handled):
            rejected += 1
            continue
        kept.append(reviewed[0])
        patched += reviewed[1]
    return FilteredOperations(kept, patched, rejected)


__all__ = ["FilteredOperations", "filter_and_guard_operations"]
