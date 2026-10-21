"""Server service layer for Browser TaskSpaces lifecycle, takeover, and observability.

[INPUT]
- myrm_agent_harness.toolkits.browser.spaces::BrowserTaskSpace (POS: 任务空间实体)
- myrm_agent_harness.toolkits.browser.spaces::HarnessTaskSpaceManager (POS: Harness空间管理引擎)

[OUTPUT]
- TaskSpaceInfo: 任务空间元数据模型
- BrowserTaskSpaceService: 任务空间服务业务实现
- get_task_space_service: 服务单例获取工厂

[POS]
浏览器任务空间服务业务实现。提供多空间生命周期、状态追踪、人工接管与定时清理服务。
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Literal

from myrm_agent_harness.toolkits.browser.spaces import (
    BrowserTaskSpace,
    HarnessTaskSpaceManager,
)
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SpaceStatus = Literal["idle", "running", "takeover", "completed", "error"]


class TaskSpaceInfo(BaseModel):
    """Observable metadata model for a single browser task space."""

    space_id: str
    name: str
    status: SpaceStatus = "idle"
    chat_id: str | None = None
    created_at: float
    last_accessed_at: float
    idle_seconds: float
    active_pages: int = 0
    takeover_active: bool = False
    current_url: str = ""
    current_title: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class TaskSpaceService:
    """Orchestrates server-side browser task space states, takeovers, and auto-pruning."""

    def __init__(
        self,
        manager: HarnessTaskSpaceManager | None = None,
        max_active_spaces: int = 5,
        default_idle_ttl_seconds: float = 900.0,
    ) -> None:
        if manager is not None:
            self.manager = manager
        else:
            self.manager = HarnessTaskSpaceManager(
                max_active_spaces=max_active_spaces,
                default_idle_ttl_seconds=default_idle_ttl_seconds,
            )
        self._space_states: dict[str, dict[str, object]] = {}

    async def list_spaces(self) -> list[TaskSpaceInfo]:
        """List all active task spaces with real-time runtime state."""
        harness_spaces = self.manager.list_spaces()
        results: list[TaskSpaceInfo] = []

        for space in harness_spaces:
            info = await self._build_space_info(space)
            results.append(info)

        return results

    async def get_or_create_space(
        self,
        space_id: str,
        name: str | None = None,
        chat_id: str | None = None,
    ) -> TaskSpaceInfo:
        """Allocate or access a task space and update its ownership mapping."""
        # Optional factory hooks can be injected when integrating with live GlobalBrowserPool
        space = await self.manager.get_or_create_space(space_id=space_id, name=name)
        state = self._space_states.setdefault(
            space_id,
            {
                "status": "idle",
                "chat_id": chat_id,
                "takeover_active": False,
                "current_url": "",
                "current_title": "",
            },
        )
        if chat_id is not None:
            state["chat_id"] = chat_id

        return await self._build_space_info(space)

    async def close_space(self, space_id: str) -> bool:
        """Close and evict a space and its server state."""
        closed = await self.manager.close_space(space_id)
        self._space_states.pop(space_id, None)
        return closed

    async def set_takeover(self, space_id: str, enabled: bool) -> TaskSpaceInfo:
        """Toggle human-takeover mode for the given space."""
        space = self.manager.get_space(space_id)
        if space is None:
            raise KeyError(f"TaskSpace '{space_id}' not found")

        state = self._space_states.setdefault(space_id, {})
        state["takeover_active"] = enabled
        state["status"] = "takeover" if enabled else "idle"
        space.touch()

        # Hard stop / resume physical browser session
        if enabled:
            await space.pause_for_takeover()
        else:
            await space.resume_from_takeover()

        logger.info("TaskSpace '%s' human takeover set to: %s", space_id, enabled)
        return await self._build_space_info(space)

    async def get_space_snapshot(self, space_id: str) -> dict[str, object]:
        """Capture live screenshot and DOM metadata for WebUI preview."""
        space = self.manager.get_space(space_id)
        if space is None:
            raise KeyError(f"TaskSpace '{space_id}' not found")

        space.touch()
        # Fallback payload if no real browser context is active yet
        state = self._space_states.get(space_id, {})
        current_url = str(state.get("current_url", "about:blank"))
        current_title = str(state.get("current_title", space.name))

        screenshot_base64 = ""
        if space.context is not None and space.context.pages:
            try:
                page = space.context.pages[0]
                current_url = page.url
                current_title = await page.title()
                raw_bytes = await page.screenshot(type="jpeg", quality=60)
                import base64

                screenshot_base64 = base64.b64encode(raw_bytes).decode("ascii")
            except Exception as exc:  # noqa: S110
                logger.debug("Failed to capture snapshot for space '%s': %s", space_id, exc)

        return {
            "space_id": space_id,
            "url": current_url,
            "title": current_title,
            "screenshot_jpeg_b64": screenshot_base64,
            "takeover_active": bool(state.get("takeover_active", False)),
            "timestamp": time.time(),
        }

    async def prune_idle(self, max_idle_seconds: float | None = None) -> int:
        """Prune idle spaces and purge orphan server metadata."""
        pruned_count = await self.manager.prune_idle_spaces(max_idle_seconds)
        active_ids = {s.space_id for s in self.manager.list_spaces()}
        stale_keys = [k for k in self._space_states if k not in active_ids]
        for k in stale_keys:
            self._space_states.pop(k, None)
        return pruned_count

    async def prune_idle_spaces(self, max_idle_seconds: float | None = None) -> int:
        """Alias for prune_idle to provide unified interface with underlying manager."""
        return await self.prune_idle(max_idle_seconds)

    async def _build_space_info(self, space: BrowserTaskSpace) -> TaskSpaceInfo:
        state = self._space_states.get(space.space_id, {})
        now = time.time()
        active_pages = 0
        current_url = str(state.get("current_url", ""))
        current_title = str(state.get("current_title", ""))

        if space.context is not None:
            try:
                pages = space.context.pages
                active_pages = len(pages)
                if pages:
                    current_url = pages[0].url
                    current_title = await pages[0].title()
            except Exception:
                pass

        status_val = str(state.get("status", "idle"))
        if status_val not in ("idle", "running", "takeover", "completed", "error"):
            status_val = "idle"

        return TaskSpaceInfo(
            space_id=space.space_id,
            name=space.name,
            status=status_val,  # type: ignore[arg-type]
            chat_id=state.get("chat_id") if isinstance(state.get("chat_id"), str) else None,
            created_at=space.created_at,
            last_accessed_at=space.last_accessed_at,
            idle_seconds=round(now - space.last_accessed_at, 1),
            active_pages=active_pages,
            takeover_active=bool(state.get("takeover_active", False)),
            current_url=current_url,
            current_title=current_title,
            metadata=space.metadata,
        )


_GLOBAL_TASK_SPACE_SERVICE: TaskSpaceService | None = None


def get_task_space_service() -> TaskSpaceService:
    """Return the global TaskSpaceService singleton."""
    global _GLOBAL_TASK_SPACE_SERVICE
    if _GLOBAL_TASK_SPACE_SERVICE is None:
        _GLOBAL_TASK_SPACE_SERVICE = TaskSpaceService()
    return _GLOBAL_TASK_SPACE_SERVICE


def _reset_task_space_service_for_test() -> None:
    """Reset singleton for clean isolated unit tests."""
    global _GLOBAL_TASK_SPACE_SERVICE
    _GLOBAL_TASK_SPACE_SERVICE = None
