"""Kanban TaskRunner — bridges KanbanTask to the Agent execution pipeline.

Implements the ``TaskRunner`` protocol from the harness layer, wiring each
task through ``AgentProfileResolver`` → ``AgentFactory`` → ``GeneralAgent``
so that WorkBoard tasks execute with the full agent profile (model, skills,
tools, memory, security).

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::TaskRunner (POS: Harness protocol.)
- myrm_agent_harness.toolkits.kanban.context_builder::build_task_context (POS: Worker context.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskTimeoutError (POS: Kanban domain types.)
- myrm_agent_harness.agent.goals.protocols::GoalProvider (POS: Goal lifecycle protocol.)
- myrm_agent_harness.api.hooks::deferral_wait_s (POS: Waitable provider usage-limit window of an LLM error.)
- app.services.agent.goals.goal_registry::GoalRegistry (POS: Session-level goal management.)
- task_runner.stream::build_multimodal_query (POS: Multimodal query assembly.)
- task_runner.worktree::resolve_workspace, cleanup_worktree, merge_task_worktree, hold_for_unlanded_parents, hold_for_unusable_workdir (POS: Git worktree isolation and the run-entry gates on parents' failed merges and on a too-broad working folder.)
- task_runner.profile::resolve_agent_profile (POS: Agent profile resolution.)
- task_runner.agent_run::execute_agent, KANBAN_CHANNEL (POS: Worker agent build and stream draining for one task.)
- task_runner.outcomes::map_goal_outcome, resolve_run_outcome (POS: What a finished run means for its task.)

[OUTPUT]
- KanbanTaskRunner: Concrete TaskRunner with goal-mode support, per-workspace
  write serialization and ``SCHEDULED`` rescheduling of provider usage limits.

[POS]
Server-layer TaskRunner that executes kanban tasks through the agent pipeline.
``agent_run`` builds and streams the agent and ``outcomes`` decides what the
finished run means (completion gate, goal-mode mapping); this module schedules
the run, reschedules provider usage limits and serializes agent writes to shared
workspace directories to prevent concurrent file corruption. Supports goal-mode
for autonomous multi-turn execution via GoalProvider injection.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from myrm_agent_harness.api import KanbanStore
from myrm_agent_harness.api.hooks import deferral_wait_s

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from myrm_agent_harness.agent.goals.protocols import GoalProvider
from myrm_agent_harness.toolkits.kanban.context_builder import build_task_context
from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    KanbanTask,
    TaskExecutionResult,
    TaskTimeoutError,
)

from app.core.agent.run_activity import track_background_agent_run
from app.core.channel_bridge.persistent_background import is_persistent_background
from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.kanban.task_runner.agent_run import KANBAN_CHANNEL, execute_agent
from app.services.kanban.task_runner.outcomes import map_goal_outcome, resolve_run_outcome
from app.services.kanban.task_runner.profile import (
    _ResolvedProfile,
    resolve_agent_profile,
)
from app.services.kanban.task_runner.stream import (
    _classify_content_type,
    build_multimodal_query,
)
from app.services.kanban.task_runner.worktree import (
    cleanup_worktree,
    hold_for_unlanded_parents,
    hold_for_unusable_workdir,
    merge_task_worktree,
    resolve_workspace,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 600
_BACKGROUND_TASK_TIMEOUT_SECONDS = 3600
_USAGE_LIMIT_BLOCK_REASON = "Waiting for the model usage limit to reset; resumes automatically"

_WAIT_NOTE_EN = "Waiting for another task to finish using this working directory…"
_WAIT_NOTE_ZH = "正在等待其他任务释放此工作目录…"

__all__ = ["KanbanTaskRunner", "_ResolvedProfile", "_classify_content_type"]


class KanbanTaskRunner:
    """Concrete TaskRunner that executes tasks through the Agent pipeline."""

    def __init__(
        self,
        store: KanbanStore,
        *,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._store = store
        self._timeout_seconds = timeout_seconds
        self._workspace_locks: dict[str, asyncio.Lock] = {}

    async def run(self, task: KanbanTask) -> tuple[bool, str] | TaskExecutionResult:
        # Before anything is built or paid for: a working folder the workspace gate would refuse, or a parent whose
        # code never landed, holds the task for the user.
        if (held := await hold_for_unusable_workdir(self._store, task)) is not None:
            return held
        if (held := await hold_for_unlanded_parents(self._store, task)) is not None:
            return held
        context = await build_task_context(self._store, task.task_id)
        profile = await resolve_agent_profile(task.agent_id)
        workspace_root = await resolve_workspace(self._store, task)
        context = self._augment_context(task, context, workspace_root)
        query_input = await build_multimodal_query(task, context)

        is_background_task = is_persistent_background(task.metadata)
        default_timeout = _BACKGROUND_TASK_TIMEOUT_SECONDS if is_background_task else self._timeout_seconds
        effective_timeout = task.max_runtime_seconds or default_timeout

        goal_provider = await self._setup_goal_provider(task) if task.goal_mode else None

        self._register_background_tokens(task)
        t0 = time.monotonic()
        async with self._workspace_lock(task, workspace_root):
            try:
                with track_background_agent_run():
                    result = await asyncio.wait_for(
                        self._execute_agent(
                            task,
                            query_input,
                            profile,
                            workspace_root,
                            goal_provider=goal_provider,
                        ),
                        timeout=effective_timeout,
                    )
                if goal_provider:
                    mapped = await self._map_goal_outcome(task, goal_provider, result)
                    return await self._resolve_run_outcome(task.task_id, mapped)
                return await self._resolve_run_outcome(task.task_id, result)
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - t0
                logger.warning(
                    "Kanban task %s timed out after %.0fs (limit %ds)",
                    task.task_id[:8],
                    elapsed,
                    effective_timeout,
                )
                raise TaskTimeoutError(
                    task_id=task.task_id,
                    elapsed_seconds=elapsed,
                    limit_seconds=effective_timeout,
                ) from None
            except Exception as exc:
                wait_s = deferral_wait_s(exc)
                if wait_s is not None:
                    logger.warning(
                        "Kanban task %s hit a provider usage limit; rescheduled in %.0fs: %s",
                        task.task_id[:8],
                        wait_s,
                        exc,
                    )
                    return TaskExecutionResult.blocked(
                        _USAGE_LIMIT_BLOCK_REASON,
                        block_kind=BlockKind.SCHEDULED,
                        scheduled_until=datetime.now(UTC) + timedelta(seconds=wait_s),
                    )
                logger.warning("Kanban task %s failed: %s", task.task_id[:8], exc)
                return False, str(exc)
            finally:
                self._unregister_background_tokens(task)
                if goal_provider:
                    GoalRegistry.unregister(f"kanban:{task.task_id}")

    @staticmethod
    def _augment_context(
        task: KanbanTask,
        context: str,
        workspace_root: str | None,
    ) -> str:
        """Append execution-environment hints to the worker context.

        Every kanban agent learns its workspace root; business layers can
        additionally inject task-specific instructions through the
        ``context_annotations`` metadata key (a list of strings).
        """
        additions: list[str] = []
        if workspace_root:
            additions.append(f"Workspace root: {workspace_root}")
        annotations = task.metadata.get("context_annotations") if task.metadata else None
        if isinstance(annotations, list):
            additions.extend(str(item) for item in annotations if item)
        if not additions:
            return context
        return f"{context}\n\n## Execution environment\n" + "\n".join(additions)

    def _register_background_tokens(self, task: KanbanTask) -> None:
        if not is_persistent_background(task.metadata):
            return
        try:
            from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
            from myrm_agent_harness.utils.runtime.steering import SteeringToken

            from app.core.channel_bridge.setup import get_background_task_handler

            handler = get_background_task_handler()
            if handler:
                handler.register_runtime_tokens(
                    task.task_id,
                    CancellationToken(),
                    SteeringToken(),
                )
        except Exception:
            logger.debug("Could not register background tokens for %s", task.task_id[:8])

    def _unregister_background_tokens(self, task: KanbanTask) -> None:
        if not is_persistent_background(task.metadata):
            return
        try:
            from app.core.channel_bridge.setup import get_background_task_handler

            handler = get_background_task_handler()
            if handler:
                handler.unregister_runtime_tokens(task.task_id)
        except Exception:
            logger.debug("Could not unregister background tokens for %s", task.task_id[:8])

    @asynccontextmanager
    async def _workspace_lock(
        self,
        task: KanbanTask,
        workspace_root: str | None,
    ) -> AsyncIterator[None]:
        """Serialize agent writes to a shared workspace directory.

        Tasks without a resolved workspace (``None``) skip locking entirely, as
        there is no shared directory to corrupt. Worktree-backed tasks already
        resolve to per-task unique paths, so they never contend here.
        """
        if not workspace_root:
            yield
            return
        key = os.path.realpath(workspace_root)
        lock = self._workspace_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._workspace_locks[key] = lock

        if lock.locked():
            note = await self._wait_note()
            try:
                await self._store.update_heartbeat(task.task_id, note=note)
            except Exception:
                logger.debug("Could not write wait note for %s", task.task_id[:8])

        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
            if not lock.locked():
                self._workspace_locks.pop(key, None)

    async def _wait_note(self) -> str:
        """Pick a locale-appropriate wait note for the blocked task."""
        try:
            from app.core.agent.tool_description_locale import (
                resolve_agent_params_locale,
            )
            from app.core.channel_bridge.config_loader import load_user_configs

            user_cfgs = await load_user_configs()
            locale = resolve_agent_params_locale(
                personal_settings=user_cfgs.personal_settings_dict or {},
                channel=KANBAN_CHANNEL,
            )
        except Exception:
            locale = "en"
        return _WAIT_NOTE_ZH if locale.startswith("zh") else _WAIT_NOTE_EN

    async def cleanup_worktree(self, task: KanbanTask) -> bool:
        return await cleanup_worktree(self._store, task)

    async def merge_task_worktree(self, task: KanbanTask) -> tuple[bool, list[str]]:
        return await merge_task_worktree(self._store, task)

    async def _load_attachment_ids(self, task_id: str) -> list[str]:
        from app.services.kanban.task_runner.stream import (
            _load_attachment_ids as load_ids,
        )

        return await load_ids(task_id)

    async def _extract_pdf_text(self, file_id: str) -> str:
        from app.services.kanban.task_runner.stream import (
            _extract_pdf_text as extract_pdf,
        )

        return await extract_pdf(file_id)

    async def _extract_document_text(self, file_id: str) -> str:
        from app.services.kanban.task_runner.stream import (
            _extract_document_text as extract_doc,
        )

        return await extract_doc(file_id)

    async def _build_multimodal_query(
        self,
        task: KanbanTask,
        text_context: str,
    ) -> str | list[dict[str, object]]:
        return await build_multimodal_query(
            task,
            text_context,
            load_attachment_ids=self._load_attachment_ids,
            extract_pdf=self._extract_pdf_text,
            extract_document=self._extract_document_text,
        )

    async def _resolve_profile(self, agent_id: str | None) -> _ResolvedProfile | None:
        return await resolve_agent_profile(agent_id)

    async def _setup_goal_provider(self, task: KanbanTask) -> GoalProvider:
        """Create or resume a GoalProvider for a goal-mode kanban task."""
        from myrm_agent_harness.agent.goals.types import GoalBudget, GoalStatus

        session_id = f"kanban:{task.task_id}"
        provider = GoalRegistry.get_or_create_provider(session_id)

        active = await provider.get_active_goal(session_id)
        if active:
            return provider

        latest = await provider.get_latest_goal(session_id)
        if latest and not latest.is_terminal and latest.status in (GoalStatus.PAUSED, GoalStatus.BUDGET_LIMITED, GoalStatus.WAIT):
            await provider.resume_goal(latest.goal_id, reset_turns=False)
            logger.info("Goal %s resumed for kanban task %s", latest.goal_id, task.task_id[:8])
            return provider

        budget = GoalBudget(max_turns=task.goal_max_turns or 10)
        criteria = task.metadata.get("completion_criteria")
        acceptance: list[dict[str, object]] | None = None
        if isinstance(criteria, list):
            acceptance = criteria
        elif isinstance(criteria, str) and criteria.strip():
            acceptance = [{"type": "semantic", "criteria": criteria}]

        await provider.create_goal(
            session_id=session_id,
            objective=task.description or task.title,
            budget=budget,
            acceptance_criteria=acceptance,
            ui_summary=task.title[:120],
        )
        logger.info(
            "Goal created for kanban task %s (max_turns=%s)",
            task.task_id[:8],
            budget.max_turns,
        )
        return provider

    async def _map_goal_outcome(
        self,
        task: KanbanTask,
        goal_provider: GoalProvider,
        agent_result: tuple[bool, str],
    ) -> tuple[bool, str] | TaskExecutionResult:
        return await map_goal_outcome(self._store, task, goal_provider, agent_result)

    async def _resolve_run_outcome(
        self,
        task_id: str,
        agent_result: tuple[bool, str] | TaskExecutionResult,
    ) -> tuple[bool, str] | TaskExecutionResult:
        return await resolve_run_outcome(self._store, task_id, agent_result)

    async def _execute_agent(
        self,
        task: KanbanTask,
        context: str | list[dict[str, object]],
        profile: _ResolvedProfile | None,
        workspace_root: str | None = None,
        goal_provider: GoalProvider | None = None,
    ) -> tuple[bool, str]:
        return await execute_agent(
            self._store,
            task,
            context,
            profile,
            workspace_root=workspace_root,
            goal_provider=goal_provider,
        )
