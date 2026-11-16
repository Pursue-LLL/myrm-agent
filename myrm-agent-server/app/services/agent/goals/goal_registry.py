"""Goal Registry — 会话级 Goal 句柄全局注册表.

[INPUT]
- myrm_agent_harness.agent.goals.protocols::GoalProvider (POS: GoalProvider protocol)
- myrm_agent_harness.agent.goals.manager::GoalManager (POS: Implementation of GoalProvider)
- app.services.agent.platform_config::load_platform_llm (POS: WebUI 默认 wire-aware 对话模型)
- app.database.models.artifact::Artifact (POS: Provides enterprise artifact models with tamper-evident tracking.)
- app.core.utils.chat_utils::extract_answer_text (POS: LangChain 响应文本提取，含 reasoning 回退)
- app.core.utils.chat_utils::parse_judge_json (POS: judge JSON 解析)

[OUTPUT]
- GoalRegistry: 全局注册表，通过 session_id 管理运行中回合的 GoalProvider；register 为一个回合新建 provider 并登记（同会话的旧条目被替换），unregister 带着该 provider 归还（条目已是别的回合的则不动）；turn_provider 为服务端自启的回合登记句柄并在回合结束时按句柄归还；resolve_provider 为 HTTP API、IM 命令与回合之外的服务端逻辑取 provider（已注册的，否则一个不注册的、绑定该会话的 ServerGoalManager，直读存储）；has_active_goal 读存储真值（与 provider 是否注册无关）
- ServerGoalManager: 扩展 harness GoalManager，提供 semantic judge 与 Goal 完成时的会话交付物汇总

[POS]
会话级 Goal 注册表。使 HTTP API 能够通过 session_id 定位正在运行的
Agent 会话的 GoalProvider，从而在运行时控制 Goal 状态（暂停/恢复）；
注册只属于运行中的回合，并归登记它的那个回合：聊天回合在编排器登记、流收尾时按自己的 provider 归还，服务端自启的回合（无人值守目标续跑）经 turn_provider 同样随回合登记与归还。
网关在回合收尾结束之前就归还会话，服务端可在这段时间内启动同一会话的下一个回合，所以较早回合的归还只动自己的条目。
读写 Goal 状态（HTTP API、IM 命令、回调与恢复逻辑）一律走 resolve_provider，回合之间无注册 provider 时它退回存储直读。
与 SteeringRegistry 和 CancellationRegistry 形成对称设计。
"""

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
        result: Result[str, str] = await db.execute(
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
    """Global registry of the goal providers of running turns, keyed by session_id.

    Enables the goal API endpoints to locate and manage goals for
    running agent sessions. A registration belongs to the turn that made it: only that turn's own provider gives
    it back, so a turn that ends late cannot drop the registration of the turn that started after it.

    Thread-safe for concurrent access from multiple endpoints.
    """

    _lock = threading.Lock()
    _providers: dict[str, "GoalProvider"] = {}

    @classmethod
    def register(cls, session_id: str) -> "GoalProvider":
        """Register a new provider as the live handle of the session's turn, replacing the session's earlier entry.

        The turn keeps the returned provider while it runs and gives it back with `unregister` when it ends. Its
        in-memory state (suppression flags) is the turn's own, and no other turn shares it. Code that runs outside
        a turn reads and changes goals through `resolve_provider`, which registers nothing.
        """
        from app.platform_utils import get_storage_provider

        provider = ServerGoalManager(get_storage_provider(), session_id=session_id)
        with cls._lock:
            cls._providers[session_id] = provider
        logger.debug("Registered goal provider: session_id=%s", session_id)
        return provider

    @classmethod
    @asynccontextmanager
    async def turn_provider(cls, session_id: str) -> AsyncIterator["GoalProvider"]:
        """The session's provider for a turn the server starts itself: registered while the turn runs, released when it ends.

        A chat turn registers its provider at setup and gives it back when its stream finalizes. A turn started
        without a chat stream (the unattended goal turn) holds the provider through this context instead, so its
        agent and its goal callbacks share one live handle, and nothing it registered stays registered after it,
        however it ends.
        """
        provider = cls.register(session_id)
        try:
            yield provider
        finally:
            cls.unregister(session_id, provider)

    @classmethod
    def get_provider(cls, session_id: str) -> "GoalProvider | None":
        """The live provider of the session's running turn, None between turns; to read or change goals use `resolve_provider`."""
        with cls._lock:
            return cls._providers.get(session_id)

    @classmethod
    def resolve_provider(cls, session_id: str) -> "GoalProvider":
        """The session's registered provider, else a manager over the same storage that is not registered.

        Providers are registered only while a turn runs, yet the HTTP API, the IM commands, the agent builder (an IM,
        cron or wake turn registers none) and the server's own logic outside a turn (callbacks the harness fires as a
        turn winds down, background-job and timer handlers, recovery) work on a session between turns too, and its
        goals live in storage. The stand-in is a `ServerGoalManager` of the session, so completing a goal through it
        collects the deliverables like a turn's provider does. It is never registered: a registered provider is the
        live handle of a running session, and `GET /goals/active` lists every registered session.
        """
        provider = cls.get_provider(session_id)
        return provider if provider is not None else cls._storage_manager(session_id)

    @classmethod
    async def has_active_goal(cls, session_id: str) -> bool:
        """Whether storage holds an ACTIVE goal for the session, whether or not a provider is registered.

        An active goal mounts complete_goal_tool and planning when an agent is built, so execution-cache
        keys depend on it. Providers are registered only while a turn runs; reading the provider map
        would give a different answer between turns than during one.
        """
        return await cls._storage_manager(session_id).get_active_goal(session_id) is not None

    @staticmethod
    def _storage_manager(session_id: str) -> ServerGoalManager:
        """An unregistered manager of the session over the platform storage, holding none of a running turn's state."""
        from app.platform_utils import get_storage_provider

        return ServerGoalManager(get_storage_provider(), session_id=session_id)

    @classmethod
    def session_ids(cls) -> list[str]:
        """Session ids that currently have a live provider."""
        with cls._lock:
            return list(cls._providers)

    @classmethod
    def unregister(cls, session_id: str, provider: "GoalProvider") -> None:
        """Give back the registration of `provider`; an entry that is another turn's provider stays.

        The gateway gives a chat turn's session back before the turn's teardown ends, so the server can start the
        session's next turn in between. The late teardown of the earlier turn must not drop the registration of the
        turn that runs.
        """
        with cls._lock:
            if cls._providers.get(session_id) is not provider:
                return
            del cls._providers[session_id]
        logger.debug("Unregistered goal provider: session_id=%s", session_id)
