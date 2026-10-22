"""Goal Registry — 会话级 Goal 句柄全局注册表.

[INPUT]
- myrm_agent_harness.agent.goals.protocols::GoalProvider (POS: GoalProvider protocol)
- myrm_agent_harness.agent.goals.manager::GoalManager (POS: Implementation of GoalProvider)
- app.services.kanban.service::KanbanService (POS: Kanban business service facade; domain logic lives in sibling orchestrator modules.)
- app.services.event.app_event_bus::get_event_bus (POS: 应用级事件总线)
- app.services.agent.platform_config::load_platform_llm (POS: WebUI 默认 wire-aware 对话模型)
- app.database.models.artifact::Artifact (POS: Provides enterprise artifact models with tamper-evident tracking.)
- app.core.utils.chat_utils::extract_answer_text (POS: LangChain 响应文本提取，含 reasoning 回退)
- app.core.utils.chat_utils::parse_judge_json (POS: judge JSON 解析)

[OUTPUT]
- GoalRegistry: 全局注册表，通过 session_id 管理运行中的 GoalProvider
- ServerGoalManager: 扩展 harness GoalManager，提供 semantic judge 与 Goal 完成时的会话交付物汇总

[POS]
会话级 Goal 注册表。使 HTTP API 能够通过 session_id 定位正在运行的
Agent 会话的 GoalProvider，从而在运行时控制 Goal 状态（暂停/恢复）。
与 SteeringRegistry 和 CancellationRegistry 形成对称设计。
"""

import logging
import threading
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.goals.manager import GoalManager

from app.core.utils.chat_utils import extract_answer_text, parse_judge_json

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.protocols import GoalProvider
    from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
    from myrm_agent_harness.agent.goals.verification.base import VerificationResult
    from myrm_agent_harness.toolkits.storage.base import StorageProvider

logger = logging.getLogger(__name__)


def _screen_is_capturable() -> bool:
    """False while the session is locked or asleep: a capture would only show the lock screen.

    Unlocking is the unattended watcher's decision (it alone checks presence and the
    unlock lease); the evaluator falls back to a text-only verdict instead of unlocking.
    """
    from myrm_agent_harness.api.security import ScreenLockState, get_default_screen_detector

    return get_default_screen_detector().get_state() not in (ScreenLockState.LOCKED, ScreenLockState.SLEEPING)


async def _collect_session_deliverables(session_id: str) -> list[dict[str, str]]:
    """Collect all artifacts produced in a chat session for goal deliverable aggregation."""
    from sqlalchemy import Result, select

    from app.database.connection import get_session
    from app.database.models.artifact import Artifact

    async with get_session() as db:
        result: Result[tuple[str, str]] = await db.execute(
            select(Artifact.id, Artifact.name)
            .where(Artifact.chat_id == session_id, Artifact.is_deleted.is_(False))
            .order_by(Artifact.created_at.asc())
        )
        rows = result.all()
        return [{"id": row.id, "filename": row.name} for row in rows]


class ServerGoalManager(GoalManager):
    """Server-side GoalManager that implements boundary methods like semantic evaluation."""

    def __init__(self, storage_provider: "StorageProvider", session_id: str | None = None) -> None:
        super().__init__(storage_provider)
        self.session_id = session_id

    async def update_status(self, goal_id: str, status: "GoalStatus") -> "Goal":
        goal = await super().update_status(goal_id, status)

        from myrm_agent_harness.agent.goals.types import GoalStatus

        if status == GoalStatus.COMPLETE:
            await self._collect_deliverables_on_completion(goal)

        return goal

    async def _collect_deliverables_on_completion(self, goal: "Goal") -> None:
        """Collect session deliverables when goal completes."""
        if not self.session_id:
            return
        try:
            deliverables = await _collect_session_deliverables(self.session_id)
            if deliverables:
                goal.metadata["deliverables"] = deliverables
                await self._storage.save_goal(goal)
        except Exception as exc:
            logger.warning("Failed to collect deliverables for goal %s: %s", goal.goal_id, exc)

    async def evaluate_semantic(
        self, criteria: str, content: str, context_messages: list[object] | None = None
    ) -> "VerificationResult":
        from langchain_core.messages import HumanMessage, SystemMessage
        from myrm_agent_harness.agent.goals.verification.base import VerificationResult

        from app.services.agent.platform_config import load_platform_llm

        try:
            llm = await load_platform_llm(streaming=False, temperature=0.0)

            requires_vision = False
            if context_messages:
                for msg in context_messages:
                    if getattr(msg, "type", "") == "tool" and getattr(msg, "name", "") in (
                        "browser_interact_tool",
                        "browser_snapshot_tool",
                        "browser_extract_tool",
                        "browser_navigate_tool",
                        "browser_execute_script_tool",
                        "desktop_snapshot_tool",
                        "desktop_interact_tool",
                        "desktop_vision_tool",
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
                        logger.warning(
                            "Failed to extract browser screenshot for semantic evaluation: %s",
                            e,
                        )

                if not screenshot_b64:
                    desktop_session = gateway.get_active_desktop_session(self.session_id)
                    if desktop_session is not None and _screen_is_capturable():
                        try:
                            action_result = await desktop_session.take_screenshot()
                            if action_result and action_result.success and action_result.screenshot_base64:
                                screenshot_b64 = action_result.screenshot_base64
                        except Exception as e:
                            logger.warning(
                                "Failed to extract desktop screenshot for semantic evaluation: %s",
                                e,
                            )

            lc_messages: list[SystemMessage | HumanMessage] = [SystemMessage(content=criteria)]

            if screenshot_b64:
                lc_messages.append(
                    HumanMessage(
                        content=[
                            {"type": "text", "text": content},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}"},
                            },
                        ]
                    )
                )
                logger.info("Multimodal Evaluator triggered: Injected visual proof (screenshot) for goal evaluation.")
            else:
                lc_messages.append(HumanMessage(content=content))

            response = await llm.ainvoke(lc_messages)
            raw = extract_answer_text(response).strip()

            parsed = parse_judge_json(raw)

            if parsed is not None:
                done = parsed.get("done", False)
                wait = bool(parsed.get("wait", False))
                reason = str(parsed.get("reason", ""))
                if done and not wait:
                    return VerificationResult(passed=True, reason=reason)
                return VerificationResult(passed=False, reason=reason, wait=wait)

            # Judge output was not parseable as JSON — signal parse_failed
            # so the harness can track consecutive failures and auto-pause.
            lower = raw.lower()
            if lower.startswith("pass") or '"done": true' in lower or '"done":true' in lower:
                return VerificationResult(passed=True, reason=raw)
            return VerificationResult(passed=False, reason=raw, parse_failed=True)

        except Exception as e:
            logger.error("Semantic evaluation failed: %s", e)
            return VerificationResult(passed=False, reason="Server evaluation failed", error_logs=str(e))


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
    def session_ids(cls) -> list[str]:
        """Session ids that currently have a live provider."""
        with cls._lock:
            return list(cls._providers)

    @classmethod
    def unregister(cls, session_id: str) -> None:
        """Remove a provider when the agent stream ends."""
        with cls._lock:
            if cls._providers.pop(session_id, None):
                logger.debug("Unregistered goal provider: session_id=%s", session_id)
