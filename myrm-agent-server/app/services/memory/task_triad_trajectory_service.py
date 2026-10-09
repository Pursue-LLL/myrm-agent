"""Service managing task triad trajectory blackbox records and anti-loop guards.

[INPUT]
- Internal: schemas.task_triad_trajectory
- External: myrm_agent_harness.toolkits.memory.triad_trajectory, pathlib

[OUTPUT]
- TaskTriadTrajectoryService: Singleton coordinating task milestones, dead-ends, and user steerings.
- get_task_triad_trajectory_service(): Singleton provider.

[POS]
Server service layer for GPT-6 Astra-inspired long-horizon task triad memory.
"""

from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    AntiLoopPromptInjector,
    TaskTriadTrajectoryManager,
    TrajectoryTaskStatus,
)

from app.schemas.task_triad_trajectory import (
    AntiLoopSnapshotResponseDTO,
    CheckActionRequestDTO,
    CheckActionResponseDTO,
    FailedAttemptItemDTO,
    MilestoneItemDTO,
    RecordFailedAttemptRequestDTO,
    RecordMilestoneRequestDTO,
    RecordUserSteeringRequestDTO,
    TaskTrajectoryBlackboxResponseDTO,
    UserSteeringItemDTO,
)


class TaskTriadTrajectoryService:
    """Business service managing task trajectory ledgers, dead-end validation, and snapshots."""

    def __init__(self, persistence_dir: Path | str | None = None) -> None:
        p_dir = Path(persistence_dir) if persistence_dir else Path("data/memory/triad_trajectory")
        self.manager = TaskTriadTrajectoryManager(persistence_dir=p_dir)

    def record_milestone(self, req: RecordMilestoneRequestDTO) -> MilestoneItemDTO:
        """Record verified milestone into task ledger."""
        ledger = self.manager.get_or_create_ledger(
            task_id=req.task_id,
            session_id=req.session_id,
            initial_goal=req.initial_goal,
        )
        milestone = ledger.record_milestone(
            step_index=req.step_index,
            title=req.title,
            verified_output_summary=req.verified_output_summary,
            description=req.description,
            artifacts=req.artifacts_produced,
        )
        self.manager.export_trajectory(req.task_id)
        return MilestoneItemDTO(
            milestone_id=milestone.milestone_id,
            step_index=milestone.step_index,
            title=milestone.title,
            description=milestone.description,
            verified_output_summary=milestone.verified_output_summary,
            artifacts_produced=milestone.artifacts_produced,
            timestamp=milestone.timestamp,
        )

    def record_failed_attempt(self, req: RecordFailedAttemptRequestDTO) -> FailedAttemptItemDTO:
        """Record a dead-end attempt and establish an anti-loop rule."""
        ledger = self.manager.get_or_create_ledger(
            task_id=req.task_id,
            session_id=req.session_id,
            initial_goal=req.initial_goal,
        )
        attempt = ledger.record_failed_attempt(
            step_index=req.step_index,
            action_attempted=req.action_attempted,
            error_type=req.error_type,
            error_summary=req.error_summary,
            dead_end_pattern=req.dead_end_pattern,
            prohibited_rule=req.prohibited_rule,
            lessons_learned=req.lessons_learned,
        )
        self.manager.export_trajectory(req.task_id)
        return FailedAttemptItemDTO(
            attempt_id=attempt.attempt_id,
            step_index=attempt.step_index,
            action_attempted=attempt.action_attempted,
            error_type=attempt.error_type,
            error_summary=attempt.error_summary,
            dead_end_pattern=attempt.dead_end_pattern,
            prohibited_rule=attempt.prohibited_rule,
            lessons_learned=attempt.lessons_learned,
            timestamp=attempt.timestamp,
        )

    def record_user_steering(self, req: RecordUserSteeringRequestDTO) -> UserSteeringItemDTO:
        """Capture in-flight user constraint instruction."""
        ledger = self.manager.get_or_create_ledger(
            task_id=req.task_id,
            session_id=req.session_id,
            initial_goal=req.initial_goal,
        )
        steering = ledger.record_user_steering(
            turn_index=req.turn_index,
            instruction_raw=req.instruction_raw,
            distilled_constraint=req.distilled_constraint,
            scope=req.scope,
        )
        self.manager.export_trajectory(req.task_id)
        return UserSteeringItemDTO(
            steering_id=steering.steering_id,
            turn_index=steering.turn_index,
            instruction_raw=steering.instruction_raw,
            distilled_constraint=steering.distilled_constraint,
            scope=steering.scope,
            is_active=steering.is_active,
            timestamp=steering.timestamp,
        )

    def check_action(self, req: CheckActionRequestDTO) -> CheckActionResponseDTO:
        """Check whether intended action triggers known dead-end path."""
        prohibited, attempt = self.manager.check_action_prohibited(req.task_id, req.action_text)
        if prohibited and attempt:
            return CheckActionResponseDTO(
                is_prohibited=True,
                matched_rule=attempt.prohibited_rule,
                error_summary=attempt.error_summary,
                matched_pattern=attempt.dead_end_pattern,
            )
        return CheckActionResponseDTO(
            is_prohibited=False,
            matched_rule=None,
            error_summary=None,
            matched_pattern=None,
        )

    def get_anti_loop_snapshot(
        self,
        task_id: str,
        step_hint: str = "",
        max_tokens: int = 150,
    ) -> AntiLoopSnapshotResponseDTO | None:
        """Synthesize pre-prompt anti-loop snapshot for the task."""
        ledger = self.manager.get_ledger(task_id)
        if not ledger:
            return None
        snapshot = AntiLoopPromptInjector.build_snapshot(ledger, step_hint=step_hint, max_tokens=max_tokens)
        return AntiLoopSnapshotResponseDTO(
            task_id=snapshot.task_id,
            snapshot_token_estimate=snapshot.snapshot_token_estimate,
            dead_end_rules_injected=snapshot.dead_end_rules_injected,
            active_user_steerings_injected=snapshot.active_user_steerings_injected,
            latest_milestone_title=snapshot.latest_milestone_title,
            formatted_prompt_block=snapshot.formatted_prompt_block,
        )

    def get_blackbox_trajectory(self, task_id: str) -> TaskTrajectoryBlackboxResponseDTO | None:
        """Retrieve full trajectory blackbox state."""
        ledger = self.manager.get_ledger(task_id)
        if not ledger:
            return None
        traj = ledger.get_trajectory()
        return TaskTrajectoryBlackboxResponseDTO(
            task_id=traj.task_id,
            session_id=traj.session_id,
            initial_goal=traj.initial_goal,
            status=traj.status.value if isinstance(traj.status, TrajectoryTaskStatus) else str(traj.status),
            version=traj.version,
            milestones=[
                MilestoneItemDTO(
                    milestone_id=m.milestone_id,
                    step_index=m.step_index,
                    title=m.title,
                    description=m.description,
                    verified_output_summary=m.verified_output_summary,
                    artifacts_produced=m.artifacts_produced,
                    timestamp=m.timestamp,
                )
                for m in traj.milestones
            ],
            failed_attempts=[
                FailedAttemptItemDTO(
                    attempt_id=f.attempt_id,
                    step_index=f.step_index,
                    action_attempted=f.action_attempted,
                    error_type=f.error_type,
                    error_summary=f.error_summary,
                    dead_end_pattern=f.dead_end_pattern,
                    prohibited_rule=f.prohibited_rule,
                    lessons_learned=f.lessons_learned,
                    timestamp=f.timestamp,
                )
                for f in traj.failed_attempts
            ],
            user_steerings=[
                UserSteeringItemDTO(
                    steering_id=s.steering_id,
                    turn_index=s.turn_index,
                    instruction_raw=s.instruction_raw,
                    distilled_constraint=s.distilled_constraint,
                    scope=s.scope,
                    is_active=s.is_active,
                    timestamp=s.timestamp,
                )
                for s in traj.user_steerings
            ],
            created_at=traj.created_at,
            updated_at=traj.updated_at,
        )


_service_instance: TaskTriadTrajectoryService | None = None


def get_task_triad_trajectory_service() -> TaskTriadTrajectoryService:
    """Obtain singleton instance of TaskTriadTrajectoryService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = TaskTriadTrajectoryService()
    return _service_instance
