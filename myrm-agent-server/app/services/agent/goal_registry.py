"""Goal Registry — 会话级 Goal 句柄全局注册表.

[INPUT]
- myrm_agent_harness.agent.goals.protocol::GoalProvider (POS: Goal provider protocol)
- myrm_agent_harness.agent.sub_agents.planner.storage::PlannerStorage (POS: Planner 计划持久化)
- app.services.chat.chat_service::ChatService (POS: Chat CRUD 编排层)
- app.services.memory.shared_context::SharedContextService (POS: Shared Context 共享上下文服务)
- app.services.memory.shared_context_materializer::SharedContextProposalMaterializer (POS: Shared Context 写入物化服务)
- app.services.event.app_event_bus::get_event_bus (POS: 应用级事件总线)

[OUTPUT]
- GoalRegistry: 全局注册表，通过 session_id 管理运行中的 GoalProvider
- ServerGoalManager: 扩展 harness GoalManager，提供 semantic judge 与 Goal 完成时 SharedContext 决策归档
- _resolve_shared_context_ids_for_goal: 按 agent+channel+conversation 解析 Goal 会话的 SharedContext 绑定

[POS]
会话级 Goal 注册表。使 HTTP API 能够通过 session_id 定位正在运行的
Agent 会话的 GoalProvider，从而在运行时控制 Goal 状态（暂停/恢复）。
与 SteeringRegistry 和 CancellationRegistry 形成对称设计。
"""

import json
import logging
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.goals.manager import GoalManager

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.protocols import GoalProvider
    from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
    from myrm_agent_harness.agent.goals.verification.base import VerificationResult

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_INLINE_RE = re.compile(
    r"\{[^{}]*\"done\"\s*:\s*(?:true|false)[^{}]*\}", re.DOTALL
)


def _parse_judge_json(raw: str) -> dict[str, object] | None:
    """Robustly extract {"done": bool, "reason": str} from LLM judge output.

    Handles: raw JSON, markdown-fenced JSON, JSON embedded in prose,
    and boolean strings like "True"/"False".
    """
    # 1. Direct JSON parse
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "done" in obj:
            return _normalize_done(obj)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Markdown fenced block
    m = _JSON_BLOCK_RE.search(raw)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "done" in obj:
                return _normalize_done(obj)
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Inline JSON extraction
    m = _JSON_INLINE_RE.search(raw)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and "done" in obj:
                return _normalize_done(obj)
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _normalize_done(obj: dict[str, object]) -> dict[str, object]:
    """Normalize the 'done' value to a Python bool."""
    done = obj.get("done")
    if isinstance(done, str):
        obj["done"] = done.strip().lower() in ("true", "yes", "1")
    return obj


async def _resolve_shared_context_ids_for_goal(session_id: str) -> list[str]:
    """Resolve SharedContext bindings for a goal session (align with agent request converter)."""
    from app.services.memory.shared_context import resolve_shared_context_ids

    agent_id: str | None = None
    try:
        from app.services.chat.chat_service import ChatService

        chat = await ChatService.get_chat_metadata(session_id)
        if chat is not None:
            agent_id = chat.agent_id
    except Exception as exc:
        logger.warning(
            "Failed to load chat metadata for goal consolidation session %s: %s",
            session_id,
            exc,
        )

    return await resolve_shared_context_ids(
        agent_id=agent_id,
        channel_id="web_chat",
        conversation_id=session_id,
    )


class ServerGoalManager(GoalManager):
    """Server-side GoalManager that implements boundary methods like semantic evaluation."""

    def __init__(self, storage_provider, session_id: str | None = None):
        super().__init__(storage_provider)
        self.session_id = session_id

    async def update_status(self, goal_id: str, status: "GoalStatus") -> "Goal":
        goal = await super().update_status(goal_id, status)

        from myrm_agent_harness.agent.goals.types import GoalStatus

        if status == GoalStatus.COMPLETE:
            await self._consolidate_decisions_on_completion(goal)

        return goal

    async def _consolidate_decisions_on_completion(self, goal: "Goal") -> None:
        """Write active architectural decisions to Shared Context when a goal completes."""
        try:
            from myrm_agent_harness.agent.sub_agents.planner.storage import (
                PlannerStorage,
            )

            planner_storage = PlannerStorage(self._storage._storage, prefix="planner_")
            plan = await planner_storage.load_plan()

            if not plan or not plan.decisions:
                return

            active_decisions = [d for d in plan.decisions if d.status == "active"]
            if not active_decisions:
                return

            decision_text = "## Architectural Decisions\n\n"
            for dec in active_decisions:
                decision_text += (
                    f"### {dec.topic}\n"
                    f"- **Decision:** {dec.decision}\n"
                    f"- **Rationale:** {dec.rationale}\n\n"
                )

            from app.platform_utils import get_session_factory
            from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
            from app.services.memory.shared_context import SharedContextService
            from app.services.memory.shared_context_materializer import (
                SharedContextProposalMaterializer,
            )

            context_ids = await _resolve_shared_context_ids_for_goal(goal.session_id)
            if not context_ids:
                logger.info(
                    "No SharedContext binding for session %s; skip decision consolidation",
                    goal.session_id,
                )
                return

            session_factory = get_session_factory()
            materialized_count = 0
            pending_count = 0
            async with session_factory() as db:
                service = SharedContextService(db)
                materializer = SharedContextProposalMaterializer(db)
                for context_id in context_ids:
                    context = await service.get_context(context_id)
                    if context is None or context.status != "active":
                        continue

                    proposal = await service.create_write_proposal(
                        context_id=context_id,
                        memory_type="semantic",
                        content=decision_text,
                        metadata={
                            "source": "goal_completion",
                            "goal_id": goal.goal_id,
                            "tags": ["Architecture", "Auto-Consolidated"],
                        },
                        source_type="goal_completion",
                        source_id=goal.goal_id,
                    )
                    if proposal is None:
                        logger.warning(
                            "SharedContext %s not found; skip decision write proposal",
                            context_id,
                        )
                        continue

                    if proposal.status in ("approved", "rejected"):
                        logger.info(
                            "Decision consolidation idempotent skip: context=%s proposal=%s status=%s",
                            context_id,
                            proposal.id,
                            proposal.status,
                        )
                        continue

                    policy = context.policy or {}
                    auto_approve = policy.get("goal_completion_auto_approve") is not False

                    if auto_approve:
                        await materializer.approve_write_proposal(proposal.id)
                        materialized_count += 1
                        logger.info(
                            "Decision consolidation auto-materialized: context=%s proposal=%s",
                            context_id,
                            proposal.id,
                        )
                    else:
                        pending_count += 1
                        logger.info(
                            "Decision consolidation proposal pending approval: context=%s proposal=%s",
                            context_id,
                            proposal.id,
                        )

                    get_event_bus().publish(
                        AppEvent(
                            event_type=AppEventType.MEMORY_OPERATION,
                            data={
                                "operation": "goal_completion_consolidation",
                                "context_id": context_id,
                                "context_name": context.name,
                                "proposal_id": proposal.id,
                                "goal_id": goal.goal_id,
                                "auto_approved": bool(auto_approve),
                                "decision_count": len(active_decisions),
                            },
                        )
                    )
            logger.info(
                "Memory consolidation: %d decisions → %d materialized, %d pending",
                len(active_decisions),
                materialized_count,
                pending_count,
            )
        except Exception as e:
            logger.warning("Failed to consolidate memory on goal completion: %s", e)
            try:
                from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

                get_event_bus().publish(
                    AppEvent(
                        event_type=AppEventType.MEMORY_OPERATION,
                        data={
                            "operation": "goal_completion_consolidation_failed",
                            "goal_id": goal.goal_id,
                            "session_id": goal.session_id,
                            "error": str(e),
                        },
                    )
                )
            except Exception:
                logger.warning(
                    "Failed to publish goal completion consolidation failure event",
                    exc_info=True,
                )

    async def evaluate_semantic(
        self, criteria: str, content: str, context_messages: list[object] | None = None
    ) -> "VerificationResult":
        from litellm import acompletion
        from myrm_agent_harness.agent.goals.verification.base import VerificationResult

        from app.services.agent.platform_config import build_platform_litellm_kwargs

        try:
            llm_kwargs = await build_platform_litellm_kwargs()
            
            requires_vision = False
            if context_messages:
                for msg in context_messages:
                    if getattr(msg, "type", "") == "tool" and getattr(msg, "name", "") in (
                        "browser_interact",
                        "browser_extract",
                        "computer_use",
                        "desktop_snapshot_tool",
                    ):
                        requires_vision = True
                        break

            screenshot_b64 = None
            if requires_vision and getattr(self, "session_id", None):
                from app.services.agent.gateway import get_agent_gateway
                gateway = get_agent_gateway()
                
                browser_session = gateway.get_active_browser_session(self.session_id)
                if browser_session is not None:
                    try:
                        screenshot_b64 = await browser_session.extract_screenshot(scale=1.0)
                    except Exception as e:
                        logger.warning("Failed to extract browser screenshot for semantic evaluation: %s", e)
                
                if not screenshot_b64:
                    desktop_session = gateway.get_active_desktop_session(self.session_id)
                    if desktop_session is not None:
                        try:
                            action_result = await desktop_session.take_screenshot()
                            if action_result and action_result.success and action_result.screenshot_base64:
                                screenshot_b64 = action_result.screenshot_base64
                        except Exception as e:
                            logger.warning("Failed to extract desktop screenshot for semantic evaluation: %s", e)

            messages: list[dict[str, object]] = [
                {"role": "system", "content": criteria},
            ]

            if screenshot_b64:
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": content},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}"}
                        }
                    ]
                })
                logger.info("Multimodal Evaluator triggered: Injected visual proof (screenshot) for goal evaluation.")
            else:
                messages.append({"role": "user", "content": content})

            response = await acompletion(
                messages=messages,
                temperature=0.0,
                max_tokens=1024,
                timeout=10,
                **llm_kwargs,
            )
            msg = response.choices[0].message
            raw = (msg.content or "").strip()

            # Reasoning models may produce empty content with reasoning in a separate field
            if not raw:
                reasoning = getattr(msg, "reasoning_content", None) or ""
                if reasoning:
                    raw = reasoning.strip()

            parsed = _parse_judge_json(raw)

            if parsed is not None:
                done = parsed.get("done", False)
                reason = str(parsed.get("reason", ""))
                if done:
                    return VerificationResult(passed=True, reason=reason)
                return VerificationResult(passed=False, reason=reason)

            lower = raw.lower()
            if (
                lower.startswith("pass")
                or '"done": true' in lower
                or '"done":true' in lower
            ):
                return VerificationResult(passed=True, reason=raw)
            return VerificationResult(passed=False, reason=raw)

        except Exception as e:
            logger.error("Semantic evaluation failed: %s", e)
            return VerificationResult(
                passed=False, reason="Server evaluation failed", error_logs=str(e)
            )


class GoalRegistry:
    """Global registry for active goal providers, keyed by session_id.

    Enables the goal API endpoints to locate and manage goals for
    running agent sessions.

    Thread-safe for concurrent access from multiple endpoints.
    """

    _lock = threading.Lock()
    _providers: dict[str, "GoalProvider"] = {}

    @classmethod
    def get_or_create_provider(cls, session_id: str) -> "GoalProvider":
        """Get the goal provider for a session, creating it if it doesn't exist.

        This ensures that the GoalManager (which holds memory state like suppression flags)
        is a singleton per session during the server's lifecycle.
        """
        with cls._lock:
            if session_id not in cls._providers:
                from app.platform_utils import get_storage_provider

                cls._providers[session_id] = ServerGoalManager(get_storage_provider(), session_id=session_id)
                logger.debug("Created new goal provider: session_id=%s", session_id)
            return cls._providers[session_id]

    @classmethod
    def get_provider(cls, session_id: str) -> "GoalProvider | None":
        """Get the goal provider for a session if it exists in memory."""
        with cls._lock:
            return cls._providers.get(session_id)

    @classmethod
    def start_branch_watcher(cls) -> None:
        """Start a background loop to watch .git/HEAD for active sessions."""
        import asyncio
        import os

        if getattr(cls, "_watcher_task", None) and not cls._watcher_task.done():
            return

        async def _watcher_loop() -> None:
            # We use os.stat polling on .git/HEAD for zero-latency, zero-overhead detection
            last_mtime = 0.0
            git_head_path = None
            disabled = False

            while True:
                try:
                    if disabled:
                        await asyncio.sleep(10.0)
                        git_head_path = None
                        disabled = False
                    else:
                        await asyncio.sleep(0.5)

                    with cls._lock:
                        session_ids = list(cls._providers.keys())
                    
                    if not session_ids:
                        continue

                    # Determine workspace_dir from the first provider (assuming single-tenant sandbox)
                    # In a real setup, workspace_dir should be injected, but we fallback to cwd
                    from app.config.settings import settings
                    workspace_dir = str(Path(settings.project_dir).expanduser().resolve())
                    if not git_head_path:
                        git_head_path = os.path.join(workspace_dir, ".git", "HEAD")
                        if not os.path.exists(git_head_path):
                            logger.debug("Branch watcher: .git/HEAD not found at %s. Pausing watcher.", git_head_path)
                            git_head_path = None
                            disabled = True
                            continue
                    
                    try:
                        current_mtime = os.stat(git_head_path).st_mtime
                    except (FileNotFoundError, PermissionError):
                        continue

                    if current_mtime != last_mtime:
                        last_mtime = current_mtime
                        for sid in session_ids:
                            try:
                                await check_and_handle_branch_stash(sid, workspace_dir=workspace_dir)
                            except Exception as e:
                                logger.error("Branch watcher error for session %s: %s", sid, e)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Branch watcher loop error: %s", e)

        cls._watcher_task = asyncio.create_task(_watcher_loop())

    @classmethod
    def stop_branch_watcher(cls) -> None:
        if hasattr(cls, "_watcher_task") and cls._watcher_task:
            cls._watcher_task.cancel()

    @classmethod
    def unregister(cls, session_id: str) -> None:
        """Remove a provider when the agent stream ends."""
        with cls._lock:
            if cls._providers.pop(session_id, None):
                logger.debug("Unregistered goal provider: session_id=%s", session_id)


async def get_current_git_branch(workspace_dir: str | None = None) -> str | None:
    """Run async subprocess to get the current Git branch name of the workspace."""
    import asyncio

    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "symbolic-ref", "--short", "HEAD",
            cwd=workspace_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="ignore").strip()
    except Exception:
        pass

    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--abbrev-ref", "HEAD",
            cwd=workspace_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            branch = stdout.decode("utf-8", errors="ignore").strip()
            if branch and branch != "HEAD":
                return branch
    except Exception:
        pass
    return None


async def check_and_handle_branch_stash(
    session_id: str, workspace_dir: str | None = None
) -> None:
    """Perceive git branch changes, auto stash/restore/migrate goals and planner progress."""
    branch = await get_current_git_branch(workspace_dir)
    if not branch:
        return

    provider = GoalRegistry.get_or_create_provider(session_id)
    storage = provider._storage._storage

    last_branch_key = f"goals_last_branch/{session_id}"
    try:
        last_branch_raw = await storage.read(last_branch_key)
        last_branch = last_branch_raw.decode("utf-8") if last_branch_raw else None
    except FileNotFoundError:
        last_branch = None

    if last_branch == branch:
        return

    # Check if the new branch has a stash
    # Using the new composite key format from Harness
    from myrm_agent_harness.agent.goals.storage import _GOAL_NAMESPACE
    try:
        stash_raw = await storage.read(key=f"{_GOAL_NAMESPACE}_stash/{session_id}/{branch}")
        has_stash = bool(stash_raw)
    except FileNotFoundError:
        has_stash = False

    migrated = False

    if last_branch:
        active_goal = await provider.get_active_goal(session_id)
        if active_goal:
            from myrm_agent_harness.agent.sub_agents.planner import PlannerStorage
            planner_storage = PlannerStorage(storage, prefix="planner_")
            plan = await planner_storage.load_plan()
            plan_dict = plan.dict() if plan else None

            # Intent-Aware Migration: If the target branch has no stash, we assume it's a new branch
            # or a branch where the user wants to continue the current goal (MIGRATE).
            if not has_stash:
                logger.info("Intent-Aware Migration: Migrating active goal to new branch %s", branch)
                migrated = True
            else:
                # Target branch has its own stash, so we STASH the current goal
                stashed = await provider.stash_goal(
                    session_id=session_id,
                    branch_name=last_branch,
                    planner_state=plan_dict,
                    chat_history=None,
                )
                if stashed:
                    logger.info(
                        "Branch switch perceived: stashed active goal and plan for branch %s",
                        last_branch,
                    )
                    await planner_storage.delete_plan()

    # Update the last perceived branch
    await storage.write(last_branch_key, branch.encode("utf-8"))

    # Update Kanban tasks metadata and append branch_switched event
    try:
        from app.services.kanban.service import KanbanService
        kanban_svc = KanbanService.get_instance()
        await kanban_svc.update_active_tasks_branch_metadata(
            new_branch=branch,
            old_branch=last_branch,
            migrated=migrated
        )
    except Exception as e:
        logger.warning("Kanban branch metadata update skipped: %s", e)

    restored = None
    if not migrated:
        # Restore stashed goal for the new branch if exists
        restored = await provider.restore_goal(session_id, branch)
        if restored:
            if restored.get("planner_state"):
                from myrm_agent_harness.agent.sub_agents.planner import PlannerStorage
                from myrm_agent_harness.agent.sub_agents.planner.schemas import Plan

                planner_storage = PlannerStorage(storage, prefix="planner_")
                try:
                    plan = Plan.model_validate(restored["planner_state"])
                    await planner_storage.save_plan(plan)
                    logger.info(
                        "Branch switch perceived: restored goal and plan for branch %s",
                        branch,
                    )
                except Exception as e:
                    logger.error("Failed to restore plan for branch %s: %s", branch, e)

    try:
        from app.services.event.app_event_bus import AppEvent, get_event_bus
        bus = get_event_bus()
        bus.publish(
            AppEvent(
                event_type="goal:branch_switched",
                data={
                    "chat_id": session_id,
                    "branch": branch,
                    "stashed_branch": last_branch,
                    "restored": bool(restored),
                    "migrated": migrated
                }
            )
        )
    except Exception as e:
        logger.error("Failed to publish goal:branch_switched event: %s", e)
