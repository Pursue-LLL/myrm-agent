"""Conversation search hits: how a recall row becomes a scored hit.

[INPUT]
myrm_agent_harness.api::RankedList, fuse_rrf_deterministic (POS: deterministic reciprocal-rank fusion of ranked lists)
myrm_agent_harness.toolkits.memory.conversation_search.types::ConversationSearchHit, ConversationSourceRef (POS: conversation search DTOs)
myrm_agent_harness.utils.db.fts5::relevance_from_rank (POS: FTS5 query sanitizing and rank relevance)
app.database.repositories.conversation_recall::ConversationRecallRow (POS: Conversation Recall 索引仓储)
app.services.chat.chat_helpers::_sanitize_snippet, strip_reasoning_tags (POS: 聊天服务辅助层)

[OUTPUT]
fts_hit: A search hit scored from FTS rank, position, agent and chat source.
recent_hit: A recent-list hit scored from its position, agent and chat source.
rank_fts_hits: FTS hits re-scored by deterministic RRF, normalized to [0, 1].
source_interaction_boost: Score adjustment for the surface a chat came from: cron demoted, interactive surfaces boosted.

[POS]
会话召回命中的构造与打分层。把召回行变成带分数与来源引用的搜索命中，只读召回行，不碰数据库。命中携带它所指消息的发送时间，
打分只看相关度、位置、agent 与来源，不看时间。
"""

from __future__ import annotations

from myrm_agent_harness.api import (
    RankedList,
    fuse_rrf_deterministic,
)
from myrm_agent_harness.toolkits.memory.conversation_search.types import (
    ConversationSearchHit,
    ConversationSourceRef,
)
from myrm_agent_harness.utils.db.fts5 import relevance_from_rank

from app.database.repositories.conversation_recall import ConversationRecallRow
from app.services.chat.chat_helpers import _sanitize_snippet, strip_reasoning_tags

_SAME_AGENT_BOOST = 0.06
_DEMOTED_CHAT_SOURCES = frozenset({"cron"})
_INTERACTIVE_CHAT_SOURCES = frozenset({"web", "feishu", "telegram", "wechat", "discord", "slack"})


def fts_hit(
    row: ConversationRecallRow,
    index: int,
    total: int,
    agent_id: str | None,
    *,
    score_weight: float = 1.0,
) -> ConversationSearchHit:
    """A search hit scored from FTS rank, position, agent and chat source.

    The hit carries the time of the message it names but the score ignores it: relevance saturates while age does not,
    so an age term would let a newer weak match outrank an older strong one.
    """
    position_score = 1.0 - (index / max(total, 1)) * 0.35
    rank_score = relevance_from_rank(row.rank)
    score = (
        rank_score * 0.52
        + position_score * 0.30
        + _same_agent_boost(row.agent_id, agent_id)
        + source_interaction_boost(row.source)
    )
    score = _clamp(score * score_weight)
    return ConversationSearchHit(
        conversation_id=row.chat_id,
        title=row.title,
        # The window FTS5 cut. `redact_hit_windows` locates the stored text by it and replaces it, so it never reaches
        # the model as it is.
        snippet=row.window,
        summary=row.summary,
        score=score,
        source="conversation_index",
        message_id=row.message_id,
        created_at=row.created_at,
        updated_at=row.last_message_at,
        metadata={"agent_id": row.agent_id or "", "source": row.source},
        source_ref=_source_ref(row, score=score, lineage=None),
    )


def recent_hit(row: ConversationRecallRow, index: int, agent_id: str | None) -> ConversationSearchHit:
    score = 0.92 - min(index, 10) * 0.035 + _same_agent_boost(row.agent_id, agent_id)
    score += source_interaction_boost(row.source)
    score = _clamp(score)
    return ConversationSearchHit(
        conversation_id=row.chat_id,
        title=row.title,
        snippet=strip_reasoning_tags(row.window),
        summary=row.summary,
        score=score,
        source="recent",
        created_at=row.created_at,
        updated_at=row.last_message_at,
        metadata={"agent_id": row.agent_id or "", "source": row.source},
        source_ref=_source_ref(row, score=score, lineage=None),
    )


def _copy_source_ref_score(source_ref: ConversationSourceRef | None, score: float) -> ConversationSourceRef | None:
    if source_ref is None:
        return None
    return source_ref.model_copy(update={"score": score})


def rank_fts_hits(
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
        return _SAME_AGENT_BOOST
    return 0.0


def source_interaction_boost(chat_source: str | None) -> float:
    normalized = (chat_source or "").strip().lower()
    if normalized in _DEMOTED_CHAT_SOURCES:
        return -0.10
    if normalized in _INTERACTIVE_CHAT_SOURCES:
        return 0.06
    return 0.0


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
        updated_at=row.last_message_at,
    )
