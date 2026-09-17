"""Guardian maintenance sub-tasks (conflict auto-resolve, archive purge).

[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager
- app.database.models::PendingMemory
- app.core.memory.adapters.setup::create_memory_manager (POS: 业务层记忆管理器工厂)

[OUTPUT]
- create_guardian_memory_manager: guardian 上下文 MemoryManager 工厂
- auto_resolve_expired_conflicts: keep_old resolve for expired low-risk conflicts
- purge_expired_archives: delegate archived-memory retention reclamation to the harness
- harvest_session_blind_spots: harvest missed queries & negative signals into knowledge patch approvals
- sync_external_harness_transcripts: 增量扫描并同步外部 Agent 会话记录到会话召回索引

[POS]
Guardian 维护子任务与工厂。纯数据/对象操作，不依赖调度状态，
由 memory_guardian 调度器与 pattern_discovery_trigger 在维护周期内调用。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.toolkits.memory import MemoryManager

logger = logging.getLogger(__name__)


async def create_guardian_memory_manager() -> MemoryManager:
    """Create a MemoryManager for background maintenance (no user session context)."""
    from app.core.memory.adapters.setup import (
        create_memory_manager,
        resolve_context_binding,
    )
    from app.services.agent.platform_config import (
        load_platform_evolution_llm,
        require_platform_embedding_config,
    )

    binding = resolve_context_binding(
        namespaces=None,
        agent_id=None,
        channel_id=None,
        conversation_id=None,
        task_id=None,
    )
    embedding_cfg = await require_platform_embedding_config()

    consolidation_llm = None
    try:
        consolidation_llm = await load_platform_evolution_llm()
    except Exception as exc:
        logger.debug("Memory guardian: evolution LLM not available for consolidation: %s", exc)

    return await create_memory_manager(
        binding,
        embedding_cfg,
        approval_required=False,
        consolidation_llm=consolidation_llm,
    )


async def auto_resolve_expired_conflicts() -> int:
    """Resolve conflicts whose auto_resolve_at deadline has passed.

    Applies KEEP_OLD (safe default): the old memory stays, the conflicting
    new content is discarded. Returns the number of resolved conflicts.

    Conflicts whose ``conflict_auto_resolve_at`` is None (high-risk conflicts
    created with importance >= 0.9) never match the ``isnot(None)`` filter and
    are therefore never auto-resolved — they require explicit user action.
    """
    from sqlalchemy import func, update

    from app.database.connection import get_session
    from app.database.models import PendingMemory

    now = datetime.now(UTC)

    async with get_session() as db:
        stmt = (
            update(PendingMemory)
            .where(
                PendingMemory.is_conflict.is_(True),
                PendingMemory.status == "pending",
                PendingMemory.conflict_auto_resolve_at.isnot(None),
                PendingMemory.conflict_auto_resolve_at <= now,
            )
            .values(
                status="resolved",
                resolved_at=now,
                metadata_json=func.json_set(
                    PendingMemory.metadata_json,
                    "$.resolution",
                    "keep_old",
                    "$.auto_resolved",
                    True,
                ),
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount  # type: ignore[return-value]


async def purge_expired_archives(manager: MemoryManager) -> int:
    """Reclaim archived memories and rules whose retention window has elapsed.

    Delegates to the harness TTL retention purge, which scans the archived
    payload flag and falls back to ``archived_at`` for entries stamped before
    every archival path wrote an expiration.
    """
    purged_memories = await manager.purge_expired_archived_memories()
    purged_rules = await manager.purge_expired_archived_rules()
    return purged_memories + purged_rules


async def harvest_session_blind_spots(
    *,
    limit: int = 50,
    since_hours: int = 168,
    min_candidates: int = 1,
) -> int:
    """Harvest missed queries from recent session messages and extract knowledge patches.

    1. Scans recent messages with missed_query / user_correction / negative feedback.
    2. Runs extract_blind_spot_patches via WebUI default platform LLM.
    3. Persists patches as pending ApprovalRecord (action_type="knowledge_patch") for HITL review.
    Returns the count of created approval records.
    """
    from datetime import timedelta

    from myrm_agent_harness.toolkits.memory.strategies.blind_spot import (
        BlindSpotCandidate,
        extract_blind_spot_patches,
    )
    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models.approval import ApprovalRecord
    from app.database.models.chat import Message
    from app.services.approvals.registry import ApprovalRegistry

    cutoff = datetime.now(UTC) - timedelta(hours=since_hours)
    candidates: list[BlindSpotCandidate] = []

    async with get_session() as db:
        stmt = (
            select(Message)
            .where(
                Message.created_at >= cutoff,
                Message.extra_data.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .limit(limit * 2)
        )
        result = await db.execute(stmt)
        messages = list(result.scalars().all())

    for msg in messages:
        extra = msg.extra_data or {}
        if not isinstance(extra, dict):
            continue

        missed = extra.get("missed_query")
        correction = extra.get("user_correction")
        is_candidate = extra.get("blind_spot_candidate") is True
        is_thumbs_down = bool(
            extra.get("thumbs_down") or extra.get("reaction") == "thumbsdown" or extra.get("rating") == "negative"
        )

        query_text = ""
        if isinstance(missed, str) and missed.strip():
            query_text = missed.strip()
        elif is_candidate or is_thumbs_down or correction:
            if msg.role == "user" and msg.content and msg.content.strip():
                query_text = msg.content.strip()

        if query_text:
            candidates.append(
                BlindSpotCandidate(
                    query=query_text,
                    session_id=str(msg.chat_id or ""),
                    turn_index=0,
                    user_correction=str(correction).strip() if correction else None,
                    thumbs_down=is_thumbs_down,
                    created_at_iso=msg.created_at.isoformat() if msg.created_at else "",
                )
            )

    if not candidates:
        return 0

    try:
        from app.services.agent.platform_config import load_platform_evolution_llm

        llm = await load_platform_evolution_llm(streaming=False, temperature=0.0)
    except Exception as exc:
        logger.info(
            "Memory guardian: evolution LLM not configured for blind spot harvesting: %s",
            exc,
        )
        return 0

    report = await extract_blind_spot_patches(candidates, llm, min_candidates=min_candidates)
    if report.skipped or not report.has_patches:
        return 0

    created_count = 0
    async with get_session() as db:
        stmt_existing = select(ApprovalRecord.payload).where(
            ApprovalRecord.action_type == "knowledge_patch",
            ApprovalRecord.status == "PENDING",
        )
        res = await db.execute(stmt_existing)
        existing_payloads = [r[0] for r in res.all() if isinstance(r[0], dict)]
        existing_titles = {str(p.get("title", "")).strip().lower() for p in existing_payloads if p.get("title")}

    for patch in report.patches:
        if patch.title.strip().lower() in existing_titles:
            continue
        await ApprovalRegistry.create_approval(
            agent_id="default",
            action_type="knowledge_patch",
            reason=f"会话盲点知识转正建议: {patch.title}",
            severity="info",
            payload={
                "title": patch.title,
                "target_type": patch.target_type.value,
                "content": patch.content,
                "trigger_condition": patch.trigger_condition,
                "rationale": patch.rationale,
                "confidence": patch.confidence,
                "source_queries": patch.source_queries,
                "suggested_action": patch.suggested_action,
            },
        )
        existing_titles.add(patch.title.strip().lower())
        created_count += 1

    logger.info(
        "Memory guardian: harvested %d knowledge patch approvals from %d candidates",
        created_count,
        len(candidates),
    )
    return created_count


async def sync_external_harness_transcripts(
    directory_path: str | Path | None = None,
    *,
    source: str = "external:claude_code",
) -> int:
    """Incrementally scan and index external transcripts into conversation recall.

    Returns the number of newly indexed turns.
    """
    import os
    from pathlib import Path

    from app.database.connection import get_session
    from app.services.memory.imports.external_transcript_sync import (
        ExternalTranscriptSyncService,
    )

    if directory_path is None:
        env_dir = os.getenv("EXTERNAL_TRANSCRIPT_DIR")
        if env_dir:
            directory_path = Path(env_dir)
        else:
            default_claude_dir = Path.home() / ".claude" / "projects"
            if default_claude_dir.is_dir():
                directory_path = default_claude_dir
            else:
                return 0

    dir_p = Path(directory_path).expanduser()
    if not dir_p.is_dir():
        return 0

    service = ExternalTranscriptSyncService()
    async with get_session() as db:
        res = await service.sync_directory(db, dir_p, source=source)
        await db.commit()
        if res.new_turns > 0:
            logger.info(
                "Memory guardian external transcript sync: %d new turns indexed across %d files",
                res.new_turns,
                res.synced_files,
            )
        return res.new_turns
