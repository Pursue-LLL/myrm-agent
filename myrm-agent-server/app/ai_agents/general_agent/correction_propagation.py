"""Implicit-feedback correction propagation for the General Agent session cleanup.

[INPUT]
- app.services.event.app_event_bus::AppEvent (POS: 应用内事件总线)
- app.services.memory.shared_context.shared_context::SharedContextService (POS: 共享上下文业务服务)
- app.services.memory.shared_context.shared_context_materializer::SharedContextProposalMaterializer (POS: 共享上下文写入物化服务)

[OUTPUT]
- build_correction_proposal_source_id: 纠错提案幂等 source_id 构造
- make_correction_propagation_callback: 会话清理纠错传播回调工厂

[POS]
会话结束时的隐式纠错传播。两阶段检测用户纠正信号，产出结构化纠错提案，分别路由到
Harness 审批队列（个人记忆，HITL）与绑定的 SharedContext 写入提案。
"""

import hashlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, cast, get_args

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory import MemoryManager
    from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import CorrectionProposal

logger = logging.getLogger(__name__)

_CORRECTION_SOURCE_ID_HASH_LENGTH = 16


def build_correction_proposal_source_id(chat_id: str | None, summary: str) -> str:
    """Build a stable idempotency key for correction propagation proposals."""
    normalized_chat = (chat_id or "unknown").strip() or "unknown"
    content_hash = hashlib.sha256(summary.encode()).hexdigest()[:_CORRECTION_SOURCE_ID_HASH_LENGTH]
    source_id = f"{normalized_chat}:{content_hash}"
    return source_id[:255]


def make_correction_propagation_callback(
    agent_id: str,
    llm_func: Callable[[str, str], Awaitable[str]],
    *,
    memory_manager: "MemoryManager | None" = None,
) -> Callable[[Sequence[dict[str, str]], str | None], Awaitable[None]]:
    """Create a session cleanup callback that detects implicit corrections and propagates them.

    Uses the two-stage implicit feedback pipeline (regex fast-path + LLM deep scan)
    to detect both explicit and implicit user corrections. Produces structured correction
    proposals routed to:
    1. Agent personal memory — submitted to the harness approval queue (HITL), so the
       user approves them through the same Governance surface as every other memory.
    2. SharedContexts — via SharedContext write proposals (policy-based auto-approve)
    """

    async def _propagate(messages: Sequence[dict[str, str]], chat_id: str | None) -> None:
        try:
            await _run_correction_propagation(
                list(messages),
                agent_id=agent_id,
                llm_func=llm_func,
                chat_id=chat_id,
                memory_manager=memory_manager,
            )
        except Exception:
            logger.error("Correction propagation failed", exc_info=True)

    return _propagate


async def _run_correction_propagation(
    messages: list[dict[str, str]],
    *,
    agent_id: str,
    llm_func: Callable[[str, str], Awaitable[str]],
    chat_id: str | None,
    memory_manager: "MemoryManager | None" = None,
) -> None:
    """Core logic: implicit feedback detection → structured planning → dual-target proposals."""
    from myrm_agent_harness.toolkits.memory.strategies.extractor import FeedbackSignal
    from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
        detect_implicit_feedback,
    )

    if len(messages) < 2:
        return

    recalled = await _recall_candidate_memories(messages, memory_manager)
    result = await detect_implicit_feedback(
        messages,
        llm_func,
        existing_memories=[f"[id: {memory_id}] {content}" for memory_id, content in recalled.items()] or None,
    )

    if result.signal != FeedbackSignal.NEGATIVE:
        return

    if not result.proposals:
        logger.info(
            "Correction signal detected for agent %s but planner produced no proposals",
            agent_id,
        )
        return

    logger.info(
        "Implicit feedback: agent=%s signal=%s implicit=%s proposals=%d",
        agent_id,
        result.signal,
        result.has_implicit_contradiction,
        len(result.proposals),
    )

    await _route_proposals_to_personal_memory(
        result.proposals,
        agent_id=agent_id,
        chat_id=chat_id,
        memory_manager=memory_manager,
        recalled=recalled,
    )

    await _route_proposals_to_shared_contexts(result.proposals, agent_id=agent_id, chat_id=chat_id)


async def _recall_candidate_memories(
    messages: list[dict[str, str]],
    memory_manager: "MemoryManager | None",
    *,
    limit: int = 8,
) -> dict[str, str]:
    """Recall memories related to the latest user turns, keyed by id → content.

    Gives the correction planner concrete targets (with stable ids) so UPDATE and
    DELETE proposals can name the memory they supersede. Restricted to semantic
    memories because correction/removal only apply to factual knowledge — a
    planner should never be handed an id it cannot safely correct. Best-effort:
    a recall failure never blocks correction propagation.
    """
    from myrm_agent_harness.toolkits.memory import MemoryType

    if memory_manager is None:
        return {}

    recent_user_text = " ".join(
        m.get("content", "")[:300] for m in messages[-4:] if m.get("role") == "user" and m.get("content")
    ).strip()
    if not recent_user_text:
        return {}

    recalled: dict[str, str] = {}
    try:
        results = await memory_manager.search(
            recent_user_text,
            memory_types=[MemoryType.SEMANTIC],
            limit=limit,
            track_access=False,
        )
    except Exception:
        logger.warning("Memory recall for correction planner failed", exc_info=True)
        return {}

    for item in results:
        memory = item.memory
        if not getattr(memory, "content", None):
            continue
        recalled[memory.id] = memory.content
    return recalled


async def _route_proposals_to_personal_memory(
    proposals: "list[CorrectionProposal]",
    *,
    agent_id: str,
    chat_id: str | None,
    memory_manager: "MemoryManager | None" = None,
    recalled: dict[str, str] | None = None,
) -> None:
    """Submit correction proposals to the harness approval queue (HITL single source of truth).

    Each proposal is materialised as a SemanticMemory and routed through
    ``MemoryManager.submit_pending`` so it lands in the same ``pending_records``
    store the WebUI approval surface reads. UPDATE proposals become linked
    corrections of their recalled target; DELETE proposals record a removal.
    """
    from myrm_agent_harness.toolkits.memory.strategies.extractor import detect_language
    from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import CorrectionAction
    from myrm_agent_harness.toolkits.memory.types import PendingResolutionAction, SemanticMemory

    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    if memory_manager is None:
        logger.info(
            "Implicit feedback proposals detected for agent %s but no memory manager is bound; skipping personal queue",
            agent_id,
        )
        return

    recalled = recalled or {}
    created_count = 0
    for proposal in proposals:
        target_memory_id = _resolve_target_memory_id(proposal, recalled)
        if proposal.action in (CorrectionAction.UPDATE, CorrectionAction.DELETE) and target_memory_id is None:
            # A correction/removal without a concrete target is not actionable.
            logger.info(
                "Skipping %s correction proposal without a resolvable target: %s",
                proposal.action.value,
                proposal.content[:80],
            )
            continue

        action = {
            CorrectionAction.ADD: PendingResolutionAction.STORE,
            CorrectionAction.UPDATE: PendingResolutionAction.CORRECT,
            CorrectionAction.DELETE: PendingResolutionAction.DELETE,
        }[proposal.action]

        # The review surface shows which memory will be replaced or removed, so
        # the user can tell an addition apart from a destructive correction.
        target_content = recalled.get(target_memory_id) if target_memory_id else None

        memory = SemanticMemory(
            id=build_correction_proposal_source_id(chat_id, proposal.content),
            content=proposal.content,
            confidence=proposal.confidence,
            importance=min(proposal.confidence, 1.0),
            source_chat_id=chat_id,
            language=detect_language(proposal.content),
        )
        try:
            pending_id = await memory_manager.submit_pending(
                memory,
                resolution_action=action,
                target_memory_id=target_memory_id,
                target_content=target_content,
            )
        except Exception:
            logger.warning(
                "Failed to queue correction proposal (action=%s, content=%s)",
                proposal.action.value,
                proposal.content[:80],
                exc_info=True,
            )
            continue
        if pending_id:
            created_count += 1

    if created_count > 0:
        logger.info(
            "Queued %d pending memory proposals from implicit feedback: agent=%s",
            created_count,
            agent_id,
        )
        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.MEMORY_OPERATION,
                data={
                    "operation": "implicit_feedback_personal",
                    "agent_id": agent_id,
                    "proposal_count": created_count,
                    "source_chat_id": chat_id or "",
                },
            )
        )


def _resolve_target_memory_id(proposal: object, recalled: dict[str, str]) -> str | None:
    """Resolve the memory a correction targets, from the recalled candidate set only.

    The planner only ever sees ids from ``recalled`` and cannot reliably echo a
    UUID back, so an explicit id is trusted only when it names a candidate that
    was actually offered this turn — a hallucinated or stale id must not shadow
    the content match, or the correction would silently degrade to an addition.
    Content matching is used only when unambiguous: picking among several
    candidates would demote the wrong memory, so an ambiguous ``old_content``
    yields ``None`` (the proposal is skipped) rather than a guess.
    """
    explicit = getattr(proposal, "target_memory_id", None)
    if explicit and str(explicit) in recalled:
        return str(explicit)

    old_content = getattr(proposal, "old_content", None)
    if not old_content:
        return None

    normalized = old_content.strip().lower()
    if not normalized:
        return None

    for memory_id, content in recalled.items():
        if content.strip().lower() == normalized:
            return memory_id

    matches = [memory_id for memory_id, content in recalled.items() if normalized in content.lower()]
    return matches[0] if len(matches) == 1 else None


async def _route_proposals_to_shared_contexts(
    proposals: "list[CorrectionProposal]",
    *,
    agent_id: str,
    chat_id: str | None,
) -> None:
    """Route correction proposals to all SharedContexts bound to this Agent."""
    from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import CorrectionAction

    from app.database.connection import get_session
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
    from app.services.memory.shared_context.shared_context import (
        SharedContextMemoryType,
        SharedContextService,
        resolve_shared_context_ids,
    )
    from app.services.memory.shared_context.shared_context_materializer import SharedContextProposalMaterializer

    context_ids = await resolve_shared_context_ids(agent_id=agent_id)
    if not context_ids:
        return

    # The planner may also emit memory types a SharedContext cannot hold (e.g. procedural);
    # those are skipped so one of them cannot abort routing of the remaining proposals.
    holdable_types = frozenset(get_args(SharedContextMemoryType))
    candidates = [p for p in proposals if p.action in (CorrectionAction.ADD, CorrectionAction.UPDATE)]
    add_or_update_proposals = [p for p in candidates if p.memory_type in holdable_types]
    if len(add_or_update_proposals) < len(candidates):
        logger.info(
            "Skipping %d correction proposal(s) whose memory type a SharedContext cannot hold",
            len(candidates) - len(add_or_update_proposals),
        )
    if not add_or_update_proposals:
        return

    async with get_session() as session:
        svc = SharedContextService(session)
        materializer = SharedContextProposalMaterializer(session)

        for context_id in context_ids:
            context = await svc.get_context(context_id)
            if context is None or context.status != "active":
                continue

            policy = context.policy or {}
            auto_approve = policy.get("correction_auto_approve") is not False

            for proposal in add_or_update_proposals:
                sc_proposal = await svc.create_write_proposal(
                    context_id=context_id,
                    memory_type=cast(SharedContextMemoryType, proposal.memory_type),
                    content=proposal.content,
                    metadata={
                        "source_agent_id": agent_id,
                        "source_chat_id": chat_id or "",
                        "propagation_type": "implicit_feedback",
                        "action": proposal.action.value,
                        "reasoning": proposal.reasoning,
                        "old_content": proposal.old_content,
                    },
                    source_type="implicit_feedback",
                    source_id=build_correction_proposal_source_id(chat_id, proposal.content),
                )
                if sc_proposal is None or sc_proposal.status in ("approved", "rejected"):
                    continue

                if auto_approve:
                    await materializer.approve_write_proposal(sc_proposal.id)

                get_event_bus().publish(
                    AppEvent(
                        event_type=AppEventType.MEMORY_OPERATION,
                        data={
                            "operation": "implicit_feedback_shared",
                            "context_id": context_id,
                            "context_name": context.name,
                            "proposal_id": sc_proposal.id,
                            "agent_id": agent_id,
                            "auto_approved": bool(auto_approve),
                            "content": proposal.content[:200],
                        },
                    )
                )
