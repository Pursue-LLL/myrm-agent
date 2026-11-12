"""Tabs, CDP clients and sessions of the relay: which tab is attached, who has been told, how events fan out.

[INPUT]
- cdp_relay.extension_link::ExtensionLink (POS: command channel to the extension)
- cdp_relay.models::CdpClient, AttachedTab, TabState (POS: relay state records)
- cdp_relay.protocol::RelayTabInfo, BROWSER_CONTEXT_ID (POS: relay wire types)

[OUTPUT]
- TargetRegistry: tab mirror, attach/detach/close, Target.* announcements, session lookup

[POS]
Middle layer of the relay bridge: turns the extension's tab list and debugger events into the
Target.attachedToTarget / detachedFromTarget / session-routed events Playwright expects.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Coroutine

from .extension_link import ExtensionLink
from .models import AttachedTab, CdpClient, TabState
from .protocol import BROWSER_CONTEXT_ID, RelayTabInfo

logger = logging.getLogger(__name__)


class TargetRegistry(ExtensionLink):
    """Mirrors the extension's tabs and tracks which of them are attached and announced to which CDP clients."""

    def __init__(self) -> None:
        super().__init__()
        self._tabs: dict[int, TabState] = {}
        self._clients: list[CdpClient] = []
        self._browser_sessions: dict[str, CdpClient] = {}
        self._child_sessions: dict[str, int] = {}
        self._auxiliary_tab_sessions: dict[str, tuple[int, str, CdpClient]] = {}
        self._next_session_ordinal = 1
        self._background_tasks: set[asyncio.Task[None]] = set()

    def sync_tabs(self, tabs: list[RelayTabInfo]) -> None:
        next_ids = {tab.tab_id for tab in tabs}
        for tab_id in list(self._tabs):
            if tab_id not in next_ids:
                self._forget_tab(tab_id)
        for info in tabs:
            existing = self._tabs.get(info.tab_id)
            if existing:
                existing.info = info
            else:
                self._tabs[info.tab_id] = TabState(info=info)

    def handle_cdp_event(
        self,
        tab_id: int,
        method: str,
        params: object,
        session_id: str | None = None,
    ) -> None:
        tab = self._tabs.get(tab_id)
        root_session = tab.attached.session_id if tab and tab.attached else None
        if not root_session:
            return
        effective_session = session_id or root_session
        if session_id:
            self._child_sessions[session_id] = tab_id
        frame = json.dumps({"sessionId": effective_session, "method": method, "params": params})
        for client in self._clients:
            if effective_session in client.announced_sessions:
                client.send(frame)

    def handle_extension_detached(self, tab_id: int) -> None:
        tab = self._tabs.get(tab_id)
        if tab and tab.attached:
            self._emit_detached(tab_id, tab.attached)
            tab.attached = None

    async def _ensure_tab_attached(self, tab_id: int) -> AttachedTab:
        tab = self._tabs.get(tab_id)
        if tab is None:
            raise RuntimeError(f"tab {tab_id} is not available to relay")
        if tab.attached:
            return tab.attached
        if tab.attaching:
            return await tab.attaching

        loop = asyncio.get_running_loop()
        attaching: asyncio.Future[AttachedTab] = loop.create_future()
        tab.attaching = attaching

        async def _attach() -> AttachedTab:
            result = await self._call_extension_cmd({"type": "attach", "tabId": tab_id})
            # Playwright matches the target id against the page's main frame id, so a guessed id would hang it.
            target_id = result.get("targetId") if isinstance(result, dict) else None
            if not isinstance(target_id, str) or not target_id:
                await self._release_in_extension(tab_id)
                raise RuntimeError(f"extension did not return a target id for tab {tab_id}")
            session_id = f"myrm-tab-{tab_id}-{self._next_session_ordinal}"
            self._next_session_ordinal += 1
            attached = AttachedTab(target_id=target_id, session_id=session_id)
            current = self._tabs.get(tab_id)
            if current is not tab:
                await self._release_in_extension(tab_id)
                raise RuntimeError(f"tab {tab_id} closed during attach")
            current.attached = attached
            return attached

        task = asyncio.create_task(_attach())
        try:
            attached = await task
            if not attaching.done():
                attaching.set_result(attached)
            return attached
        except Exception as exc:
            if not attaching.done():
                attaching.set_exception(exc)
            raise
        finally:
            tab.attaching = None

    def _target_info(self, tab: TabState, target_id: str) -> dict[str, object]:
        return {
            "targetId": target_id,
            "type": "page",
            "title": tab.info.title,
            "url": tab.info.url,
            "browserContextId": tab.context_id or BROWSER_CONTEXT_ID,
            "attached": True,
            "canAccessOpener": False,
        }

    def _announce_attached(self, client: CdpClient, tab_id: int, attached: AttachedTab) -> None:
        tab = self._tabs.get(tab_id)
        if not tab:
            return
        if attached.session_id in client.announced_sessions:
            return
        client.announced_sessions.add(attached.session_id)
        event = {
            "method": "Target.attachedToTarget",
            "params": {
                "sessionId": attached.session_id,
                "targetInfo": self._target_info(tab, attached.target_id),
                "waitingForDebugger": False,
            },
        }
        client.send(json.dumps(event))

    def _emit_detached(self, tab_id: int, attached: AttachedTab) -> None:
        event = json.dumps(
            {
                "method": "Target.detachedFromTarget",
                "params": {"sessionId": attached.session_id, "targetId": attached.target_id},
            }
        )
        for client in self._clients:
            if attached.session_id in client.announced_sessions:
                client.announced_sessions.discard(attached.session_id)
                client.send(event)
        for child_session, owner_tab in list(self._child_sessions.items()):
            if owner_tab == tab_id:
                del self._child_sessions[child_session]
                for client in self._clients:
                    client.announced_sessions.discard(child_session)

    def _tab_by_session(self, session_id: str) -> tuple[int, bool] | None:
        for tab_id, tab in self._tabs.items():
            if tab.attached and tab.attached.session_id == session_id:
                return tab_id, False
        if session_id in self._auxiliary_tab_sessions:
            tab_id, _, _ = self._auxiliary_tab_sessions[session_id]
            return tab_id, False
        owner = self._child_sessions.get(session_id)
        if owner is not None:
            return owner, True
        return None

    def _tab_by_target(self, target_id: str) -> TabState | None:
        for tab in self._tabs.values():
            if tab.attached and tab.attached.target_id == target_id:
                return tab
        return None

    def _detach_all_when_idle(self) -> None:
        if self._clients or not self._call_extension:
            return
        for tab_id, tab in list(self._tabs.items()):
            if tab.attached:
                attached = tab.attached
                tab.attached = None
                self._emit_detached(tab_id, attached)
                self._spawn(self._release_in_extension(tab_id))

    def _forget_tab(self, tab_id: int) -> None:
        """Drop a tab from the relay, telling every client that announced it that the target is gone."""
        state = self._tabs.pop(tab_id, None)
        if state and state.attached:
            self._emit_detached(tab_id, state.attached)

    async def _close_tab(self, tab_id: int) -> None:
        """Close a tab in the browser (the extension only closes tabs the Agent opened), then forget it."""
        await self._call_extension_cmd({"type": "closeTab", "tabId": tab_id})
        self._forget_tab(tab_id)

    async def _release_in_extension(self, tab_id: int) -> None:
        """Detach the extension's debugger from a tab; a failure means the tab or the extension is already gone."""
        try:
            await self._call_extension_cmd({"type": "detach", "tabId": tab_id})
        except RuntimeError as exc:
            logger.warning("Could not detach tab %s in the extension: %s", tab_id, exc)

    def _spawn(self, work: Coroutine[object, object, None]) -> None:
        """Run fire-and-forget work with a strong reference so it cannot be garbage-collected mid-flight."""
        task = asyncio.create_task(work)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
