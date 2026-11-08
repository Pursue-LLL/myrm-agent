"""[INPUT]
- dynamic_workflow.spawn_cache::SpawnCacheParams (POS: 缓存指纹)
- dynamic_workflow.store::WorkflowEventStore (POS: L2 持久缓存)
- sub_agents.spawn_prep (POS: 与 delegate 共用的 spawn 准备)
- sub_agents.types (POS: 目录/配置/结果类型)
- sub_agents.orchestrator / verifier_selection (POS: 对抗式验证选择)

[OUTPUT]
- SpawnSubagentTool / WorkflowRunGuard / DwVerificationMode

[POS]
`dynamic_workflow/tools/` 的子 Agent 派生工具；负责并发、验证模式与结果规范化。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, cast

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from myrm_agent_harness.agent.dynamic_workflow.spawn_cache import SpawnCacheParams
from myrm_agent_harness.agent.dynamic_workflow.store import WorkflowEventStore
from myrm_agent_harness.agent.skills.mcp.progress_payload import (
    build_workflow_stage_event,
)
from myrm_agent_harness.agent.sub_agents.spawn_prep import (
    apply_readonly_to_config,
    build_child_context_from_parent_agent,
    coerce_spawn_readonly,
    enforce_spawn_policy_on_config,
    memory_isolation_scope,
)
from myrm_agent_harness.agent.sub_agents.types import SubagentCatalog, SubAgentResult
from myrm_agent_harness.core.security.path import coerce_filesystem_path
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

if TYPE_CHECKING:
    from myrm_agent_harness.agent.base_agent import BaseAgent

logger = logging.getLogger(__name__)

DEFAULT_MAX_SPAWN_PER_WORKFLOW = 50

DEFAULT_MAX_CONCURRENT_SPAWNS = 5

class DwVerificationMode(StrEnum):
    NONE = "none"
    ADVERSARIAL = "adversarial"
    AUDITOR_BLIND = "auditor_blind"
    MULTI_SKEPTIC = "multi_skeptic"

class WorkflowRunGuard:
    """Hard cap on total spawns and concurrent in-flight sub-agents."""

    __slots__ = (
        "_max_concurrent",
        "_max_spawns",
        "_semaphore",
        "_spawn_count",
    )

    def __init__(
        self,
        *,
        max_spawns: int = DEFAULT_MAX_SPAWN_PER_WORKFLOW,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT_SPAWNS,
    ) -> None:
        self._max_spawns = max_spawns
        self._max_concurrent = max_concurrent
        self._spawn_count = 0
        self._semaphore = asyncio.Semaphore(max_concurrent)

    @property
    def spawn_count(self) -> int:
        return self._spawn_count

    async def acquire_spawn_slot(self) -> str | None:
        if self._spawn_count >= self._max_spawns:
            return f"Workflow spawn limit reached ({self._max_spawns}). Reduce parallel tasks or split the workflow."
        self._spawn_count += 1
        await self._semaphore.acquire()
        return None

    def release_spawn_slot(self) -> None:
        self._semaphore.release()

def _normalize_spawn_result(result: object, *, task_id: str, agent_type: str) -> dict[str, object]:
    if isinstance(result, dict):
        return result

    if isinstance(result, SubAgentResult):
        return result.to_dict()

    status_val = getattr(result, "status", None)
    return {
        "success": getattr(result, "success", False),
        "task_id": getattr(result, "task_id", task_id),
        "agent_type": getattr(result, "agent_type", agent_type),
        "result": getattr(result, "result", None),
        "error": getattr(result, "error", None),
        "status": (
            status_val.value
            if status_val is not None and hasattr(status_val, "value")
            else str(status_val or "unknown")
        ),
    }

class SpawnSubagentInput(BaseModel):
    task_id: str = Field(..., description="Unique identifier for this sub-agent task.")
    agent_type: str = Field(
        default="generalPurpose",
        description="Type of agent to spawn (e.g., 'generalPurpose', 'shell').",
    )
    task_description: str = Field(..., description="The prompt/task for the sub-agent to execute.")
    readonly: bool = Field(
        default=False,
        description="If true: no file writes, no bash, no MCP tools unless marked read-only. For analysis-only tasks.",
    )
    verification_mode: Literal["none", "adversarial", "auditor_blind", "multi_skeptic"] = Field(
        default="none",
        description='Verification: "none" (default), "adversarial" (standard retry loop), "auditor_blind" (omits worker narrative to eliminate confirmation bias), or "multi_skeptic" (parallel multi-verifier voting).',
    )
    verifier_agent_type: str | None = Field(
        default=None,
        description="Optional verifier agent type when verification_mode is adversarial.",
    )
    max_verification_rounds: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Max adversarial verification rounds (1-5).",
    )
    complexity_tier: str | None = Field(
        default=None,
        description="Optional model tier hint ('simple', 'standard', 'reasoning').",
    )

class SpawnSubagentTool(BaseTool):
    """PTC tool that spawns sub-agents through the parent agent's delegate path."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "spawn_subagent"
    description: str = "Spawn a sub-agent to execute a task. This tool blocks until the sub-agent completes."
    args_schema: type[BaseModel] = SpawnSubagentInput

    parent_agent: object
    tool_registry_getter: Callable[[], list[object]]
    workflow_id: str
    catalog: object | None = None
    store: WorkflowEventStore | None = None
    cancel_token: object | None = None
    event_queue: asyncio.Queue[dict[str, object]] | None = None
    message_id: str = ""
    run_guard: WorkflowRunGuard | None = None

    async def _emit_spawn_stage(
        self,
        message: str,
        *,
        level: str = "info",
        category: str = "subagent",
    ) -> None:
        if self.event_queue is None or not self.message_id:
            return
        event = build_workflow_stage_event(
            self.message_id,
            message,
            level=level,
            category=category,
        )
        await self.event_queue.put(event)

    def _run(
        self,
        task_id: str,
        agent_type: str,
        task_description: str,
        readonly: bool = False,
        verification_mode: Literal["none", "adversarial", "auditor_blind", "multi_skeptic"] = "none",
        verifier_agent_type: str | None = None,
        max_verification_rounds: int = 2,
        complexity_tier: str | None = None,
    ) -> object:
        raise NotImplementedError("SpawnSubagentTool only supports async execution.")

    async def _arun(
        self,
        task_id: str,
        agent_type: str = "generalPurpose",
        task_description: str = "",
        readonly: bool = False,
        verification_mode: Literal["none", "adversarial", "auditor_blind", "multi_skeptic"] = "none",
        verifier_agent_type: str | None = None,
        max_verification_rounds: int = 2,
        complexity_tier: str | None = None,
    ) -> object:
        if self.cancel_token and getattr(self.cancel_token, "is_cancelled", False):
            return {
                "success": False,
                "task_id": task_id,
                "agent_type": agent_type,
                "result": None,
                "error": "Workflow cancelled by user.",
            }

        readonly = coerce_spawn_readonly(self.parent_agent, readonly)

        cache_params = SpawnCacheParams(
            agent_type=agent_type,
            task_description=task_description,
            readonly=readonly,
            verification_mode=verification_mode,
            verifier_agent_type=verifier_agent_type,
            max_verification_rounds=max_verification_rounds,
            complexity_tier=complexity_tier,
        )

        if self.store:
            cached = self.store.get_cached_result(
                self.workflow_id,
                task_id,
                expected=cache_params,
            )
            if cached:
                logger.info("DW cache hit: workflow=%s task=%s", self.workflow_id, task_id)
                await self._emit_spawn_stage(f"Using cached result for sub-agent `{task_id}`.")
                return cached

        guard_error: str | None = None
        if self.run_guard is not None:
            guard_error = await self.run_guard.acquire_spawn_slot()
        if guard_error:
            await self._emit_spawn_stage(
                f"Sub-agent `{task_id}` blocked: {guard_error}",
                level="warn",
            )
            return {
                "success": False,
                "task_id": task_id,
                "agent_type": agent_type,
                "result": None,
                "error": guard_error,
            }

        from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

        config = None
        if self.catalog:
            config = await cast("SubagentCatalog", self.catalog).resolve(agent_type)
        if not config:
            parent_resolver = getattr(self.parent_agent, "model_resolver", None)
            config = SubagentConfig(
                system_prompt="You are a sub-agent executing a specific task within a Dynamic Workflow.",
                max_spawn_depth=0,
                concurrency_limit=10,
                max_cost_usd=2.0,
                budget_tokens=200_000,
                model_resolver=parent_resolver,
            )

        verifier_fallback = config
        config = apply_readonly_to_config(config, readonly)
        config = enforce_spawn_policy_on_config(config)

        child_context = build_child_context_from_parent_agent(self.parent_agent)

        use_verification = verification_mode in {
            DwVerificationMode.ADVERSARIAL.value,
            DwVerificationMode.AUDITOR_BLIND.value,
            DwVerificationMode.MULTI_SKEPTIC.value,
        }
        stage_label = (
            f"Spawning sub-agent `{task_id}` ({agent_type}) with {verification_mode} verification..."
            if use_verification
            else f"Spawning sub-agent `{task_id}` ({agent_type})..."
        )
        await self._emit_spawn_stage(stage_label)

        try:
            try:
                with memory_isolation_scope():
                    if use_verification:
                        if not hasattr(self.parent_agent, "_subagent_manager"):
                            logger.warning(
                                "DW verification unavailable (no SubagentManager); falling back to direct spawn"
                            )
                            await self._emit_spawn_stage(
                                f"Sub-agent `{task_id}`: verification unavailable, using direct spawn.",
                                level="warn",
                            )
                            result = await cast("BaseAgent", self.parent_agent)._spawn_child(
                                task_id=task_id,
                                agent_type=agent_type,
                                task_description=task_description,
                                config=config,
                                context=child_context,
                                tool_registry_getter=cast(
                                    "Callable[[], list[BaseTool]]",
                                    self.tool_registry_getter,
                                ),
                                wait=True,
                                cancel_token=cast("CancellationToken | None", self.cancel_token),
                                complexity_tier=complexity_tier,
                            )
                        else:
                            manager = getattr(self.parent_agent, "_subagent_manager", None)
                            if manager is None:
                                raise ValueError("Parent agent missing _subagent_manager")
                            from myrm_agent_harness.agent.sub_agents.orchestrator import (
                                run_with_verification,
                            )
                            from myrm_agent_harness.agent.sub_agents.verifier_selection import resolve_verifier

                            registry_getter = cast("Callable[[], list[BaseTool]]", self.tool_registry_getter)
                            v_type, verifier_config = await resolve_verifier(
                                cast("SubagentCatalog | None", self.catalog),
                                verifier_agent_type,
                                agent_type,
                                verifier_fallback,
                                registry_getter(),
                            )

                            v_mode_param: Literal["adversarial", "auditor_blind", "multi_skeptic"] = (
                                "auditor_blind"
                                if verification_mode == DwVerificationMode.AUDITOR_BLIND.value
                                else (
                                    "multi_skeptic"
                                    if verification_mode == DwVerificationMode.MULTI_SKEPTIC.value
                                    else "adversarial"
                                )
                            )

                            result = await run_with_verification(
                                manager=manager,
                                worker_type=agent_type,
                                worker_config=config,
                                worker_task=task_description,
                                verifier_type=v_type,
                                verifier_config=verifier_config,
                                context=child_context,
                                tool_registry_getter=registry_getter,
                                max_rounds=max_verification_rounds,
                                cancel_token=cast("CancellationToken | None", self.cancel_token),
                                task_id=task_id,
                                verification_mode=v_mode_param,
                                complexity_tier=complexity_tier,
                            )
                    else:
                        result = await cast("BaseAgent", self.parent_agent)._spawn_child(
                            task_id=task_id,
                            agent_type=agent_type,
                            task_description=task_description,
                            config=config,
                            context=child_context,
                            tool_registry_getter=cast(
                                "Callable[[], list[BaseTool]]",
                                self.tool_registry_getter,
                            ),
                            wait=True,
                            cancel_token=cast("CancellationToken | None", self.cancel_token),
                            complexity_tier=complexity_tier,
                        )
            except Exception as e:
                logger.error("DW spawn failed: task=%s error=%s", task_id, e)
                await self._emit_spawn_stage(
                    f"Sub-agent `{task_id}` failed: {type(e).__name__}: {e}",
                    level="warn",
                )
                return {
                    "success": False,
                    "task_id": task_id,
                    "agent_type": agent_type,
                    "result": None,
                    "error": f"{type(e).__name__}: {e}",
                }
        finally:
            if self.run_guard is not None:
                self.run_guard.release_spawn_slot()

        final_result = _normalize_spawn_result(result, task_id=task_id, agent_type=agent_type)

        if self.store:
            self.store.save_result(
                workflow_id=self.workflow_id,
                task_id=task_id,
                agent_type=agent_type,
                task_description=task_description,
                result=final_result,
                spawn_params=cache_params,
            )
            # Sidecar journal mirror (best-effort workspace snapshot)
            ws_root = None
            if self.parent_agent:
                parent_ctx = getattr(self.parent_agent, "context", None)
                if parent_ctx is not None:
                    raw_ws = getattr(parent_ctx, "workspace_dir", None)
                    ws_root = coerce_filesystem_path(raw_ws)
            if ws_root is not None:
                journal_file = ws_root / ".myrm" / ".workflow-journal.jsonl"
                self.store.append_journal_entry(
                    journal_file,
                    workflow_id=self.workflow_id,
                    task_id=task_id,
                    agent_type=agent_type,
                    task_description=task_description,
                    result=final_result,
                    spawn_params=cache_params,
                )

        if final_result.get("success"):
            await self._emit_spawn_stage(f"Sub-agent `{task_id}` completed.")
        else:
            error_text = final_result.get("error") or "unknown error"
            await self._emit_spawn_stage(
                f"Sub-agent `{task_id}` failed: {error_text}",
                level="warn",
            )

        return final_result
