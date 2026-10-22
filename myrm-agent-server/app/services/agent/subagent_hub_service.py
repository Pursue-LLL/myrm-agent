"""
[INPUT]
- myrm_agent_harness.agent.sub_agents.supervision_hub (SubagentSupervisionCoordinator)
- app.schemas.subagent_hub.*

[OUTPUT]
- SubagentHubService

[POS]
Server 业务层子代理实时监管抽屉服务（Topic 12 · 第 18 项）。
聚合 Harness 层的 SubagentSupervisionCoordinator 与 Checkpoint 存储，提供实时花名册聚合、Live Transcript 与 Steer/Kill/Revive 动作调度。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.sub_agents.checkpoint.saver import SubagentCheckpointStorage
from myrm_agent_harness.agent.sub_agents.supervision_hub import (
    SubagentSupervisionCoordinator,
)

from app.schemas.subagent_hub import (
    SubagentRosterOverviewResponseDTO,
    SubagentTranscriptResponseDTO,
    SubagentWorkerRosterItemDTO,
    SubagentWorkerStatusLiteral,
    SupervisionActionLiteral,
    SupervisionActionResponseDTO,
    SupervisionTranscriptEntryDTO,
)

logger = logging.getLogger(__name__)


class SubagentHubService:
    """Service governing subagent live supervision, transcripts, and lifecycle actions."""

    def __init__(
        self,
        coordinator: SubagentSupervisionCoordinator | None = None,
        checkpoint_storage: SubagentCheckpointStorage | None = None,
    ) -> None:
        self._coordinator = coordinator or SubagentSupervisionCoordinator.get_instance()
        self._storage = checkpoint_storage or SubagentCheckpointStorage()

    async def get_roster_overview(self, chat_id: str) -> SubagentRosterOverviewResponseDTO:
        """Fetch aggregated roster overview for chat session, including checkpointed workers."""
        overview = self._coordinator.get_roster_overview(chat_id)
        workers_dto: list[SubagentWorkerRosterItemDTO] = []
        registered_ids = {w.task_id for w in overview.workers}

        for w in overview.workers:
            status_val: SubagentWorkerStatusLiteral = (
                w.status if w.status in ("running", "parked", "stuck", "done", "failed", "interrupted") else "running"
            )
            workers_dto.append(
                SubagentWorkerRosterItemDTO(
                    task_id=w.task_id,
                    agent_type=w.agent_type,
                    status=status_val,
                    current_activity=w.current_activity,
                    model=w.model,
                    tokens_used=w.tokens_used,
                    elapsed_seconds=w.elapsed_seconds,
                    last_tool=w.last_tool,
                    can_steer=w.can_steer,
                    can_kill=w.can_kill,
                    can_revive=w.can_revive,
                    description=w.description,
                    created_at=w.created_at,
                )
            )

        # Merge persisted checkpoints if not in active memory
        try:
            checkpoints = await self._storage.list_checkpoints(session_id=chat_id)
            for cp in checkpoints:
                if cp.task_id not in registered_ids:
                    status_str: SubagentWorkerStatusLiteral = "interrupted" if cp.interruption_reason else "parked"
                    workers_dto.append(
                        SubagentWorkerRosterItemDTO(
                            task_id=cp.task_id,
                            agent_type=cp.agent_type,
                            status=status_str,
                            current_activity=(
                                f"Interrupted: {cp.interruption_reason}" if cp.interruption_reason else "Parked in checkpoint"
                            ),
                            model="default",
                            tokens_used=0,
                            elapsed_seconds=0.0,
                            last_tool=cp.last_tool or "",
                            can_steer=False,
                            can_kill=False,
                            can_revive=True,
                            description=cp.task_description or "",
                            created_at=cp.timestamp,
                        )
                    )
                    registered_ids.add(cp.task_id)
        except Exception:
            logger.exception("Failed to hydrate checkpoints into supervision roster: %s", chat_id)

        active_cnt = sum(1 for w in workers_dto if w.status == "running")
        parked_cnt = sum(1 for w in workers_dto if w.status in ("parked", "interrupted"))
        stuck_cnt = sum(1 for w in workers_dto if w.status == "stuck")
        total_toks = sum(w.tokens_used for w in workers_dto)
        max_duration = max((w.elapsed_seconds for w in workers_dto), default=0.0)

        return SubagentRosterOverviewResponseDTO(
            session_id=chat_id,
            total_workers=len(workers_dto),
            active_workers=active_cnt,
            parked_workers=parked_cnt,
            stuck_workers=stuck_cnt,
            total_tokens=total_toks,
            total_duration_seconds=round(max_duration, 2),
            workers=workers_dto,
        )

    def get_transcript(self, chat_id: str, task_id: str, limit: int | None = None) -> SubagentTranscriptResponseDTO:
        """Fetch execution transcript entries for a given worker."""
        raw_entries = self._coordinator.get_transcript_entries(task_id, limit=limit)
        dto_entries: list[SupervisionTranscriptEntryDTO] = []

        for e in raw_entries:
            lvl = e.get("level")
            lvl_val = "error" if lvl == "error" else "warn" if lvl == "warn" else "info"
            dur = e.get("duration_ms")
            dur_int = int(dur) if isinstance(dur, (int, float)) else None

            dto_entries.append(
                SupervisionTranscriptEntryDTO(
                    entry_id=str(e.get("entry_id", "")),
                    timestamp=str(e.get("timestamp", "")),
                    tool_name=str(e.get("tool_name", "")),
                    input_summary=str(e.get("input_summary", "")),
                    output_summary=str(e.get("output_summary", "")),
                    level=lvl_val,
                    duration_ms=dur_int,
                )
            )

        return SubagentTranscriptResponseDTO(
            task_id=task_id,
            total_entries=len(dto_entries),
            entries=dto_entries,
        )

    def execute_action(
        self,
        chat_id: str,
        task_id: str,
        action: SupervisionActionLiteral,
        message: str = "",
    ) -> SupervisionActionResponseDTO:
        """Dispatch steer, kill, or revive action on a subagent worker."""
        result = self._coordinator.execute_action(
            task_id=task_id,
            action=action,
            steering_message=message,
        )
        new_stat: SubagentWorkerStatusLiteral = (
            result.new_status
            if result.new_status in ("running", "parked", "stuck", "done", "failed", "interrupted")
            else "failed"
        )

        return SupervisionActionResponseDTO(
            task_id=result.task_id,
            action=action,
            success=result.success,
            message=result.message,
            new_status=new_stat,
        )
