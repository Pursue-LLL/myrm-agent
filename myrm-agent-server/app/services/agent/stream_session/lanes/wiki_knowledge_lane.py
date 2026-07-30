"""Chat Wiki Knowledge Quick Lane — zero-LLM wiki retrieval stream.

[INPUT]
- app.services.wiki.knowledge_query_service::execute_wiki_knowledge_query
- app.services.agent.params.helpers::_extract_text_from_query

[OUTPUT]
- create_wiki_knowledge_lane_stream(): SSE dict generator (SOURCES + MESSAGE + MESSAGE_END)

[POS]
Peer to Fast Lane; bypasses GeneralAgent for read-only wiki Q&A in Chat.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterable
from typing import TYPE_CHECKING, cast

from myrm_agent_harness.api import AgentEventType

from app.ai_agents.agents import GeneralAgentParams
from app.services.agent.params import MultimodalQuery, _extract_text_from_query
from app.services.wiki.knowledge_query_service import execute_wiki_knowledge_query

if TYPE_CHECKING:
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

logger = logging.getLogger(__name__)
_EXECUTION_LANE = "wiki_knowledge"


def _extract_lane_question(params: GeneralAgentParams) -> str:
    return _extract_text_from_query(cast(MultimodalQuery, params.query)).strip()


async def create_wiki_knowledge_lane_stream(
    params: GeneralAgentParams,
    cancel_token: CancellationToken | None,
) -> AsyncIterable[dict[str, object]]:
    """Build zero-LLM wiki retrieval SSE stream for eligible chat turns."""
    message_id = params.message_id or ""
    question = _extract_lane_question(params)

    yield {
        "type": AgentEventType.STATUS.value,
        "messageId": message_id,
        "step_key": "wiki_knowledge_lane",
        "status": "active",
        "data": {"phase": "query"},
    }

    try:
        query_result = await execute_wiki_knowledge_query(
            agent_id=params.agent_id,
            question=question,
            lite_model_cfg=params.lite_model_cfg,
            model_cfg=params.model_cfg,
        )
    except Exception as exc:
        logger.error("Wiki knowledge lane query failed: %s", exc, exc_info=True)
        yield {
            "type": AgentEventType.STATUS.value,
            "messageId": message_id,
            "step_key": "wiki_knowledge_lane_clear",
            "status": "failed",
            "data": {"error": str(exc)},
        }
        yield {
            "type": AgentEventType.MESSAGE.value,
            "messageId": message_id,
            "data": "Wiki query failed. Please retry or switch to full agent mode.",
        }
        yield {
            "type": AgentEventType.MESSAGE_END.value,
            "messageId": message_id,
            "usage": {},
            "completion_status": "failed",
            "execution_lane": _EXECUTION_LANE,
        }
        return

    if cancel_token and cancel_token.is_cancelled:
        return

    indexed_sources: list[dict[str, object]] = []
    for index, source in enumerate(query_result.sources, start=1):
        entry = {**source, "index": index}
        if params.agent_id:
            entry["agent_id"] = params.agent_id
        indexed_sources.append(entry)

    if indexed_sources:
        yield {
            "type": AgentEventType.SOURCES.value,
            "messageId": message_id,
            "data": indexed_sources,
        }

    yield {
        "type": AgentEventType.MESSAGE.value,
        "messageId": message_id,
        "data": query_result.answer,
    }

    yield {
        "type": AgentEventType.STATUS.value,
        "messageId": message_id,
        "step_key": "wiki_knowledge_lane_clear",
        "status": "done",
        "data": {
            "confidence_score": query_result.confidence_score,
            "source_count": len(indexed_sources),
        },
    }

    yield {
        "type": AgentEventType.MESSAGE_END.value,
        "messageId": message_id,
        "usage": {},
        "completion_status": "success",
        "execution_lane": _EXECUTION_LANE,
        "wiki_confidence_score": query_result.confidence_score,
        "wiki_source_count": len(indexed_sources),
    }
