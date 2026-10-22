"""Service layer for Persistent Kanban Job Queue and Massive Parallel Dogfooding Runner."""

from typing import Dict, List, Optional

from myrm_agent_harness.agent.sub_agents.kanban_queue import (
    BatchRunnerConfig,
    JobPriority,
    KanbanJob,
    KanbanJobStatus,
    MassiveParallelBatchRunner,
    PersistentKanbanQueueManager,
    SwarmTopologyStage,
)

from app.schemas.kanban_queue import (
    BatchRunnerStatusDTO,
    BlackboardEntryDTO,
    CreateKanbanJobRequest,
    DispatchWaveResponseDTO,
    JobPriorityEnum,
    KanbanCommentDTO,
    KanbanJobDTO,
    KanbanJobStatusEnum,
    SpecifyPromptResponse,
    SwarmTopologyStageEnum,
)


class PersistentKanbanQueueService:
    """Session-isolated service managing kanban queues, swarm blackboard, and batch runner."""

    def __init__(self) -> None:
        self._sessions: Dict[str, tuple[PersistentKanbanQueueManager, MassiveParallelBatchRunner]] = {}

    def _get_bundle(self, chat_id: str) -> tuple[PersistentKanbanQueueManager, MassiveParallelBatchRunner]:
        if chat_id not in self._sessions:
            mgr = PersistentKanbanQueueManager(stale_timeout_seconds=14400.0)
            runner = MassiveParallelBatchRunner(mgr, config=BatchRunnerConfig(max_parallel=12))
            self._sessions[chat_id] = (mgr, runner)
        return self._sessions[chat_id]

    def _to_job_dto(self, job: KanbanJob) -> KanbanJobDTO:
        comments_dto = [
            KanbanCommentDTO(
                author=c.author,
                content=c.content,
                timestamp=c.timestamp,
                is_blackboard=c.is_blackboard,
            )
            for c in job.comments
        ]
        return KanbanJobDTO(
            job_id=job.job_id,
            title=job.title,
            goal=job.goal,
            approach=job.approach,
            acceptance_criteria=list(job.acceptance_criteria),
            status=KanbanJobStatusEnum(job.status.value),
            priority=JobPriorityEnum(job.priority.value),
            stage=SwarmTopologyStageEnum(job.stage.value),
            assignee=job.assignee,
            dependencies=list(job.dependencies),
            blocked_reason=job.blocked_reason,
            worktree_path=job.worktree_path,
            skills=list(job.skills),
            comments=comments_dto,
            result_summary=job.result_summary,
            result_metadata=dict(job.result_metadata),
            failure_count=job.failure_count,
            goal_mode=job.goal_mode,
            goal_max_turns=job.goal_max_turns,
            last_heartbeat_timestamp=job.last_heartbeat_timestamp,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    def create_job(self, chat_id: str, req: CreateKanbanJobRequest) -> KanbanJobDTO:
        mgr, _ = self._get_bundle(chat_id)
        job = mgr.kanban_create(
            title=req.title,
            goal=req.goal,
            approach=req.approach,
            acceptance_criteria=req.acceptance_criteria,
            priority=JobPriority(req.priority.value),
            stage=SwarmTopologyStage(req.stage.value),
            assignee=req.assignee,
            dependencies=req.dependencies,
            skills=req.skills,
            goal_mode=req.goal_mode,
            goal_max_turns=req.goal_max_turns,
        )
        return self._to_job_dto(job)

    def list_jobs(
        self,
        chat_id: str,
        status: Optional[KanbanJobStatusEnum] = None,
        stage: Optional[SwarmTopologyStageEnum] = None,
        assignee: Optional[str] = None,
    ) -> List[KanbanJobDTO]:
        mgr, _ = self._get_bundle(chat_id)
        status_val = KanbanJobStatus(status.value) if status else None
        stage_val = SwarmTopologyStage(stage.value) if stage else None
        jobs = mgr.kanban_list(status=status_val, stage=stage_val, assignee=assignee)
        return [self._to_job_dto(j) for j in jobs]

    def get_job(self, chat_id: str, job_id: str) -> Optional[KanbanJobDTO]:
        mgr, _ = self._get_bundle(chat_id)
        job = mgr.kanban_show(job_id)
        return self._to_job_dto(job) if job else None

    def claim_job(self, chat_id: str, job_id: str, assignee: str) -> KanbanJobDTO:
        mgr, _ = self._get_bundle(chat_id)
        job = mgr.kanban_claim_or_run(job_id, assignee)
        return self._to_job_dto(job)

    def complete_job(
        self, chat_id: str, job_id: str, summary: str, metadata: Dict[str, str]
    ) -> KanbanJobDTO:
        mgr, _ = self._get_bundle(chat_id)
        job = mgr.kanban_complete(job_id, summary=summary, metadata=metadata)
        return self._to_job_dto(job)

    def block_job(self, chat_id: str, job_id: str, reason: str) -> KanbanJobDTO:
        mgr, _ = self._get_bundle(chat_id)
        job = mgr.kanban_block(job_id, reason=reason)
        return self._to_job_dto(job)

    def unblock_job(self, chat_id: str, job_id: str) -> KanbanJobDTO:
        mgr, _ = self._get_bundle(chat_id)
        job = mgr.kanban_unblock(job_id)
        return self._to_job_dto(job)

    def heartbeat_job(self, chat_id: str, job_id: str) -> bool:
        mgr, _ = self._get_bundle(chat_id)
        return mgr.kanban_heartbeat(job_id)

    def add_comment(self, chat_id: str, job_id: str, author: str, content: str) -> KanbanCommentDTO:
        mgr, _ = self._get_bundle(chat_id)
        comment = mgr.kanban_comment(job_id, author=author, content=content)
        return KanbanCommentDTO(
            author=comment.author,
            content=comment.content,
            timestamp=comment.timestamp,
            is_blackboard=comment.is_blackboard,
        )

    def link_dependency(self, chat_id: str, from_job_id: str, to_job_id: str) -> bool:
        mgr, _ = self._get_bundle(chat_id)
        return mgr.kanban_link(from_job_id, to_job_id)

    def specify_prompt(self, chat_id: str, prompt: str) -> SpecifyPromptResponse:
        mgr, _ = self._get_bundle(chat_id)
        res = mgr.kanban_specify(prompt)
        crit = res.get("acceptance_criteria", [])
        return SpecifyPromptResponse(
            title=str(res.get("title", "")),
            goal=str(res.get("goal", "")),
            approach=str(res.get("approach", "")),
            acceptance_criteria=[str(c) for c in crit] if isinstance(crit, list) else [],
        )

    def decompose_job(
        self, chat_id: str, parent_job_id: str, subtasks: List[Dict[str, str]]
    ) -> List[KanbanJobDTO]:
        mgr, _ = self._get_bundle(chat_id)
        jobs = mgr.kanban_decompose(parent_job_id, subtasks)
        return [self._to_job_dto(j) for j in jobs]

    def toggle_circuit_breaker(self, chat_id: str, enabled: bool) -> bool:
        mgr, _ = self._get_bundle(chat_id)
        mgr.set_auto_decompose_enabled(enabled)
        return mgr.is_auto_decompose_enabled()

    def reclaim_stale_workers(self, chat_id: str) -> List[str]:
        mgr, _ = self._get_bundle(chat_id)
        return mgr.reclaim_stale_workers()

    def get_blackboard(
        self, chat_id: str, stage: Optional[SwarmTopologyStageEnum] = None
    ) -> List[BlackboardEntryDTO]:
        mgr, _ = self._get_bundle(chat_id)
        stage_val = SwarmTopologyStage(stage.value) if stage else None
        entries = mgr.get_blackboard_entries(stage_val)
        return [
            BlackboardEntryDTO(
                entry_id=e.entry_id,
                job_id=e.job_id,
                stage=SwarmTopologyStageEnum(e.stage.value),
                author=e.author,
                payload=dict(e.payload),
                created_at=e.created_at,
            )
            for e in entries
        ]

    def dispatch_wave(
        self, chat_id: str, max_parallel: int = 12, strategy: str = "round_robin"
    ) -> DispatchWaveResponseDTO:
        _, runner = self._get_bundle(chat_id)
        runner.config.max_parallel = max_parallel
        runner.config.distribution_strategy = strategy
        stats = runner.dispatch_parallel_wave()
        return DispatchWaveResponseDTO(
            dispatched=stats.get("dispatched", 0),
            running=stats.get("running", 0),
            completed=stats.get("completed", 0),
            active_workers=stats.get("active_workers", 0),
        )

    def get_batch_status(self, chat_id: str) -> BatchRunnerStatusDTO:
        _, runner = self._get_bundle(chat_id)
        st = runner.get_checkpoint_status()
        return BatchRunnerStatusDTO(
            total_jobs=int(st["total_jobs"]),
            done_jobs=int(st["done_jobs"]),
            ready_jobs=int(st["ready_jobs"]),
            running_jobs=int(st["running_jobs"]),
            blocked_jobs=int(st["blocked_jobs"]),
            resume_available=bool(st["resume_available"]),
            trajectories_collected=int(st["trajectories_collected"]),
        )

    def export_trajectories(self, chat_id: str) -> str:
        _, runner = self._get_bundle(chat_id)
        return runner.export_trajectories_jsonl()

    def reset_session(self, chat_id: str) -> None:
        if chat_id in self._sessions:
            del self._sessions[chat_id]


_singleton_kanban_queue_service = PersistentKanbanQueueService()


def get_kanban_queue_service() -> PersistentKanbanQueueService:
    """Return the global singleton instance of PersistentKanbanQueueService."""
    return _singleton_kanban_queue_service
