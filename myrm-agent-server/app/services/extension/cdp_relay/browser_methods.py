"""Browser- and Target-domain CDP methods the relay answers itself instead of forwarding to a tab.

[INPUT]
- cdp_relay.contexts::ContextRegistry (POS: virtual contexts over the tab mirror)
- cdp_relay.models::CdpRequest (POS: one client request that answers itself)
- cdp_relay.protocol::BROWSER_TARGET_ID, RelayTabInfo (POS: relay wire types)

[OUTPUT]
- BrowserMethods: browser-scoped request dispatch (method name → handler)

[POS]
Synthesizes the browser endpoint Playwright connects to: version, target discovery, attach/detach, target
creation and closing, virtual browser contexts. Anything not listed here is answered with "method not found"
rather than faked.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from .contexts import ContextRegistry
from .models import CdpClient, CdpRequest, TabState
from .protocol import BROWSER_TARGET_ID, RelayTabInfo

logger = logging.getLogger(__name__)

BrowserHandler = Callable[[CdpRequest], Awaitable[None]]


class BrowserMethods(ContextRegistry):
    """Dispatches browser-scoped CDP requests to their handlers."""

    def __init__(self) -> None:
        super().__init__()
        self._browser_handlers: dict[str, BrowserHandler] = {
            "Browser.getVersion": self._browser_get_version,
            "Browser.close": self._acknowledge,
            "Browser.setDownloadBehavior": self._acknowledge,
            "Target.setDiscoverTargets": self._acknowledge,
            "Target.getTargetInfo": self._target_get_target_info,
            "Target.getTargets": self._target_get_targets,
            "Target.attachToBrowserTarget": self._target_attach_to_browser_target,
            "Target.setAutoAttach": self._target_set_auto_attach,
            "Target.attachToTarget": self._target_attach_to_target,
            "Target.detachFromTarget": self._target_detach_from_target,
            "Target.createTarget": self._target_create_target,
            "Target.closeTarget": self._target_close_target,
            "Target.createBrowserContext": self._target_create_browser_context,
            "Target.disposeBrowserContext": self._target_dispose_browser_context,
        }

    async def _handle_browser_scoped(
        self,
        client: CdpClient,
        req_id: int,
        method: str,
        params: dict[str, object],
        session_id: str | None,
    ) -> None:
        request = CdpRequest(client, req_id, method, params, session_id)
        handler = self._browser_handlers.get(method)
        if handler is None:
            request.error(f"Unsupported browser method: {method}", -32601)
            return
        await handler(request)

    async def _acknowledge(self, request: CdpRequest) -> None:
        request.ok()

    async def _browser_get_version(self, request: CdpRequest) -> None:
        request.ok(
            {
                "protocolVersion": "1.3",
                "product": self._identity.browser_version or "Chrome/unknown",
                "revision": "myrm-extension-relay",
                "userAgent": self._identity.user_agent or "unknown",
                "jsVersion": "",
            }
        )

    async def _target_get_target_info(self, request: CdpRequest) -> None:
        target_id = request.params.get("targetId")
        if target_id == BROWSER_TARGET_ID or not target_id:
            request.ok(
                {
                    "targetInfo": {
                        "targetId": BROWSER_TARGET_ID,
                        "type": "browser",
                        "title": "Myrm Extension Relay",
                        "url": "",
                        "attached": True,
                        "canAccessOpener": False,
                    }
                }
            )
            return
        found = self._tab_by_target(str(target_id))
        if not found:
            request.error(f"No target with given id found: {target_id}", -32602)
            return
        resolved_target = found.attached.target_id if found.attached else str(target_id)
        request.ok({"targetInfo": self._target_info(found, resolved_target)})

    async def _target_get_targets(self, request: CdpRequest) -> None:
        infos = [self._target_info(tab, tab.attached.target_id) for tab in self._tabs.values() if tab.attached]
        request.ok({"targetInfos": infos})

    async def _target_attach_to_browser_target(self, request: CdpRequest) -> None:
        new_session = f"myrm-browser-{self._next_session_ordinal}"
        self._next_session_ordinal += 1
        self._browser_sessions[new_session] = request.client
        request.ok({"sessionId": new_session})

    async def _target_set_auto_attach(self, request: CdpRequest) -> None:
        auto_attach = request.params.get("autoAttach", True) is not False
        request.client.auto_attach = auto_attach
        if auto_attach:
            for tab_id in list(self._tabs):
                try:
                    attached = await self._ensure_tab_attached(tab_id)
                    self._announce_attached(request.client, tab_id, attached)
                except Exception as exc:
                    logger.warning("setAutoAttach failed for tab %s: %s", tab_id, exc)
        request.ok()

    async def _target_attach_to_target(self, request: CdpRequest) -> None:
        target_id = request.params.get("targetId")
        found = self._tab_by_target(str(target_id)) if target_id else None
        if not found:
            request.error("targetId is required", -32602)
            return
        attached = await self._ensure_tab_attached(found.info.tab_id)
        if request.session_id and self._browser_sessions.get(request.session_id) is request.client:
            aux_session = f"myrm-tab-{found.info.tab_id}-{self._next_session_ordinal}"
            self._next_session_ordinal += 1
            self._auxiliary_tab_sessions[aux_session] = (found.info.tab_id, request.session_id, request.client)
            request.ok({"sessionId": aux_session})
            return
        self._announce_attached(request.client, found.info.tab_id, attached)
        request.ok({"sessionId": attached.session_id})

    async def _target_detach_from_target(self, request: CdpRequest) -> None:
        detach_session = request.params.get("sessionId")
        if isinstance(detach_session, str):
            if self._browser_sessions.get(detach_session) is request.client:
                del self._browser_sessions[detach_session]
            if detach_session in self._auxiliary_tab_sessions:
                del self._auxiliary_tab_sessions[detach_session]
        request.ok()

    async def _target_create_target(self, request: CdpRequest) -> None:
        url = request.params.get("url")
        target_url = url if isinstance(url, str) and url else "about:blank"
        background = request.params.get("background") is True
        context_id = request.params.get("browserContextId")
        if context_id is not None and (not isinstance(context_id, str) or context_id not in self._contexts):
            request.error(f"Failed to find browser context with id {context_id}", -32602)
            return
        created = await self._call_extension_cmd({"type": "createTab", "url": target_url, "background": background})
        tab_id_raw = created.get("tabId") if isinstance(created, dict) else None
        if not isinstance(tab_id_raw, int):
            request.error("extension did not return tabId", -32000)
            return
        tab_id = tab_id_raw
        tab = self._tabs.get(tab_id)
        if tab is None:
            tab = self._tabs[tab_id] = TabState(info=RelayTabInfo(tab_id=tab_id, url=target_url, title="", active=not background))
        tab.context_id = context_id if isinstance(context_id, str) else None
        attached = await self._ensure_tab_attached(tab_id)
        self._announce_attached(request.client, tab_id, attached)
        request.ok({"targetId": attached.target_id})

    async def _target_close_target(self, request: CdpRequest) -> None:
        target_id = request.params.get("targetId")
        found = self._tab_by_target(target_id) if isinstance(target_id, str) else None
        if found is None:
            request.error(f"No target with given id found: {target_id}", -32602)
            return
        await self._close_tab(found.info.tab_id)
        request.ok({"success": True})

    async def _target_create_browser_context(self, request: CdpRequest) -> None:
        request.ok({"browserContextId": self._create_context(request.client)})

    async def _target_dispose_browser_context(self, request: CdpRequest) -> None:
        context_id = request.params.get("browserContextId")
        if not isinstance(context_id, str) or context_id not in self._contexts:
            request.error(f"Failed to find browser context with id {context_id}", -32602)
            return
        await self._dispose_context(context_id)
        request.ok()
