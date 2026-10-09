"""Service orchestrating background dream cognitive consolidation and growth diaries.

[POS]
后台梦境认知重组与成长日记单例业务门面服务。
负责连接 Harness 框架层 DreamCognitivePipeline 引擎与 Server 端 REST API，
维护持久化/内存级成长日记索引并支持白盒具身自省视图查询。

[INPUT]
- CognitiveConsolidationRequestDTO: 包含会话碎片与关联 Cube 的请求体

[OUTPUT]
- DreamCognitiveService: 单例门面服务
- 强类型 DTO 响应（CognitiveConsolidationReportDTO, GrowthDiaryEntryDTO 等）
"""

from __future__ import annotations

import threading

# 严格架构门禁：必须从 myrm_agent_harness.toolkits.memory 顶级包导入，严禁 deep import
from myrm_agent_harness.toolkits.memory import (
    CognitiveConsolidationReport,
    DreamCognitiveAction,
    DreamCognitivePipeline,
    DreamSessionFragment,
    GrowthDiaryEntry,
)

from app.schemas.dream_cognitive import (
    CognitiveConsolidationReportDTO,
    CognitiveConsolidationRequestDTO,
    DreamCognitiveActionDTO,
    DreamCognitiveActionTypeEnum,
    DreamCognitiveOverviewDTO,
    DreamMotiveTypeEnum,
    DreamTargetMemoryTypeEnum,
    GrowthDiaryEntryDTO,
    HypotheticalDeductionDTO,
)


def _action_domain_to_dto(action: DreamCognitiveAction) -> DreamCognitiveActionDTO:
    return DreamCognitiveActionDTO(
        action_id=action.action_id,
        action_type=DreamCognitiveActionTypeEnum(action.action_type.value),
        target_type=DreamTargetMemoryTypeEnum(action.target_type.value),
        target_id=action.target_id,
        source_fact_ids=list(action.source_fact_ids),
        payload_statement=action.payload_statement,
        deduction=HypotheticalDeductionDTO(
            hypothetical_query=action.deduction.hypothetical_query,
            improved_response_reasoning=action.deduction.improved_response_reasoning,
            confidence_gain=action.deduction.confidence_gain,
        ),
        confidence=action.confidence,
        cube_id=action.cube_id,
    )


def _diary_domain_to_dto(diary: GrowthDiaryEntry) -> GrowthDiaryEntryDTO:
    return GrowthDiaryEntryDTO(
        diary_id=diary.diary_id,
        title=diary.title,
        summary=diary.summary,
        reflective_narrative=diary.reflective_narrative,
        motive_type=DreamMotiveTypeEnum(diary.motive_type.value),
        themes=list(diary.themes),
        cube_id=diary.cube_id,
        generated_actions=[_action_domain_to_dto(a) for a in diary.generated_actions],
        created_at=diary.created_at,
    )


def _report_domain_to_dto(report: CognitiveConsolidationReport) -> CognitiveConsolidationReportDTO:
    return CognitiveConsolidationReportDTO(
        run_id=report.run_id,
        cube_id=report.cube_id,
        timestamp=report.timestamp,
        duration_ms=report.duration_ms,
        input_fact_count=report.input_fact_count,
        clusters_formed=report.clusters_formed,
        actions_generated=report.actions_generated,
        diary_entries=[_diary_domain_to_dto(d) for d in report.diary_entries],
    )


class DreamCognitiveService:
    """Singleton service facade managing dream cognitive consolidation and diaries."""

    def __init__(self, pipeline: DreamCognitivePipeline | None = None) -> None:
        self._pipeline = pipeline or DreamCognitivePipeline()
        self._lock = threading.RLock()
        self._diaries: dict[str, GrowthDiaryEntry] = {}
        self._latest_run_id: str | None = None

    def consolidate(self, req: CognitiveConsolidationRequestDTO) -> CognitiveConsolidationReportDTO:
        """Execute cognitive consolidation cycle over incoming session fragments."""
        domain_fragments: list[DreamSessionFragment] = []
        for frag in req.fragments:
            mem_dicts: list[dict[str, object]] = []
            for mem in frag.memories:
                ev_list: list[dict[str, object]] = [
                    {
                        "message_id": ev.message_id,
                        "speaker": ev.speaker,
                        "verbatim_quote": ev.verbatim_quote,
                    }
                    for ev in mem.evidence
                ]
                mem_dicts.append(
                    {
                        "id": mem.fact_id,
                        "content": mem.content,
                        "evidence": ev_list,
                    }
                )
            domain_fragments.append(
                DreamSessionFragment(
                    session_id=frag.session_id,
                    project_id=frag.project_id,
                    chat_turn_count=frag.chat_turn_count,
                    memories=mem_dicts,
                )
            )

        report = self._pipeline.consolidate(
            fragments=domain_fragments,
            cube_id=req.cube_id,
            target_project_id=req.target_project_id,
        )

        with self._lock:
            self._latest_run_id = report.run_id
            for entry in report.diary_entries:
                self._diaries[entry.diary_id] = entry

        return _report_domain_to_dto(report)

    def list_diaries(self, cube_id: str | None = None, limit: int = 50) -> list[GrowthDiaryEntryDTO]:
        """List recorded growth diaries optionally filtered by Memory Cube."""
        with self._lock:
            entries = list(self._diaries.values())

        if cube_id is not None:
            entries = [e for e in entries if e.cube_id == cube_id]

        entries.sort(key=lambda e: e.created_at, reverse=True)
        return [_diary_domain_to_dto(e) for e in entries[:limit]]

    def get_diary(self, diary_id: str) -> GrowthDiaryEntryDTO | None:
        """Fetch a specific diary entry by its identifier."""
        with self._lock:
            entry = self._diaries.get(diary_id)
        return _diary_domain_to_dto(entry) if entry else None

    def get_diary_markdown(self, diary_id: str) -> str | None:
        """Fetch the formatted human-readable markdown presentation of a diary entry."""
        with self._lock:
            entry = self._diaries.get(diary_id)
        return entry.format_markdown() if entry else None

    def get_overview(self) -> DreamCognitiveOverviewDTO:
        """Produce high-level summary overview of cognitive dreaming state."""
        with self._lock:
            all_entries = list(self._diaries.values())
            latest_run = self._latest_run_id

        total_actions = sum(len(e.generated_actions) for e in all_entries)
        active_cubes = sorted({e.cube_id for e in all_entries if e.cube_id is not None})

        return DreamCognitiveOverviewDTO(
            total_diaries=len(all_entries),
            total_actions=total_actions,
            active_cubes=active_cubes,
            latest_run_id=latest_run,
        )


_service_instance: DreamCognitiveService | None = None


def get_dream_cognitive_service() -> DreamCognitiveService:
    """Retrieve singleton instance of DreamCognitiveService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = DreamCognitiveService()
    return _service_instance
