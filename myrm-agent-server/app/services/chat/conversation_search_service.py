"""Conversation recall service for agent tools.

[INPUT]
app.database.repositories.conversation_recall::ConversationRecallRepository (POS: Conversation Recall 索引仓储)
app.services.chat.conversation_recall_index_service::ConversationRecallIndexService (POS: Conversation Recall 索引生命周期服务)
myrm_agent_harness.toolkits.memory.protocols.conversation_search::ConversationSearchProtocol (POS: conversation search protocol boundary)

[OUTPUT]
ConversationHistorySearchProvider: Server adapter implementing Harness conversation search protocol.
ConversationSearchService: Business service for FTS5 conversation recall, index coverage reporting, cron source demotion, and expand_message_id windows.

[POS]
会话历史召回服务。将 Server 的 Chat DB、FTS5 与预计算摘要组合为 agent 可用的只读工具能力。
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

from myrm_agent_harness.api import (
    RankedList,
    fuse_rrf_deterministic,
)
from myrm_agent_harness.toolkits.memory.conversation_search.types import (
    ConversationIndexCoverage,
    ConversationSearchHit,
    ConversationSearchRequest,
    ConversationSearchResponse,
    ConversationSourceRef,
)
from myrm_agent_harness.utils.db.fts5 import sanitize_fts5_query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall import (
    ConversationRecallContext,
    ConversationRecallLookupRepository,
    ConversationRecallRepository,
    ConversationRecallRow,
)
from app.database.repositories.uow import UnitOfWork
from app.services.chat.chat_helpers import _sanitize_snippet
from app.services.chat.conversation_recall_index_service import (
    ConversationRecallIndexService,
)
from app.services.chat.conversation_recall_query import (
    ConversationRecallFtsQuery,
    build_conversation_recall_fts_queries,
)

logger = logging.getLogger(__name__)

FTS_CANDIDATE_MULTIPLIER = 5
MAX_FTS_CANDIDATES = 48
SAME_AGENT_BOOST = 0.06
_DEMOTED_CHAT_SOURCES = frozenset({"cron"})
_INTERACTIVE_CHAT_SOURCES = frozenset({"web", "feishu", "telegram", "wechat", "discord", "slack"})


class ConversationHistorySearchProvider:
    """Server-side Harness protocol adapter bound to one agent run."""

    def __init__(
        self,
        *,
        current_chat_id: str | None,
        agent_id: str | None,
        default_scope: str | None = None,
    ) -> None:
        self._current_chat_id = current_chat_id
        self._agent_id = agent_id
        self._default_scope = default_scope

    async def search(self, request: ConversationSearchRequest) -> ConversationSearchResponse:
        updates: dict[str, object] = {"current_conversation_id": request.current_conversation_id or self._current_chat_id}
        if self._default_scope:
            updates["scope"] = self._default_scope
        effective = request.model_copy(update=updates)
        return await ConversationSearchService.search(effective, agent_id=self._agent_id)


class ConversationSearchService:
    """Conversation-level FTS5 recall."""

    @staticmethod
    async def set_chat_excluded(chat_id: str, excluded: bool) -> bool:
        result: object = await ConversationRecallIndexService.set_chat_excluded(chat_id, excluded)
        return bool(result)

    @staticmethod
    async def health() -> dict[str, object]:
        result: object = await ConversationRecallIndexService.health()
        return dict(result) if isinstance(result, dict) else {}

    @staticmethod
    async def _compute_coverage() -> ConversationIndexCoverage | None:
        try:
            health_data = await ConversationRecallIndexService.health()
            if not isinstance(health_data, dict):
                return None
            indexed = int(health_data.get("indexed_conversations") or 0)
            missing = int(health_data.get("missing_conversations") or 0)
            fts_ready = bool(health_data.get("fts_ready", True))
            total = indexed + missing
            ratio = (indexed / total) if total > 0 else 1.0
            return ConversationIndexCoverage(
                total_conversations=total,
                indexed_conversations=indexed,
                coverage_ratio=max(0.0, min(1.0, ratio)),
                unindexed_recent_count=missing,
                indexing_degraded=not fts_ready,
            )
        except Exception:
            return None

    @staticmethod
    async def search(
        request: ConversationSearchRequest,
        *,
        agent_id: str | None,
    ) -> ConversationSearchResponse:
        if request.expand_message_id and request.expand_conversation_id:
            return await ConversationSearchService._expand_message_window(
                request,
                agent_id=agent_id,
            )

        query = request.query.strip()
        if request.mode == "recent" or not query:
            return await ConversationSearchService._recent(request, agent_id=agent_id)

        safe_query = sanitize_fts5_query(query)
        fts_queries = build_conversation_recall_fts_queries(query, safe_query)
        fts_hits, relaxed_used, effective_tokens = await ConversationSearchService._search_fts(
            request,
            fts_queries=fts_queries,
            agent_id=agent_id,
        )
        ranked_hits, recall_debug = _rank_fts_hits(fts_hits, request.limit)
        hits = [hit for hit in ranked_hits if hit.score >= request.min_score]
        rejected_reason = None if hits else "No sufficiently relevant previous conversations found."
        coverage = await ConversationSearchService._compute_coverage()
        return ConversationSearchResponse(
            mode="search",
            hits=hits,
            query=query,
            rejected_reason=rejected_reason,
            coverage=coverage,
            relaxed=relaxed_used,
            query_tokens=effective_tokens,
            recall_debug=recall_debug,
        )

    @staticmethod
    async def _recent(
        request: ConversationSearchRequest,
        *,
        agent_id: str | None,
    ) -> ConversationSearchResponse:
        coverage = await ConversationSearchService._compute_coverage()
        async with UnitOfWork() as uow:
            session = uow.session
            if session is None:
                return ConversationSearchResponse(mode="recent", hits=[], query="", coverage=coverage)
            context = await _conversation_context(session, request, agent_id)
            lineage_chat_ids = await _lineage_chat_ids(session, request)
            if request.lineage != "all" and not lineage_chat_ids:
                return ConversationSearchResponse(mode="recent", hits=[], query="", coverage=coverage)
            rows = await ConversationRecallRepository.recent(
                session,
                limit=request.limit,
                current_chat_id=request.current_conversation_id,
                agent_id=context.agent_id,
                current_source=context.source,
                scope=request.scope,
                lineage_chat_ids=lineage_chat_ids,
                since=request.since,
                until=request.until,
            )
        hits = [_recent_hit(row, index, agent_id) for index, row in enumerate(rows)]
        return ConversationSearchResponse(mode="recent", hits=hits, query="", coverage=coverage)

    @staticmethod
    async def _expand_message_window(
        request: ConversationSearchRequest,
        *,
        agent_id: str | None,
    ) -> ConversationSearchResponse:
        chat_id = (request.expand_conversation_id or "").strip()
        message_id = (request.expand_message_id or "").strip()
        if not chat_id or not message_id:
            return ConversationSearchResponse(
                mode="search",
                hits=[],
                query=request.query,
                rejected_reason="expand requires expand_conversation_id and expand_message_id.",
            )

        async with UnitOfWork() as uow:
            session = uow.session
            if session is None:
                return ConversationSearchResponse(mode="search", hits=[], query=request.query)
            segments = await ConversationRecallLookupRepository.fetch_message_window(
                session,
                chat_id=chat_id,
                message_id=message_id,
                window=request.expand_window,
                current_chat_id=request.current_conversation_id,
                agent_id=agent_id,
                scope=request.scope,
            )
            if not segments:
                return ConversationSearchResponse(
                    mode="search",
                    hits=[],
                    query=request.query,
                    rejected_reason="No visible messages found for the requested expand window.",
                )

        from app.services.chat.chat_crud import _ChatCrudMixin

        chat_meta = await _ChatCrudMixin.get_chat_metadata(chat_id)
        title = chat_meta.title if chat_meta is not None else None

        lines = [f"{segment.role}: {segment.segment_text}" for segment in segments]
        expanded_snippet = "\n".join(lines)
        hit = ConversationSearchHit(
            conversation_id=chat_id,
            title=title,
            snippet=_sanitize_snippet(expanded_snippet),
            summary=None,
            score=1.0,
            source="conversation_index",
            message_id=message_id,
            source_ref=ConversationSourceRef(
                conversation_id=chat_id,
                message_id=message_id,
                title=title,
                snippet=_sanitize_snippet(expanded_snippet),
                score=1.0,
            ),
        )
        return ConversationSearchResponse(mode="search", hits=[hit], query=request.query)

    @staticmethod
    async def _search_fts(
        request: ConversationSearchRequest,
        *,
        fts_queries: list[ConversationRecallFtsQuery],
        agent_id: str | None,
    ) -> tuple[list[ConversationSearchHit], bool, list[str]]:
        if not fts_queries:
            return [], False, []
        candidate_limit = min(
            MAX_FTS_CANDIDATES,
            max(request.limit * FTS_CANDIDATE_MULTIPLIER, request.limit),
        )
        relaxed_used = False
        effective_tokens: list[str] = []
        async with UnitOfWork() as uow:
            session = uow.session
            if session is None:
                return [], False, []
            context = await _conversation_context(session, request, agent_id)
            lineage_chat_ids = await _lineage_chat_ids(session, request)
            if request.lineage != "all" and not lineage_chat_ids:
                return [], False, []
            hits: list[ConversationSearchHit] = []
            seen_chat_ids: set[str] = set()
            for planned in fts_queries:
                if hits and len(hits) >= request.limit:
                    break
                rows = await ConversationRecallRepository.search(
                    session,
                    safe_query=planned.query,
                    limit=candidate_limit,
                    current_chat_id=request.current_conversation_id,
                    agent_id=context.agent_id,
                    current_source=context.source,
                    scope=request.scope,
                    lineage_chat_ids=lineage_chat_ids,
                    since=request.since,
                    until=request.until,
                )
                if rows:
                    effective_tokens = list(planned.tokens)
                    if planned.is_relaxed:
                        relaxed_used = True
                new_rows = [row for row in rows if row.chat_id not in seen_chat_ids]
                scored_candidates = [
                    (
                        row,
                        _fts_hit(
                            row,
                            index,
                            len(rows),
                            agent_id,
                            score_weight=planned.score_weight,
                        ),
                    )
                    for index, row in enumerate(new_rows)
                ]
                scored_candidates.sort(key=lambda pair: pair[1].score, reverse=True)
                for _, hit in scored_candidates:
                    hits.append(hit)
                    seen_chat_ids.add(hit.conversation_id)
                    if len(hits) >= candidate_limit:
                        return hits, relaxed_used, effective_tokens
        return hits, relaxed_used, effective_tokens


async def _conversation_context(
    session: AsyncSession,
    request: ConversationSearchRequest,
    fallback_agent_id: str | None,
) -> ConversationRecallContext:
    if request.current_conversation_id:
        context = await ConversationRecallRepository.get_context(session, request.current_conversation_id)
        if context is not None:
            return ConversationRecallContext(
                chat_id=context.chat_id,
                agent_id=fallback_agent_id or context.agent_id,
                source=context.source,
            )
    return ConversationRecallContext(
        chat_id=request.current_conversation_id or "",
        agent_id=fallback_agent_id,
        source=None,
    )


async def _lineage_chat_ids(session: AsyncSession, request: ConversationSearchRequest) -> list[str]:
    if request.lineage == "all" or not request.current_conversation_id:
        return []
    lineage: object = await ConversationRecallRepository.get_lineage_chat_ids(
        session,
        request.current_conversation_id,
        request.lineage,
    )
    return [str(chat_id) for chat_id in lineage] if isinstance(lineage, list) else []


def _fts_hit(
    row: ConversationRecallRow,
    index: int,
    total: int,
    agent_id: str | None,
    *,
    score_weight: float = 1.0,
) -> ConversationSearchHit:
    position_score = 1.0 - (index / max(total, 1)) * 0.35
    recency_score = _recency_score(row.updated_at or row.last_message_at)
    rank_score = _rank_score(row.rank)
    score = (
        rank_score * 0.52
        + position_score * 0.30
        + recency_score * 0.12
        + _same_agent_boost(row.agent_id, agent_id)
        + _source_interaction_boost(row.source)
    )
    score = _clamp(score * score_weight)
    return ConversationSearchHit(
        conversation_id=row.chat_id,
        title=row.title,
        snippet=_sanitize_snippet(row.snippet),
        summary=row.summary,
        score=score,
        source="conversation_index",
        message_id=row.message_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata={"agent_id": row.agent_id or "", "source": row.source},
        source_ref=_source_ref(row, score=score, lineage=None),
    )


def _recent_hit(row: ConversationRecallRow, index: int, agent_id: str | None) -> ConversationSearchHit:
    score = 0.92 - min(index, 10) * 0.035 + _same_agent_boost(row.agent_id, agent_id)
    score += _source_interaction_boost(row.source)
    score = _clamp(score)
    return ConversationSearchHit(
        conversation_id=row.chat_id,
        title=row.title,
        snippet=_sanitize_snippet(row.snippet),
        summary=row.summary,
        score=score,
        source="recent",
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata={"agent_id": row.agent_id or "", "source": row.source},
        source_ref=_source_ref(row, score=score, lineage=None),
    )


def _copy_source_ref_score(source_ref: ConversationSourceRef | None, score: float) -> ConversationSourceRef | None:
    if source_ref is None:
        return None
    return source_ref.model_copy(update={"score": score})


def _rank_fts_hits(
    fts_hits: list[ConversationSearchHit],
    limit: int,
) -> tuple[list[ConversationSearchHit], dict[str, object]]:
    """Re-score FTS hits by rank with deterministic RRF, normalized to [0, 1] for the ``min_score`` filter."""
    fused_results, recall_debug = fuse_rrf_deterministic(
        [RankedList(source="conversation_fts", items=fts_hits)],
        key_func=lambda h: h.conversation_id,
        top_k=limit,
    )
    ranked = [
        f_hit.item.model_copy(
            update={
                "score": f_hit.score,
                "source_ref": _copy_source_ref_score(f_hit.item.source_ref, f_hit.score),
            }
        )
        for f_hit in fused_results
    ]
    debug_dict: dict[str, object] = {
        "fused_count": recall_debug.fused_count,
        "per_source": [
            {
                "source": s.source,
                "count": s.count,
                "latency_ms": s.latency_ms,
            }
            for s in recall_debug.per_source
        ],
    }
    return ranked, debug_dict


def _same_agent_boost(row_agent_id: str | None, current_agent_id: str | None) -> float:
    if row_agent_id and current_agent_id and row_agent_id == current_agent_id:
        return SAME_AGENT_BOOST
    return 0.0


def _source_interaction_boost(chat_source: str | None) -> float:
    normalized = (chat_source or "").strip().lower()
    if normalized in _DEMOTED_CHAT_SOURCES:
        return -0.10
    if normalized in _INTERACTIVE_CHAT_SOURCES:
        return 0.06
    return 0.0


def _recency_score(value: datetime | None) -> float:
    if value is None:
        return 0.0
    now = datetime.now(UTC)
    timestamp = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    age_days = max((now - timestamp).total_seconds() / 86_400, 0.0)
    return math.exp(-age_days / 30.0)


def _rank_score(rank: float) -> float:
    return 1.0 / (1.0 + abs(rank))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _source_ref(
    row: ConversationRecallRow,
    *,
    score: float,
    lineage: str | None,
) -> ConversationSourceRef:
    return ConversationSourceRef(
        conversation_id=row.chat_id,
        message_id=row.message_id,
        title=row.title,
        snippet=_sanitize_snippet(row.snippet),
        summary=row.summary,
        score=score,
        agent_id=row.agent_id,
        surface=row.source,
        fork_parent_id=row.fork_parent_id,
        lineage=lineage,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
