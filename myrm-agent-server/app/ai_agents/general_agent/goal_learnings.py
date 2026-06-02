"""Goal learnings extraction — server-side callback for post-goal memory capture.

[INPUT]
- myrm_agent_harness.toolkits.memory.strategies.extractor::extract_goal_learnings (POS: LLM-based goal learnings extraction)
- myrm_agent_harness.agent._internals.memory_extraction::create_extraction_llm_func, persist_extracted_memories (POS: LLM wrapper and persistence utilities)
- myrm_agent_harness.toolkits.memory.manager::MemoryManager (POS: memory lifecycle manager)

[OUTPUT]
- build_goal_terminal_callback: Factory for on_goal_terminal callback
- retrieve_relevant_learnings: Retrieve historical learnings for a new goal

[POS]
Server-layer integration for automatic goal learnings extraction. Provides the concrete
callback implementation injected into StreamContext.on_goal_terminal, and the retrieval
logic for enriching new goals with relevant historical learnings.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage
    from myrm_agent_harness.agent.goals.types import Goal, GoalExecutionSummary
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


def build_goal_terminal_callback(
    memory_manager: "MemoryManager",
    llm: "BaseChatModel",
) -> Callable[["Goal", list["BaseMessage"], "GoalExecutionSummary"], Awaitable[None]]:
    """Build the on_goal_terminal callback for goal learnings extraction and summary storage.

    This callback is fire-and-forget: it extracts forward-looking learnings from
    the full goal execution trace and persists them as SemanticMemory with
    'goal_learning' tag for future retrieval.
    """

    async def _on_goal_terminal(goal: "Goal", messages: list["BaseMessage"], summary: "GoalExecutionSummary") -> None:
        logger.info(
            "Goal %s terminal: %d files, %d tokens, $%.4f",
            goal.goal_id,
            len(summary.files_modified),
            summary.total_tokens,
            summary.total_cost_usd,
        )

        # Publish goal terminal notification to EventBus
        try:
            from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

            event_bus = get_event_bus()
            event_bus.publish(
                AppEvent(
                    event_type=AppEventType.GOAL_TERMINAL,
                    data={
                        "goal_id": goal.goal_id,
                        "session_id": goal.session_id,
                        "status": goal.status.value,
                        "objective": goal.objective[:200],
                        "files_modified": len(summary.files_modified),
                        "total_tokens": summary.total_tokens,
                        "total_cost_usd": round(summary.total_cost_usd, 4),
                    },
                )
            )
        except Exception as e:
            logger.warning("Failed to publish goal terminal event (non-fatal): %s", e)

        try:
            from myrm_agent_harness.agent._internals.memory_extraction import (
                create_extraction_llm_func,
                persist_extracted_memories,
            )
            from myrm_agent_harness.toolkits.memory.strategies.extractor import (
                extract_goal_learnings,
            )

            dict_messages = [
                {
                    "role": "assistant" if msg.type == "ai" else "user",
                    "content": str(msg.content),
                }
                for msg in messages
                if hasattr(msg, "content") and msg.content
            ]

            if len(dict_messages) < 3:
                logger.info("Goal %s: too few messages for learnings extraction", goal.goal_id)
            else:
                llm_func = create_extraction_llm_func(llm)
                learnings = await extract_goal_learnings(
                    messages=dict_messages,
                    goal_objective=goal.objective,
                    llm_func=llm_func,
                )

                if learnings:
                    stored_count = await persist_extracted_memories(
                        learnings,
                        memory_manager,
                        source_chat_id=goal.session_id,
                    )
                    logger.info(
                        "Goal %s: extracted %d learnings, stored %d",
                        goal.goal_id,
                        len(learnings),
                        stored_count,
                    )
                else:
                    logger.info("Goal %s: no learnings extracted", goal.goal_id)
        except Exception as e:
            logger.warning("Goal learnings extraction failed (non-fatal): %s", e, exc_info=True)

        # Dequeue next goal if available
        await _try_dequeue_next(goal.session_id)

    return _on_goal_terminal


async def _try_dequeue_next(session_id: str, *, _depth: int = 0) -> None:
    """Attempt to dequeue and start the next queued goal for a session."""
    if _depth >= 5:
        logger.warning("Dequeue recursion limit reached for session %s", session_id)
        return

    from app.services.agent.goal_registry import GoalRegistry

    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        return

    try:
        next_goal = await provider.dequeue_next(session_id)
    except Exception as e:
        logger.error("Failed to dequeue next goal for session %s: %s", session_id, e)
        return

    if not next_goal:
        logger.info("Queue empty for session %s, no more goals to execute", session_id)
        return

    logger.info(
        "Dequeued goal %s for session %s: %s",
        next_goal.goal_id,
        session_id,
        next_goal.objective[:60],
    )

    try:
        from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.GOAL_DEQUEUED,
                data={
                    "goal_id": next_goal.goal_id,
                    "session_id": session_id,
                    "objective": next_goal.objective[:200],
                },
            )
        )
    except Exception:
        pass

    try:
        from app.services.agent.goal_stream_trigger import trigger_goal_stream

        await trigger_goal_stream(session_id, next_goal)
    except Exception as e:
        logger.error(
            "Failed to start stream for dequeued goal %s: %s",
            next_goal.goal_id,
            e,
        )
        from myrm_agent_harness.agent.goals.types import GoalStatus

        try:
            await provider.update_status(next_goal.goal_id, GoalStatus.NEEDS_HUMAN_REVIEW)
        except Exception:
            logger.warning("Could not mark goal %s as NEEDS_HUMAN_REVIEW", next_goal.goal_id)
        await _try_dequeue_next(session_id, _depth=_depth + 1)


async def retrieve_relevant_learnings(
    memory_manager: "MemoryManager",
    objective: str,
    *,
    limit: int = 5,
) -> list[str]:
    """Retrieve relevant historical learnings for a new goal objective.

    Searches SemanticMemory with 'goal_learning' tag using the objective as query.
    Returns plain-text learnings suitable for injection into goal.metadata.
    """
    from myrm_agent_harness.toolkits.memory.types import MemoryType

    try:
        results = await memory_manager.search(
            query=objective,
            memory_types=[MemoryType.SEMANTIC],
            limit=limit,
        )
        # Filter for goal_learning tagged results
        learnings: list[str] = []
        for result in results:
            content = result.content
            if content and len(content.strip()) > 10:
                learnings.append(content.strip())

        if learnings:
            logger.info(
                "Retrieved %d relevant learnings for goal objective",
                len(learnings),
            )
        return learnings[:limit]
    except Exception as e:
        logger.warning("Failed to retrieve goal learnings (non-fatal): %s", e)
        return []
