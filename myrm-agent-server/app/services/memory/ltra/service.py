"""Business logic service for Listen-Translate-Remember-Act (LTRA) cognitive pipeline.

[POS]
随身感知“听—译—记—办”业务调度层。协调声纹转录摄入、事实持久化与检索、
原话高亮追问、HTTP 206 毫秒级音频切片代理以及沙箱工单闭环派发。

[INPUT]
- app.schemas.ltra_cognitive DTOs
- myrm_agent_harness.toolkits.memory.ltra 核心引擎

[OUTPUT]
- ListenTranslateRememberActService: 全流程感知认知与派办单例服务
"""

from __future__ import annotations

import threading

from myrm_agent_harness.toolkits.memory import (
    AudioFactDistillationWorker,
    CognitiveFactQuadruple,
    DiarizedTranscriptSegment,
    FollowupTaskDraft,
    FollowupTaskDraftBuilder,
    SpeakerIdentityResolver,
)

from app.schemas.ltra_cognitive import (
    AudioTimestampAnchorDTO,
    CognitiveFactDTO,
    DispatchedTaskResponse,
    FactDistillResponse,
    FollowupQueryResponse,
    IngestAudioTranscriptRequest,
    TaskDispatchPlanRequest,
)


class ListenTranslateRememberActService:
    """Singleton service driving the LTRA pipeline across ingestion, memory, and dispatch."""

    def __init__(self) -> None:
        """Initialize in-memory stores and concurrency lock."""
        self._lock = threading.RLock()
        self._facts: dict[str, CognitiveFactQuadruple] = {}
        self._dispatched_tasks: dict[str, FollowupTaskDraft] = {}
        self._idempotency_cache: dict[str, FollowupTaskDraft] = {}
        self._audio_store: dict[str, bytes] = {}

    def ingest_transcript(self, request: IngestAudioTranscriptRequest) -> FactDistillResponse:
        """Process diarized turns into facts and persist in memory store."""
        resolver = SpeakerIdentityResolver(request.speaker_aliases)
        worker = AudioFactDistillationWorker(identity_resolver=resolver)

        segments = [
            DiarizedTranscriptSegment(
                speaker_id=s.speaker_id,
                text=s.text,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                confidence=s.confidence,
            )
            for s in request.segments
        ]

        facts = worker.distill_facts(
            segments=segments,
            audio_id=request.audio_id,
            project_id=request.project_id,
            target_agent_id=request.target_agent_id,
        )

        with self._lock:
            for fact in facts:
                self._facts[fact.fact_id] = fact

        fact_dtos = [self._to_fact_dto(f) for f in facts]
        return FactDistillResponse(
            status="success",
            audio_id=request.audio_id,
            processed_segments_count=len(segments),
            distilled_facts_count=len(facts),
            facts=fact_dtos,
        )

    def list_facts(
        self,
        project_id: str | None = None,
        target_agent_id: str | None = None,
    ) -> list[CognitiveFactDTO]:
        """List stored facts with optional project or agent filters."""
        with self._lock:
            facts = list(self._facts.values())

        filtered: list[CognitiveFactQuadruple] = []
        for fact in facts:
            if project_id and fact.project_id != project_id:
                continue
            if target_agent_id and fact.target_agent_id != target_agent_id:
                continue
            filtered.append(fact)

        return [self._to_fact_dto(f) for f in filtered]

    def query_and_cite(
        self,
        query: str,
        project_id: str | None = None,
        target_agent_id: str | None = None,
    ) -> FollowupQueryResponse:
        """Search facts matching natural language query and provide citation references."""
        candidates = self.list_facts(project_id=project_id, target_agent_id=target_agent_id)
        tokens = [t.lower() for t in query.split() if len(t) > 1] or [query.lower()]

        matched: list[CognitiveFactDTO] = []
        for dto in candidates:
            searchable_text = f"{dto.subject} {dto.demand} {dto.commitment} {dto.pending_issue}".lower()
            if any(t in searchable_text for t in tokens) or not tokens:
                matched.append(dto)

        suggested_draft: dict[str, str] | None = None
        if matched:
            top_fact = matched[0]
            suggested_draft = {
                "fact_id": top_fact.fact_id,
                "suggested_title": f"落实 {top_fact.subject} 的诉求：{top_fact.demand[:25]}",
                "evidence_quote": top_fact.anchors[0].verbatim_quote if top_fact.anchors else "",
            }

        return FollowupQueryResponse(
            status="success",
            query=query,
            matched_facts_count=len(matched),
            facts=matched,
            suggested_task_draft=suggested_draft,
        )

    def dispatch_task(self, request: TaskDispatchPlanRequest) -> DispatchedTaskResponse:
        """Convert confirmed fact into dispatched sandbox task specification."""
        with self._lock:
            fact = self._facts.get(request.fact_id)
            if not fact:
                raise ValueError(f"Fact with id '{request.fact_id}' not found.")

            # Generate draft blueprint via Harness builder
            draft = FollowupTaskDraftBuilder.build_draft(
                fact=fact,
                target_agent_role=request.target_agent_role,
            )

            # Check idempotency cache to prevent accidental double-clicks
            if draft.idempotency_token in self._idempotency_cache:
                existing = self._idempotency_cache[draft.idempotency_token]
                return self._to_dispatched_response(existing)

            self._dispatched_tasks[draft.task_id] = draft
            self._idempotency_cache[draft.idempotency_token] = draft

        return self._to_dispatched_response(draft)

    def store_audio_bytes(self, audio_id: str, audio_data: bytes) -> None:
        """Store raw audio bytes for slicing and range streaming."""
        with self._lock:
            self._audio_store[audio_id] = audio_data

    def get_audio_clip(
        self,
        audio_id: str,
        start_ms: int,
        end_ms: int,
    ) -> tuple[bytes, int, int, int]:
        """Return audio slice bytes and boundary coordinates for HTTP 206 streaming."""
        with self._lock:
            raw_bytes = self._audio_store.get(audio_id)

        if not raw_bytes:
            # Fallback mock audio header bytes for simulated playback testing
            raw_bytes = b"RIFFmockWAVEfmt " + b"\x00" * 4096

        total_bytes = len(raw_bytes)
        # Approximate byte offsets based on millisecond proportion (assuming 16kHz 16bit mono = 32 bytes/ms)
        bytes_per_ms = 32
        start_byte = max(0, min(start_ms * bytes_per_ms, total_bytes - 1))
        end_byte = max(start_byte + 1, min(end_ms * bytes_per_ms, total_bytes))
        clip_bytes = raw_bytes[start_byte:end_byte]

        return (clip_bytes, start_byte, end_byte - 1, total_bytes)

    def _to_fact_dto(self, fact: CognitiveFactQuadruple) -> CognitiveFactDTO:
        """Convert Harness domain fact to API DTO."""
        anchor_dtos = [
            AudioTimestampAnchorDTO(
                audio_id=a.audio_id,
                start_ms=a.start_ms,
                end_ms=a.end_ms,
                verbatim_quote=a.verbatim_quote,
                sha256_digest=a.sha256_digest,
            )
            for a in fact.anchors
        ]
        return CognitiveFactDTO(
            fact_id=fact.fact_id,
            subject=fact.subject,
            demand=fact.demand,
            commitment=fact.commitment,
            pending_issue=fact.pending_issue,
            anchors=anchor_dtos,
            project_id=fact.project_id,
            target_agent_id=fact.target_agent_id,
            is_confidential=fact.is_confidential,
            created_at_iso=fact.created_at_iso,
        )

    def _to_dispatched_response(self, draft: FollowupTaskDraft) -> DispatchedTaskResponse:
        """Convert task draft into API response."""
        return DispatchedTaskResponse(
            status="dispatched",
            task_id=draft.task_id,
            source_fact_id=draft.source_fact_id,
            title=draft.title,
            target_agent_role=draft.target_agent_role,
            sandbox_deliverable_path=draft.sandbox_deliverable_path,
            action_plan_steps=list(draft.action_plan_steps),
            idempotency_token=draft.idempotency_token,
            created_at_iso=draft.created_at_iso,
        )


_SERVICE_INSTANCE: ListenTranslateRememberActService | None = None
_INSTANCE_LOCK = threading.Lock()


def get_ltra_service() -> ListenTranslateRememberActService:
    """Get or create singleton instance of ListenTranslateRememberActService."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        with _INSTANCE_LOCK:
            if _SERVICE_INSTANCE is None:
                _SERVICE_INSTANCE = ListenTranslateRememberActService()
    return _SERVICE_INSTANCE
