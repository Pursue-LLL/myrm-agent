"""
[POS] app/services/agent/goals/split_session_goal_service.py
[INPUT] threading, time, uuid, app.schemas.split_session_goal
[OUTPUT] SplitSessionGoalService, get_split_session_goal_service, BUILTIN_SPLIT_SESSION_TEMPLATES

Service managing Split-Session 2-Window (Window 1: Ship / Window 2: Plan) Goal state machine, templates, and handover digests.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
import time
import uuid

from app.schemas.split_session_goal import (
    AdvanceSplitSessionRequestDTO,
    CreateSplitSessionGoalRequestDTO,
    NextIterationPlanDTO,
    SplitSessionGoalInstanceDTO,
    SplitSessionGoalTemplateDTO,
)

BUILTIN_SPLIT_SESSION_TEMPLATES: list[SplitSessionGoalTemplateDTO] = [
    SplitSessionGoalTemplateDTO(
        template_id="code_ship_architecture_plan",
        name_zh="代码快速交付与架构演进双窗口",
        name_en="Code Ship & Architecture Plan (2-Window Split)",
        description_zh="窗口 1 专注产出可运行代码与 100% 自动化测试通过；窗口 2 重置上下文专注规划下一阶段架构蓝图与任务分解，规避长会话上下文膨胀与 Weekly 限额消耗。",
        description_en="Window 1 strictly ships runnable code with green tests. Window 2 resets context to synthesize architectural roadmap and task breakdown, conserving weekly model limits.",
        window1_prompt_template="[WINDOW 1: SHIP MODE] Focus exclusively on implementing working code and passing tests. Deliverables must be verified before pause.",
        window2_prompt_template="[WINDOW 2: PLAN MODE] Ingest the Window 1 Ship Dossier in a clean context. Formulate next architectural milestones and task specifications.",
        acceptance_gate="Automated test suite must execute cleanly with zero errors before Window 1 closes.",
    ),
    SplitSessionGoalTemplateDTO(
        template_id="feature_delivery_roadmap_plan",
        name_zh="功能发布验收与演进路线规划双窗口",
        name_en="Feature Delivery & Roadmap Planning (2-Window Split)",
        description_zh="窗口 1 交付核心业务功能组件并生成交付物凭证；窗口 2 在纯净上下文中产出产品迭代路线图与下一期需求规范。",
        description_en="Window 1 delivers core feature components and verified artifact dossier. Window 2 synthesizes product evolution roadmap and requirement specs in a clean turn.",
        window1_prompt_template="[WINDOW 1: FEATURE SHIP] Implement feature components, generate deliverables, and execute validation.",
        window2_prompt_template="[WINDOW 2: ROADMAP PLAN] Review feature deliverables and project the next evolution roadmap.",
        acceptance_gate="Core feature deliverables verified and release notes documented.",
    ),
]


class SplitSessionGoalService:
    """Thread-safe coordinator for Split-Session 2-Window goal execution."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._templates: dict[str, SplitSessionGoalTemplateDTO] = {t.template_id: t for t in BUILTIN_SPLIT_SESSION_TEMPLATES}
        self._instances: dict[str, SplitSessionGoalInstanceDTO] = {}

    def list_templates(self) -> list[SplitSessionGoalTemplateDTO]:
        """Retrieve collection of available split-session templates."""
        with self._lock:
            return list(self._templates.values())

    def get_template(self, template_id: str) -> SplitSessionGoalTemplateDTO | None:
        """Fetch template definition by ID."""
        with self._lock:
            return self._templates.get(template_id)

    def create_instance(
        self,
        req: CreateSplitSessionGoalRequestDTO,
    ) -> SplitSessionGoalInstanceDTO:
        """Instantiate a new Split-Session Goal state machine."""
        with self._lock:
            if req.template_id not in self._templates:
                raise ValueError(f"Unknown split-session template ID: '{req.template_id}'.")

            inst_id = f"split-goal-{uuid.uuid4().hex[:10]}"
            now = time.time()
            instance = SplitSessionGoalInstanceDTO(
                instance_id=inst_id,
                session_id=req.session_id,
                template_id=req.template_id,
                title=req.title,
                current_phase="window1_shipping",
                ship_dossier=None,
                iteration_plan=None,
                created_at=now,
                updated_at=now,
            )
            self._instances[inst_id] = instance
            return instance

    def get_instance(self, instance_id: str) -> SplitSessionGoalInstanceDTO | None:
        """Retrieve goal instance snapshot by ID."""
        with self._lock:
            return self._instances.get(instance_id)

    def advance_phase(
        self,
        instance_id: str,
        req: AdvanceSplitSessionRequestDTO,
    ) -> SplitSessionGoalInstanceDTO:
        """Advance split-session lifecycle state with validation gates."""
        with self._lock:
            inst = self._instances.get(instance_id)
            if inst is None:
                raise KeyError(f"Split-session goal instance '{instance_id}' not found.")

            current = inst.current_phase
            target = req.target_phase
            now = time.time()

            # State machine transitions
            if target == "window1_completed":
                if current != "window1_shipping":
                    raise ValueError(f"Cannot complete Window 1 from current phase '{current}'.")
                if req.ship_dossier is None:
                    raise ValueError("Advancing to 'window1_completed' requires 'ship_dossier'.")
                if not req.ship_dossier.tests_passed:
                    raise ValueError("Cannot complete Window 1: tests have not passed acceptance gate.")
                inst.ship_dossier = req.ship_dossier
                inst.current_phase = "window1_completed"

            elif target == "window2_planning":
                if current != "window1_completed":
                    raise ValueError(f"Cannot enter Window 2 planning before Window 1 is completed (current: '{current}').")
                inst.current_phase = "window2_planning"

            elif target == "all_completed":
                if current != "window2_planning":
                    raise ValueError(f"Cannot complete all phases from current phase '{current}'.")
                if req.iteration_plan is None:
                    raise ValueError("Advancing to 'all_completed' requires 'iteration_plan'.")

                # Calculate estimated tokens saved from context isolation
                estimated_savings = req.iteration_plan.estimated_tokens_savings
                if estimated_savings <= 0:
                    estimated_savings = 32000  # typical 32k tokens preserved by fresh window

                plan_with_savings = NextIterationPlanDTO(
                    next_objective=req.iteration_plan.next_objective,
                    architecture_notes=req.iteration_plan.architecture_notes,
                    planned_task_steps=req.iteration_plan.planned_task_steps,
                    estimated_tokens_savings=estimated_savings,
                )
                inst.iteration_plan = plan_with_savings
                inst.current_phase = "all_completed"

            else:
                raise ValueError(f"Unsupported transition target phase: '{target}'.")

            inst.updated_at = now
            return inst


_GLOBAL_SPLIT_SESSION_SERVICE: SplitSessionGoalService | None = None


def get_split_session_goal_service() -> SplitSessionGoalService:
    """FastAPI dependency provider for SplitSessionGoalService singleton."""
    global _GLOBAL_SPLIT_SESSION_SERVICE
    if _GLOBAL_SPLIT_SESSION_SERVICE is None:
        _GLOBAL_SPLIT_SESSION_SERVICE = SplitSessionGoalService()
    return _GLOBAL_SPLIT_SESSION_SERVICE
