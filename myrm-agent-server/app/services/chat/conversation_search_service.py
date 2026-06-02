"""Conversation recall service for agent tools.

[INPUT]
app.database.repositories.conversation_recall_repo::ConversationRecallRepository (POS: Conversation Recall 索引仓储)
app.services.chat.conversation_recall_index_service::ConversationRecallIndexService (POS: Conversation Recall 索引生命周期服务)
myrm_agent_harness.toolkits.memory.protocols.conversation_search::ConversationSearchProtocol (POS: conversation search protocol boundary)

[OUTPUT]
ConversationHistorySearchProvider: Server adapter implementing Harness conversation search protocol.
ConversationSearchService: Business service for exact + semantic conversation recall.

[POS]
会话历史召回服务。将 Server 的 Chat DB、FTS5、预计算摘要与 Harness MemoryManager 语义召回组合为 agent 可用的只读工具能力。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory.conversation_search.types import (
    ConversationSearchHit,
    ConversationSearchRequest,
    ConversationSearchResponse,
    ConversationSourceRef,
)
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import ConversationMemory, MemoryType
from myrm_agent_harness.utils.db.fts5 import sanitize_fts5_query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall_lookup_repo import ConversationRecallLookupRepository
from app.database.repositories.conversation_recall_repo import (
    ConversationRecallContext,
    ConversationRecallRepository,
    ConversationRecallRow,
)
from app.database.repositories.uow import UnitOfWork
from app.services.chat.chat_helpers import _sanitize_snippet
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService
from app.services.chat.conversation_recall_query import (
    ConversationRecallFtsQuery,
    build_conversation_recall_fts_queries,
)

logger = logging.getLogger(__name__)

FTS_CANDIDATE_MULTIPLIER = 5
MAX_FTS_CANDIDATES = 48
SAME_AGENT_BOOST = 0.06
SEMANTIC_SCORE_WEIGHT = 0.9


@dataclass(frozen=True, slots=True)
class _SemanticCandidate:
    conversation_id: str
    message_id: str | None
    summary: str
    score: float
    metadata: dict[str, str | int | float | bool]
    created_at: datetime | None
    updated_at: datetime | None


class ConversationHistorySearchProvider:
    """Server-side Harness protocol adapter bound to one agent run."""

    def __init__(
        self,
        *,
        current_chat_id: str | None,
        agent_id: str | None,
        memory_manager: MemoryManager | None,
    ) -> None:
        self._current_chat_id = current_chat_id
        self._agent_id = agent_id
        self._memory_manager = memory_manager

    async def search(self, request: ConversationSearchRequest) -> ConversationSearchResponse:
        effective = request.model_copy(
            update={"current_conversation_id": request.current_conversation_id or self._current_chat_id}
        )
        return await ConversationSearchService.search(
            effective,
            agent_id=self._agent_id,
            memory_manager=self._memory_manager,
        )


class ConversationSearchService:
    """Conversation-level exact and semantic recall."""

    @staticmethod
    async def set_chat_excluded(chat_id: str, excluded: bool) -> bool:
        result: object = await ConversationRecallIndexService.set_chat_excluded(chat_id, excluded)
        return bool(result)

    @staticmethod
    async def health() -> dict[str, object]:
        result: object = await ConversationRecallIndexService.health()
        return dict(result) if isinstance(result, dict) else {}

    @staticmethod
    async def search(
        request: ConversationSearchRequest,
        *,
        agent_id: str | None,
        memory_manager: MemoryManager | None,
    ) -> ConversationSearchResponse:
        query = request.query.strip()
        if request.mode == "recent" or not query:
            return await ConversationSearchService._recent(request, agent_id=agent_id)

        safe_query = sanitize_fts5_query(query)
        fts_queries = build_conversation_recall_fts_queries(query, safe_query)
        fts_hits = await ConversationSearchService._search_fts(
            request,
            fts_queries=fts_queries,
            agent_id=agent_id,
        )
        semantic_hits = await ConversationSearchService._search_semantic(
            request,
            agent_id=agent_id,
            memory_manager=memory_manager,
        )
        hits = [
            hit
            for hit in _merge_hits(fts_hits, semantic_hits, request.limit)
            if hit.score >= request.min_score
        ]
        rejected_reason = None if hits else "No sufficiently relevant previous conversations found."
        return ConversationSearchResponse(mode="search", hits=hits, query=query, rejected_reason=rejected_reason)

    @staticmethod
    async def _recent(
        request: ConversationSearchRequest,
        *,
        agent_id: str | None,
    ) -> ConversationSearchResponse:
        async with UnitOfWork() as uow:
            session = uow.session
            if session is None:
                return ConversationSearchResponse(mode="recent", hits=[], query="")
            context = await _conversation_context(session, request, agent_id)
            lineage_chat_ids = await _lineage_chat_ids(session, request)
            if request.lineage != "all" and not lineage_chat_ids:
                return ConversationSearchResponse(mode="recent", hits=[], query="")
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
        return ConversationSearchResponse(mode="recent", hits=hits, query="")

    @staticmethod
    async def _search_fts(
        request: ConversationSearchRequest,
        *,
        fts_queries: list[ConversationRecallFtsQuery],
        agent_id: str | None,
    ) -> list[ConversationSearchHit]:
        if not fts_queries:
            return []
        candidate_limit = min(MAX_FTS_CANDIDATES, max(request.limit * FTS_CANDIDATE_MULTIPLIER, request.limit))
        async with UnitOfWork() as uow:
            session = uow.session
            if session is None:
                return []
            context = await _conversation_context(session, request, agent_id)
            lineage_chat_ids = await _lineage_chat_ids(session, request)
            if request.lineage != "all" and not lineage_chat_ids:
                return []
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
                new_rows = [row for row in rows if row.chat_id not in seen_chat_ids]
                for index, row in enumerate(new_rows):
                    hits.append(_fts_hit(row, index, len(rows), agent_id, score_weight=planned.score_weight))
                    seen_chat_ids.add(row.chat_id)
                    if len(hits) >= candidate_limit:
                        return hits
        return hits

    @staticmethod
    async def _search_semantic(
        request: ConversationSearchRequest,
        *,
        agent_id: str | None,
        memory_manager: MemoryManager | None,
    ) -> list[ConversationSearchHit]:
        if memory_manager is None:
            return []
        candidate_limit = min(MAX_FTS_CANDIDATES, max(request.limit * FTS_CANDIDATE_MULTIPLIER, request.limit))
        try:
            results = await memory_manager.search(
                request.query,
                memory_types=[MemoryType.CONVERSATION],
                limit=candidate_limit,
                include_raw=False,
                since=request.since,
                until=request.until,
            )
        except Exception as exc:
            logger.warning("Conversation semantic search failed: %s", exc)
            return []

        candidates: list[_SemanticCandidate] = []
        for result in results:
            memory = result.memory
            if not isinstance(memory, ConversationMemory):
                continue
            conversation_id = memory.source_chat_id or memory.id
            if request.current_conversation_id and conversation_id == request.current_conversation_id:
                continue
            score = _clamp(result.score * SEMANTIC_SCORE_WEIGHT)
            if score < request.min_score:
                continue
            candidates.append(
                _SemanticCandidate(
                    conversation_id=conversation_id,
                    message_id=memory.source_message_id,
                    summary=memory.content,
                    score=score,
                    metadata=memory.metadata,
                    created_at=memory.created_at,
                    updated_at=memory.updated_at,
                )
            )
        return await _hydrate_semantic_hits(candidates, request=request, agent_id=agent_id)


async def _hydrate_semantic_hits(
    candidates: list[_SemanticCandidate],
    *,
    request: ConversationSearchRequest,
    agent_id: str | None,
) -> list[ConversationSearchHit]:
    if not candidates:
        return []
    chat_message_ids = {candidate.conversation_id: candidate.message_id for candidate in candidates}
    async with UnitOfWork() as uow:
        session = uow.session
        if session is None:
            return []
        context = await _conversation_context(session, request, agent_id)
        lineage_chat_ids = await _lineage_chat_ids(session, request)
        if request.lineage != "all" and not lineage_chat_ids:
            return []
        rows = await ConversationRecallLookupRepository.hydrate_visible_rows(
            session,
            chat_message_ids=chat_message_ids,
            current_chat_id=request.current_conversation_id,
            agent_id=context.agent_id,
            current_source=context.source,
            scope=request.scope,
            lineage_chat_ids=lineage_chat_ids,
            since=request.since,
            until=request.until,
        )

    hits: list[ConversationSearchHit] = []
    for candidate in candidates:
        row = rows.get(candidate.conversation_id)
        if row is None:
            continue
        summary = row.summary or candidate.summary
        source_ref = _source_ref(row, score=candidate.score, lineage=None, summary=summary)
        hits.append(
            ConversationSearchHit(
                conversation_id=row.chat_id,
                title=row.title or _metadata_text(candidate.metadata, "title"),
                snippet=_sanitize_snippet(row.snippet),
                summary=summary,
                score=candidate.score,
                source="semantic",
                message_id=row.message_id or candidate.message_id,
                created_at=row.created_at or candidate.created_at,
                updated_at=row.updated_at or candidate.updated_at,
                metadata={
                    **candidate.metadata,
                    "agent_id": row.agent_id or "",
                    "source": row.source,
                },
                source_ref=source_ref,
            )
        )
        if len(hits) >= request.limit:
            break
    return hits


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
    return ConversationRecallContext(chat_id=request.current_conversation_id or "", agent_id=fallback_agent_id, source=None)


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
    score = rank_score * 0.52 + position_score * 0.30 + recency_score * 0.12 + _same_agent_boost(row.agent_id, agent_id)
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


def _merge_hits(
    fts_hits: list[ConversationSearchHit],
    semantic_hits: list[ConversationSearchHit],
    limit: int,
) -> list[ConversationSearchHit]:
    merged: dict[str, ConversationSearchHit] = {}
    for hit in [*fts_hits, *semantic_hits]:
        existing = merged.get(hit.conversation_id)
        if existing is None:
            merged[hit.conversation_id] = hit
            continue
        score = _clamp(max(existing.score, hit.score) + 0.05)
        source = "hybrid" if existing.source != hit.source else existing.source
        merged[hit.conversation_id] = existing.model_copy(
            update={
                "score": score,
                "source": source,
                "summary": existing.summary or hit.summary,
                "snippet": existing.snippet or hit.snippet,
                "message_id": existing.message_id or hit.message_id,
                "source_ref": _copy_source_ref_score(existing.source_ref or hit.source_ref, score),
            }
        )
    return sorted(merged.values(), key=lambda item: item.score, reverse=True)[:limit]


def _same_agent_boost(row_agent_id: str | None, current_agent_id: str | None) -> float:
    if row_agent_id and current_agent_id and row_agent_id == current_agent_id:
        return SAME_AGENT_BOOST
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


def _metadata_text(metadata: dict[str, str | int | float | bool], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _source_ref(
    row: ConversationRecallRow,
    *,
    score: float,
    lineage: str | None,
    summary: str | None = None,
) -> ConversationSourceRef:
    return ConversationSourceRef(
        conversation_id=row.chat_id,
        message_id=row.message_id,
        title=row.title,
        snippet=_sanitize_snippet(row.snippet),
        summary=summary if summary is not None else row.summary,
        score=score,
        agent_id=row.agent_id,
        surface=row.source,
        fork_parent_id=row.fork_parent_id,
        lineage=lineage,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
