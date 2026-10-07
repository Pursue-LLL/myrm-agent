# [POS]: app/services/memory/conversation_lineage_defense_service.py
# [INPUT]: Harness lineage defense engine, Server schemas
# [OUTPUT]: Domain service managing lineage dedup, automation demotion, and hydration stats

from __future__ import annotations

from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory import (
    ConversationSourceKind,
    LineageNode,
    SourceDemotionPolicy,
    run_lineage_defense_pipeline,
)

from app.schemas.conversation_lineage_defense import (
    CandidateSessionDTO,
    HydratedHitDTO,
    LineageDedupAuditReportDTO,
    LineageDefenseSearchRequestDTO,
    LineageDefenseSearchResponseDTO,
    LineageDefenseStatsDTO,
)


def _to_harness_node(dto: CandidateSessionDTO) -> LineageNode:
    source_kind_map: dict[str, ConversationSourceKind] = {
        "interactive": ConversationSourceKind.INTERACTIVE,
        "cron": ConversationSourceKind.CRON_SCHEDULED,
        "internal_worker": ConversationSourceKind.INTERNAL_WORKER,
    }
    return LineageNode(
        session_id=dto.session_id,
        lineage_root_id=dto.lineage_root_id,
        parent_id=dto.parent_id,
        generation=dto.generation,
        source_kind=source_kind_map.get(dto.source_kind, ConversationSourceKind.INTERACTIVE),
        title=dto.title,
        raw_score=dto.raw_score,
        messages_context=dto.messages_context,
        updated_at=dto.updated_at,
    )


def _build_default_candidates() -> list[CandidateSessionDTO]:
    now = datetime.now(UTC)
    return [
        CandidateSessionDTO(
            session_id="cron_hourly_db_vacuum",
            lineage_root_id="cron_hourly_db_vacuum",
            generation=1,
            source_kind="cron",
            title="Scheduled Database Vacuum & Health Check",
            raw_score=0.94,
            messages_context=[
                "SYSTEM: Scheduled cron trigger at 04:00.",
                "VACUUM: Processed 128 SQLite memory tables without error.",
                "METRICS: Latency 1.2ms, zero lock contention recorded.",
            ],
            updated_at=now,
        ),
        CandidateSessionDTO(
            session_id="chat_auth_refactor_v1",
            lineage_root_id="root_auth_refactor",
            generation=1,
            source_kind="interactive",
            title="Authentication & Session Token Architecture Discussion",
            raw_score=0.86,
            messages_context=[
                "USER: How should we structure the Bearer token validation middleware?",
                "AGENT: We should enforce strict HMAC verification and 24-hour expiration.",
            ],
            updated_at=now,
        ),
        CandidateSessionDTO(
            session_id="chat_auth_refactor_v2",
            lineage_root_id="root_auth_refactor",
            generation=2,
            parent_id="chat_auth_refactor_v1",
            source_kind="interactive",
            title="Authentication Middleware Implementation Compaction v2",
            raw_score=0.89,
            messages_context=[
                "SUMMARY: Previous round decided on 24h HMAC tokens.",
                "USER: Let's write the FastAPI dependency and unit tests.",
                "AGENT: Dependency get_current_user implemented with full 401 handling.",
            ],
            updated_at=now,
        ),
        CandidateSessionDTO(
            session_id="worker_scrape_docs_temp",
            lineage_root_id="worker_scrape_docs",
            generation=1,
            source_kind="internal_worker",
            title="Internal worker temporary documentation scrape",
            raw_score=0.96,
            messages_context=[
                "WORKER: Fetching raw markdown docs from repository...",
                "WORKER: Parsing completed, cache flushed.",
            ],
            updated_at=now,
        ),
    ]


class ConversationLineageDefenseService:
    """Service facade for lineage deduplication and automation demotion."""

    def search_with_defense(
        self, payload: LineageDefenseSearchRequestDTO
    ) -> LineageDefenseSearchResponseDTO:
        candidates = payload.candidates if payload.candidates else _build_default_candidates()
        harness_nodes = [_to_harness_node(c) for c in candidates]

        policy = SourceDemotionPolicy(
            cron_weight_multiplier=payload.cron_weight_multiplier,
            hide_internal_workers=not payload.include_internal,
        )

        hits, audit = run_lineage_defense_pipeline(
            harness_nodes,
            policy=policy,
            include_internal=payload.include_internal,
            window_size=payload.window_size,
            max_hits=payload.limit,
        )

        dto_hits: list[HydratedHitDTO] = [
            HydratedHitDTO(
                session_id=h.session_id,
                lineage_root_id=h.lineage_root_id,
                title=h.title,
                source_kind=h.source_kind.value,  # type: ignore[arg-type]
                detail_level=h.detail_level.value,  # type: ignore[arg-type]
                content_snippet=h.content_snippet,
                window_messages=h.window_messages,
                token_estimate=h.token_estimate,
                is_demoted=h.is_demoted,
                is_lineage_primary=h.is_lineage_primary,
                collapsed_generations_count=h.collapsed_generations_count,
                collapsed_session_ids=h.collapsed_session_ids,
            )
            for h in hits
        ]

        dto_audit = LineageDedupAuditReportDTO(
            total_candidates=audit.total_candidates,
            retained_hits_count=audit.retained_hits_count,
            hidden_internal_count=audit.hidden_internal_count,
            demoted_cron_count=audit.demoted_cron_count,
            collapsed_lineage_count=audit.collapsed_lineage_count,
            interactive_top1_ratio=audit.interactive_top1_ratio,
            estimated_tokens_saved=audit.estimated_tokens_saved,
            token_saving_percent=audit.token_saving_percent,
        )

        return LineageDefenseSearchResponseDTO(
            query=payload.query,
            hits=dto_hits,
            audit_report=dto_audit,
        )

    def get_stats(self) -> LineageDefenseStatsDTO:
        candidates = _build_default_candidates()
        harness_nodes = [_to_harness_node(c) for c in candidates]
        _hits, audit = run_lineage_defense_pipeline(harness_nodes)

        return LineageDefenseStatsDTO(
            total_inspected_sessions=len(candidates),
            interactive_sessions_count=sum(1 for c in candidates if c.source_kind == "interactive"),
            cron_sessions_count=sum(1 for c in candidates if c.source_kind == "cron"),
            internal_workers_count=sum(1 for c in candidates if c.source_kind == "internal_worker"),
            average_token_savings_percent=audit.token_saving_percent,
            recall_blindness_defense_active=True,
        )


_service_instance: ConversationLineageDefenseService | None = None


def get_conversation_lineage_defense_service() -> ConversationLineageDefenseService:
    global _service_instance
    if _service_instance is None:
        _service_instance = ConversationLineageDefenseService()
    return _service_instance
