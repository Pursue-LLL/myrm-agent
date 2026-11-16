"""Key-value goal persistence over StorageProvider.

[INPUT]
- toolkits.storage.base::StorageProvider (POS: Storage protocol)
- .types::Goal, GoalStatus, GoalBudget (POS: Goal data types)
- .queue_index::GoalQueueIndex (POS: Per-session goal queue persistence)

[OUTPUT]
- GoalStorage: goal, session-index, stash and queue persistence; an unreadable session index reads as
  "no goal" and an unreadable queue as empty, each logged at most once per window per storage instance.
- StashRecord: persisted shape of a branch stash, as get_stash returns it.

[POS]
Handles persistence of Goal state using the framework's standard StorageProvider.
Ensures goal state survives process restarts and thread recovery.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, NotRequired, TypedDict

from .queue_index import GoalQueueIndex
from .types import Goal, GoalBudget, GoalStatus

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.storage.base import StorageProvider

logger = logging.getLogger(__name__)

_GOAL_NAMESPACE = "goals"

# Seconds between WARNINGs for one unreadable (index, session) on one GoalStorage instance. The goals
# panel polls every few seconds and the agent reads the active index on every model request, so a
# persistent fault would otherwise log on each read.
_INDEX_WARN_INTERVAL_S = 600.0


class _BudgetRecord(TypedDict, total=False):
    """Persisted shape of a GoalBudget; absent keys fall back to the dataclass defaults."""

    max_tokens: int | None
    max_usd: float | None
    max_time_seconds: int | None
    max_turns: int | None
    convergence_window: int | None
    loop_on_pause: bool
    max_loop_restarts: int


class _GoalRecord(TypedDict):
    """Persisted shape of a Goal: the identity and timestamp keys are always written, the rest default when absent."""

    goal_id: str
    session_id: str
    objective: str
    status: str
    created_at: str
    updated_at: str
    ui_summary: NotRequired[str]
    priority: NotRequired[int]
    auto_approve: NotRequired[bool]
    constraints: NotRequired[list[str]]
    protected_paths: NotRequired[list[str]]
    budget: NotRequired[_BudgetRecord | None]
    acceptance_criteria: NotRequired[list[dict[str, object]] | None]
    subgoals: NotRequired[list[dict[str, object]] | None]
    verification_retries: NotRequired[int]
    tokens_used: NotRequired[int]
    time_used_seconds: NotRequired[int]
    cost_usd: NotRequired[float]
    turns_used: NotRequired[int]
    no_progress_streak: NotRequired[int]
    loop_restarts: NotRequired[int]
    consecutive_judge_parse_failures: NotRequired[int]
    metadata: NotRequired[dict[str, object]]


class StashRecord(TypedDict):
    """Persisted shape of a branch stash; only the identity keys are always present.

    The progress state sits under `progress_state`; `planner_state` is the other key `restore_goal` accepts.
    """

    goal_id: str
    session_id: str
    progress_state: NotRequired[dict[str, object] | None]
    planner_state: NotRequired[dict[str, object] | None]
    chat_history: NotRequired[list[dict[str, object]] | None]
    stashed_at: NotRequired[str]


class GoalStorage:
    """Goal persistence over a StorageProvider."""

    def __init__(self, storage: StorageProvider) -> None:
        self._storage = storage
        self._queue = GoalQueueIndex(storage, key_prefix=f"{_GOAL_NAMESPACE}_queue")
        # (index, session_id) -> monotonic time of the last WARNING for that unreadable index.
        self._index_warned_at: dict[tuple[str, str], float] = {}

    async def save_goal(self, goal: Goal) -> None:
        """Save goal state to storage."""
        data = self._serialize_goal(goal)
        await self._storage.write(
            key=f"{_GOAL_NAMESPACE}/{goal.goal_id}",
            content=json.dumps(data).encode("utf-8"),
        )

        # Maintain session -> active goal index
        if goal.status == GoalStatus.ACTIVE:
            await self._storage.write(
                key=f"{_GOAL_NAMESPACE}_active/{goal.session_id}",
                content=goal.goal_id.encode("utf-8"),
            )
        else:
            # If not active, check if it was the active one and remove index
            active_id = await self.get_active_goal_id(goal.session_id)
            if active_id == goal.goal_id:
                await self._storage.delete(key=f"{_GOAL_NAMESPACE}_active/{goal.session_id}")

        # Always maintain latest goal index
        await self._storage.write(
            key=f"{_GOAL_NAMESPACE}_latest/{goal.session_id}",
            content=goal.goal_id.encode("utf-8"),
        )

    async def get_goal(self, goal_id: str) -> Goal | None:
        """Retrieve goal by ID."""
        try:
            raw = await self._storage.read(key=f"{_GOAL_NAMESPACE}/{goal_id}")
            if not raw:
                return None

            data = json.loads(raw.decode("utf-8"))
            return self._deserialize_goal(data)
        except Exception as e:
            logger.error("Failed to deserialize goal %s: %s", goal_id, e)
            return None

    async def get_active_goal_id(self, session_id: str) -> str | None:
        """Get the ID of the currently active goal for a session."""
        return await self._read_index("active", session_id)

    async def list_active_sessions(self) -> list[str]:
        """Return all session_ids that currently have an ACTIVE goal."""
        prefix = f"{_GOAL_NAMESPACE}_active/"
        try:
            keys = await self._storage.list(prefix=prefix)
            return [k.removeprefix(prefix) for k in keys if k.startswith(prefix)]
        except Exception:
            logger.warning("Failed to enumerate active goal sessions", exc_info=True)
            return []

    async def list_latest_goal_sessions(self) -> list[str]:
        """Return session_ids that have a latest goal index entry."""
        prefix = f"{_GOAL_NAMESPACE}_latest/"
        try:
            keys = await self._storage.list(prefix=prefix)
            return [k.removeprefix(prefix) for k in keys if k.startswith(prefix)]
        except Exception:
            logger.warning("Failed to enumerate latest goal sessions", exc_info=True)
            return []

    async def get_latest_goal_id(self, session_id: str) -> str | None:
        """Get the ID of the latest goal for a session."""
        return await self._read_index("latest", session_id)

    async def _read_index(self, index: str, session_id: str) -> str | None:
        """Read a per-session goal-id index; a missing key means the session has no such goal.

        Any other failure also reads as "no goal" so a damaged index never breaks a caller, but it is
        reported here: callers cannot tell "no goal" from "unreadable", so their own failure handling
        never sees an error that this method absorbed.
        """
        try:
            raw = await self._storage.read(key=f"{_GOAL_NAMESPACE}_{index}/{session_id}")
            return raw.decode("utf-8") if raw else None
        except FileNotFoundError:
            return None
        except Exception as exc:
            self._report_index_failure(index, session_id, exc)
            return None

    def _report_index_failure(self, index: str, session_id: str, exc: Exception) -> None:
        """Log an unreadable index at WARNING once per window (per storage instance) and at DEBUG after that.

        The session id comes from request paths and the exception text from the storage backend, so
        both are logged with %r to keep a hostile id from forging log lines.
        """
        now = time.monotonic()
        key = (index, session_id)
        last = self._index_warned_at.get(key)
        first_in_window = last is None or now - last >= _INDEX_WARN_INTERVAL_S
        if first_in_window:
            self._index_warned_at[key] = now
        logger.log(
            logging.WARNING if first_in_window else logging.DEBUG,
            "Goal %s index for session %r could not be read (%s): %.300r",
            index,
            session_id,
            type(exc).__name__,
            str(exc),
        )

    def _serialize_goal(self, goal: Goal) -> dict[str, object]:
        budget_dict = None
        if goal.budget:
            budget_dict = {
                "max_tokens": goal.budget.max_tokens,
                "max_usd": goal.budget.max_usd,
                "max_time_seconds": goal.budget.max_time_seconds,
                "max_turns": goal.budget.max_turns,
                "convergence_window": goal.budget.convergence_window,
                "loop_on_pause": goal.budget.loop_on_pause,
                "max_loop_restarts": goal.budget.max_loop_restarts,
            }

        return {
            "goal_id": goal.goal_id,
            "session_id": goal.session_id,
            "objective": goal.objective,
            "status": goal.status.value,
            "ui_summary": goal.ui_summary,
            "priority": goal.priority,
            "auto_approve": goal.auto_approve,
            "constraints": goal.constraints,
            "protected_paths": goal.protected_paths,
            "budget": budget_dict,
            "acceptance_criteria": goal.acceptance_criteria,
            "subgoals": goal.subgoals,
            "verification_retries": goal.verification_retries,
            "tokens_used": goal.tokens_used,
            "time_used_seconds": goal.time_used_seconds,
            "cost_usd": goal.cost_usd,
            "turns_used": goal.turns_used,
            "no_progress_streak": goal.no_progress_streak,
            "loop_restarts": goal.loop_restarts,
            "consecutive_judge_parse_failures": goal.consecutive_judge_parse_failures,
            "created_at": goal.created_at.isoformat(),
            "updated_at": goal.updated_at.isoformat(),
            "metadata": goal.metadata,
        }

    def _deserialize_goal(self, data: _GoalRecord) -> Goal:
        budget = None
        b_data = data.get("budget")
        if b_data:
            budget = GoalBudget(
                max_tokens=b_data.get("max_tokens"),
                max_usd=b_data.get("max_usd"),
                max_time_seconds=b_data.get("max_time_seconds"),
                max_turns=b_data.get("max_turns"),
                convergence_window=b_data.get("convergence_window"),
                loop_on_pause=b_data.get("loop_on_pause", False),
                max_loop_restarts=b_data.get("max_loop_restarts", 10),
            )

        return Goal(
            goal_id=data["goal_id"],
            session_id=data["session_id"],
            objective=data["objective"],
            status=GoalStatus(data["status"]),
            ui_summary=data.get("ui_summary", ""),
            priority=data.get("priority", 0),
            auto_approve=data.get("auto_approve", False),
            constraints=data.get("constraints", []),
            protected_paths=data.get("protected_paths", []),
            budget=budget,
            acceptance_criteria=data.get("acceptance_criteria", []),
            subgoals=data.get("subgoals", []),
            verification_retries=data.get("verification_retries", 0),
            tokens_used=data.get("tokens_used", 0),
            time_used_seconds=data.get("time_used_seconds", 0),
            cost_usd=data.get("cost_usd", 0.0),
            turns_used=data.get("turns_used", 0),
            no_progress_streak=data.get("no_progress_streak", 0),
            loop_restarts=data.get("loop_restarts", 0),
            consecutive_judge_parse_failures=data.get("consecutive_judge_parse_failures", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
        )

    async def save_stash(
        self,
        branch_name: str,
        session_id: str,
        goal_id: str,
        progress_state: dict[str, object] | None,
        chat_history: list[dict[str, object]] | None,
    ) -> None:
        """Save a stashed goal state for a branch."""

        data: StashRecord = {
            "session_id": session_id,
            "goal_id": goal_id,
            "progress_state": progress_state,
            "chat_history": chat_history,
            "stashed_at": datetime.now().isoformat(),
        }
        await self._storage.write(
            key=f"{_GOAL_NAMESPACE}_stash/{session_id}/{branch_name}",
            content=json.dumps(data).encode("utf-8"),
        )

    async def get_stash(self, session_id: str, branch_name: str) -> StashRecord | None:
        """Retrieve a stashed goal state for a branch."""

        try:
            raw = await self._storage.read(key=f"{_GOAL_NAMESPACE}_stash/{session_id}/{branch_name}")
            if not raw:
                return None
            stash: StashRecord = json.loads(raw.decode("utf-8"))
            return stash
        except Exception as e:
            logger.debug("Failed to read stash for branch %s: %s", branch_name, e)
            return None

    async def delete_stash(self, session_id: str, branch_name: str) -> None:
        """Delete stashed goal state for a branch."""
        try:
            await self._storage.delete(key=f"{_GOAL_NAMESPACE}_stash/{session_id}/{branch_name}")
        except Exception as e:
            logger.error("Failed to delete stash for branch %s: %s", branch_name, e)

    # --- Queue index operations (see queue_index.py) ---

    async def add_to_queue(self, goal: Goal) -> None:
        """Add a goal to the session queue index."""
        await self._queue.add(goal)

    async def get_queue(self, session_id: str) -> list[dict[str, object]]:
        """Get the ordered queue entries for a session; a queue that cannot be read reads as empty and is logged.

        The changes below raise instead: they write the queue back, and an empty stand-in would replace it.
        """
        try:
            return await self._queue.read(session_id)
        except Exception as exc:
            self._report_index_failure("queue", session_id, exc)
            return []

    async def remove_from_queue(self, session_id: str, goal_id: str) -> None:
        """Remove a goal from the queue index."""
        await self._queue.remove(session_id, goal_id)

    async def reorder_queue(self, session_id: str, ordered_goal_ids: list[str]) -> None:
        """Reorder queue by assigning priorities based on the provided order."""
        await self._queue.reorder(session_id, ordered_goal_ids)
