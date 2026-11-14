"""GeneralAgent resource lifecycle — per-turn release and full teardown.

[INPUT]
- app.services.external_agents.runtime_pool_registry::close_runtime_pool_bounded, get_chat_runtime_pool_registry (POS: the pool a chat shares across turns, and the bounded close of one an agent built itself)
- myrm_agent_harness.runtime.context.offload::cleanup_session_context_files (POS: removes the context files a session offloaded through its executor)
- app.config.settings::get_settings (POS: harness directory a recorded session video path is made relative to)

[OUTPUT]
- AgentLifecycleMixin: release_pooled_session (after each turn), close (when the agent is dropped), session recording capture

[POS]
GeneralAgent teardown. A pooled agent is reused across turns of a chat, so release_pooled_session frees only what a
turn owns while close frees everything, including the browser, the executor and the harness SkillAgent. Every release is
guarded on its own: one that fails is logged and never keeps the next from running.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.api import SkillAgent
    from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
    from myrm_agent_harness.toolkits.acp.types import DelegationPool
    from myrm_agent_harness.toolkits.browser import BrowserSession
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor

logger = logging.getLogger(__name__)


class AgentLifecycleMixin:
    """Releases what a GeneralAgent holds."""

    if TYPE_CHECKING:
        agent: SkillAgent | None
        _runtime_pool: DelegationPool | None
        _runtime_pool_scope_id: str | None
        _runtime_pool_from_registry: bool
        _owned_runtime_pool: RuntimePool | None
        _executor: CodeExecutor | None
        _current_chat_id: str | None
        _browser_session: BrowserSession | None

    async def _release_runtime_pool(self) -> None:
        """Release the external-agent pool: registry-owned pools stay cached, a pool this agent built itself is closed."""
        if self._runtime_pool is None:
            return
        try:
            from app.services.external_agents.runtime_pool_registry import (
                close_runtime_pool_bounded,
                get_chat_runtime_pool_registry,
            )

            scope_id = (self._runtime_pool_scope_id or "").strip()
            if self._runtime_pool_from_registry and scope_id:
                await get_chat_runtime_pool_registry().release(scope_id)
            elif self._owned_runtime_pool is not None:
                await close_runtime_pool_bounded(self._owned_runtime_pool, scope="ephemeral")
        except Exception as e:
            logger.warning("RuntimePool release failed: %s", e)
        finally:
            self._runtime_pool = None
            self._owned_runtime_pool = None

    async def _cleanup_context_files(self) -> None:
        """Remove the context files this chat offloaded through its executor; a failure is logged, never raised."""
        if self._executor is None or self._current_chat_id is None:
            return
        try:
            from myrm_agent_harness.runtime.context.offload import cleanup_session_context_files

            await cleanup_session_context_files(self._current_chat_id, self._executor)
        except Exception as e:
            logger.warning("Context cleanup failed for chat_id=%s: %s", self._current_chat_id, e)

    async def release_pooled_session(self) -> None:
        """Release per-turn server resources without closing pooled SkillAgent/Browser."""
        await self._release_runtime_pool()
        await self._cleanup_context_files()

    async def close(self) -> None:
        """Close Agent and release resources."""
        await self._release_runtime_pool()

        if self._browser_session is not None:
            try:
                await self._browser_session.close()
                self._capture_session_recording_info()
            except Exception as e:
                logger.warning("BrowserSession close failed: %s", e)
            finally:
                self._browser_session = None

        if self._executor is not None:
            await self._cleanup_context_files()
            try:
                await self._executor.close()
            except Exception as e:
                logger.warning("Executor close failed for chat_id=%s: %s", self._current_chat_id, e)
            finally:
                self._executor = None

        if self.agent is not None:
            try:
                await self.agent.close()
                logger.info("Agent resources fully released")
            except Exception as e:
                logger.warning("Agent close failed: %s", e)
            finally:
                self.agent = None

    def _capture_session_recording_info(self) -> None:
        """Store session recording metadata for SSE delivery after close."""
        try:
            session = self._browser_session
            if session is None:
                return
            obs = getattr(session, "_observability", None)
            if obs is None or not obs.recording_enabled:
                return
            video_path = obs.video_path
            if video_path is None or not Path(video_path).exists():
                return

            from app.config.settings import get_settings

            harness_dir = get_settings().database.harness_dir
            relative_path = str(video_path)
            if relative_path.startswith(harness_dir):
                relative_path = relative_path[len(harness_dir) :]
                if relative_path.startswith("/"):
                    relative_path = relative_path[1:]

            self._session_recording_info: dict[str, str] = {
                "filename": Path(video_path).name,
                "preview_url": f"/api/v1/files/vault/render?filepath={relative_path}&workspace={harness_dir}",
                "content_type": "video/webm",
            }
            logger.info("Session recording captured: %s", video_path)
        except Exception as e:
            logger.debug("Session recording capture skipped: %s", e)
