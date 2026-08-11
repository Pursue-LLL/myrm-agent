"""CDP bridge: Playwright connectOverCDP ↔ extension chrome.debugger transport.

[INPUT]
- cdp_relay.protocol::RelayCommand, RelayTabInfo (POS: relay wire types)
- asyncio, json (POS: async CDP client orchestration)

[OUTPUT]
- ExtensionCdpRelayBridge: Target synthesis + CDP client handler + automation probe
- build_extension_call_extension: bind bridge to extension WebSocket transport

[POS]
Server-side CDP relay bridge. Synthesizes Target.* semantics for Playwright while
the MV3 extension remains a chrome.debugger forwarder.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .protocol import (
    BROWSER_CONTEXT_ID,
    BROWSER_TARGET_ID,
    RELAY_COMMAND_TIMEOUT_S,
    RelayCommand,
    RelayTabInfo,
)

logger = logging.getLogger(__name__)

_AUTOMATION_PROBE_ID = 9001

SendToExtension = Callable[[dict[str, object]], Awaitable[None]]
CallExtension = Callable[[RelayCommand], Awaitable[object]]


@dataclass
class _CdpClient:
    send: Callable[[str], None]
    auto_attach: bool = False
    announced_sessions: set[str] = field(default_factory=set)


@dataclass
class _AttachedTab:
    target_id: str
    session_id: str


@dataclass
class _TabState:
    info: RelayTabInfo
    attached: _AttachedTab | None = None
    attaching: asyncio.Future[_AttachedTab] | None = None


@dataclass
class ExtensionIdentity:
    user_agent: str = ""
    browser_version: str = ""


class ExtensionCdpRelayBridge:
    """Synthesizes CDP Target.* semantics server-side; extension stays a forwarder."""

    def __init__(self) -> None:
        self._tabs: dict[int, _TabState] = {}
        self._clients: list[_CdpClient] = []
        self._browser_sessions: dict[str, _CdpClient] = {}
        self._child_sessions: dict[str, int] = {}
        self._auxiliary_tab_sessions: dict[str, tuple[int, str, _CdpClient]] = {}
        self._pending_extension: dict[int, asyncio.Future[object]] = {}
        self._next_seq = 1
        self._next_session_ordinal = 1
        self._identity = ExtensionIdentity()
        self._call_extension: CallExtension | None = None
        self._extension_connected = False

    @property
    def identity(self) -> ExtensionIdentity:
        return self._identity

    @property
    def extension_connected(self) -> bool:
        return self._extension_connected

    def set_extension_transport(self, call_extension: CallExtension | None) -> None:
        self._call_extension = call_extension
        self._extension_connected = call_extension is not None
        if call_extension is None:
            self._fail_pending_extension_commands("extension disconnected")

    def set_identity(
        self,
        *,
        user_agent: str = "",
        browser_version: str = "",
    ) -> None:
        self._identity = ExtensionIdentity(
            user_agent=user_agent,
            browser_version=browser_version,
        )

    def sync_tabs(self, tabs: list[RelayTabInfo]) -> None:
        next_ids = {tab.tab_id for tab in tabs}
        for tab_id in list(self._tabs):
            if tab_id not in next_ids:
                state = self._tabs.pop(tab_id)
                if state.attached:
                    self._emit_detached(tab_id, state.attached)
        for info in tabs:
            existing = self._tabs.get(info.tab_id)
            if existing:
                existing.info = info
            else:
                self._tabs[info.tab_id] = _TabState(info=info)

    async def handle_extension_result(self, seq: int, result: object) -> None:
        pending = self._pending_extension.pop(seq, None)
        if pending and not pending.done():
            pending.set_result(result)

    async def handle_extension_error(self, seq: int, message: str) -> None:
        pending = self._pending_extension.pop(seq, None)
        if pending and not pending.done():
            pending.set_exception(RuntimeError(message))

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

    def attach_cdp_client(
        self,
        send: Callable[[str], None],
    ) -> tuple[Callable[[str], None], Callable[[], None]]:
        client = _CdpClient(send=send)
        self._clients.append(client)

        def on_message(raw: str) -> None:
            asyncio.create_task(self._handle_cdp_client_message(client, raw))

        def on_close() -> None:
            try:
                self._clients.remove(client)
            except ValueError:
                pass
            for session_id, owner in list(self._browser_sessions.items()):
                if owner is client:
                    del self._browser_sessions[session_id]
            for session_id, (_, _, owner) in list(self._auxiliary_tab_sessions.items()):
                if owner is client:
                    del self._auxiliary_tab_sessions[session_id]
            self._detach_all_when_idle()

        return on_message, on_close

    async def probe_ready(self) -> bool:
        return self._extension_connected and self._call_extension is not None

    async def probe_automation_ready(self) -> bool:
        """Verify loopback CDP responds to Browser.getVersion (real automation path)."""
        if not await self.probe_ready():
            return False

        loop = asyncio.get_running_loop()
        probe_result: asyncio.Future[bool] = loop.create_future()
        sent_messages: list[str] = []

        def send(raw: str) -> None:
            sent_messages.append(raw)
            if probe_result.done():
                return
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return
            if payload.get("id") != _AUTOMATION_PROBE_ID:
                return
            if "result" in payload and isinstance(payload["result"], dict):
                probe_result.set_result(True)
            elif "error" in payload:
                probe_result.set_result(False)

        on_message, on_close = self.attach_cdp_client(send)
        try:
            on_message(json.dumps({"id": _AUTOMATION_PROBE_ID, "method": "Browser.getVersion"}))
            return await asyncio.wait_for(probe_result, timeout=5.0)
        except asyncio.TimeoutError:
            return False
        finally:
            on_close()

    async def _call_extension_cmd(self, command: RelayCommand) -> object:
        if self._call_extension is None:
            raise RuntimeError("Browser extension is not connected to CDP relay")
        return await self._call_extension(command)

    async def _handle_cdp_client_message(self, client: _CdpClient, raw: str) -> None:
        try:
            request = json.loads(raw)
        except json.JSONDecodeError:
            client.send(json.dumps({"id": None, "error": {"message": "Parse error", "code": -32700}}))
            return
        if not isinstance(request, dict):
            client.send(json.dumps({"id": None, "error": {"message": "Invalid request", "code": -32600}}))
            return
        req_id = request.get("id")
        method = request.get("method")
        if not isinstance(req_id, int) or not isinstance(method, str):
            client.send(
                json.dumps(
                    {
                        "id": req_id if isinstance(req_id, int) else None,
                        "error": {"message": "Invalid request", "code": -32600},
                    }
                )
            )
            return
        session_id = request.get("sessionId")
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        try:
            if isinstance(session_id, str):
                if self._browser_sessions.get(session_id) is client:
                    await self._handle_browser_scoped(client, req_id, method, params, session_id)
                else:
                    await self._handle_session_scoped(client, req_id, method, params, session_id)
            else:
                await self._handle_browser_scoped(client, req_id, method, params, None)
        except Exception as exc:
            self._respond_error(client, req_id, session_id if isinstance(session_id, str) else None, str(exc))

    async def _handle_session_scoped(
        self,
        client: _CdpClient,
        req_id: int,
        method: str,
        params: dict[str, object],
        session_id: str,
    ) -> None:
        route = self._tab_by_session(session_id)
        if route is None:
            self._respond_error(client, req_id, session_id, f"Session not found: {session_id}", -32001)
            return
        tab_id, is_child = route
        cmd: RelayCommand = {
            "type": "cdp",
            "tabId": tab_id,
            "method": method,
            "params": params,
        }
        if is_child:
            cmd["sessionId"] = session_id
        result = await self._call_extension_cmd(cmd)
        self._respond_ok(client, req_id, session_id, result)

    async def _handle_browser_scoped(
        self,
        client: _CdpClient,
        req_id: int,
        method: str,
        params: dict[str, object],
        session_id: str | None,
    ) -> None:
        if method == "Browser.getVersion":
            self._respond_ok(
                client,
                req_id,
                session_id,
                {
                    "protocolVersion": "1.3",
                    "product": self._identity.browser_version or "Chrome/unknown",
                    "revision": "myrm-extension-relay",
                    "userAgent": self._identity.user_agent or "unknown",
                    "jsVersion": "",
                },
            )
            return
        if method in ("Browser.close", "Browser.setDownloadBehavior", "Target.setDiscoverTargets"):
            self._respond_ok(client, req_id, session_id, {})
            if method == "Browser.close":
                client.send(json.dumps({"id": req_id, "result": {}}))
            return
        if method == "Target.getTargetInfo":
            target_id = params.get("targetId")
            if target_id == BROWSER_TARGET_ID or not target_id:
                self._respond_ok(
                    client,
                    req_id,
                    session_id,
                    {
                        "targetInfo": {
                            "targetId": BROWSER_TARGET_ID,
                            "type": "browser",
                            "title": "Myrm Extension Relay",
                            "url": "",
                            "attached": True,
                            "canAccessOpener": False,
                        }
                    },
                )
                return
            found = self._tab_by_target(str(target_id))
            if not found:
                self._respond_error(client, req_id, session_id, f"No target with given id found: {target_id}", -32602)
                return
            resolved_target = (
                found.attached.target_id
                if found.attached
                else str(target_id)
            )
            self._respond_ok(
                client,
                req_id,
                session_id,
                {"targetInfo": self._target_info(found.info, resolved_target)},
            )
            return
        if method == "Target.getTargets":
            infos = [
                self._target_info(tab.info, tab.attached.target_id)
                for tab in self._tabs.values()
                if tab.attached
            ]
            self._respond_ok(client, req_id, session_id, {"targetInfos": infos})
            return
        if method == "Target.attachToBrowserTarget":
            new_session = f"myrm-browser-{self._next_session_ordinal}"
            self._next_session_ordinal += 1
            self._browser_sessions[new_session] = client
            self._respond_ok(client, req_id, session_id, {"sessionId": new_session})
            return
        if method == "Target.setAutoAttach":
            auto_attach = params.get("autoAttach", True) is not False
            client.auto_attach = auto_attach
            if auto_attach:
                for tab_id in list(self._tabs):
                    try:
                        attached = await self._ensure_tab_attached(tab_id)
                        self._announce_attached(client, tab_id, attached)
                    except Exception as exc:
                        logger.warning("setAutoAttach failed for tab %s: %s", tab_id, exc)
            self._respond_ok(client, req_id, session_id, {})
            return
        if method == "Target.attachToTarget":
            target_id = params.get("targetId")
            found = self._tab_by_target(str(target_id)) if target_id else None
            if not found:
                self._respond_error(client, req_id, session_id, "targetId is required", -32602)
                return
            attached = await self._ensure_tab_attached(found.info.tab_id)
            if session_id and self._browser_sessions.get(session_id) is client:
                aux_session = f"myrm-tab-{found.info.tab_id}-{self._next_session_ordinal}"
                self._next_session_ordinal += 1
                self._auxiliary_tab_sessions[aux_session] = (found.info.tab_id, session_id, client)
                self._respond_ok(client, req_id, session_id, {"sessionId": aux_session})
                return
            self._announce_attached(client, found.info.tab_id, attached)
            self._respond_ok(client, req_id, session_id, {"sessionId": attached.session_id})
            return
        if method == "Target.detachFromTarget":
            detach_session = params.get("sessionId")
            if isinstance(detach_session, str):
                if self._browser_sessions.get(detach_session) is client:
                    del self._browser_sessions[detach_session]
                if detach_session in self._auxiliary_tab_sessions:
                    del self._auxiliary_tab_sessions[detach_session]
            self._respond_ok(client, req_id, session_id, {})
            return
        if method == "Target.createTarget":
            url = params.get("url")
            target_url = url if isinstance(url, str) and url else "about:blank"
            background = params.get("background") is True
            created = await self._call_extension_cmd(
                {"type": "createTab", "url": target_url, "background": background}
            )
            tab_id_raw = created.get("tabId") if isinstance(created, dict) else None
            if not isinstance(tab_id_raw, int):
                self._respond_error(client, req_id, session_id, "extension did not return tabId", -32000)
                return
            tab_id = tab_id_raw
            if tab_id not in self._tabs:
                self._tabs[tab_id] = _TabState(
                    info=RelayTabInfo(tab_id=tab_id, url=target_url, title="", active=not background)
                )
            attached = await self._ensure_tab_attached(tab_id)
            self._announce_attached(client, tab_id, attached)
            self._respond_ok(client, req_id, session_id, {"targetId": attached.target_id})
            return
        self._respond_error(client, req_id, session_id, f"Unsupported browser method: {method}", -32601)

    async def _ensure_tab_attached(self, tab_id: int) -> _AttachedTab:
        tab = self._tabs.get(tab_id)
        if tab is None:
            raise RuntimeError(f"tab {tab_id} is not available to relay")
        if tab.attached:
            return tab.attached
        if tab.attaching:
            return await tab.attaching

        loop = asyncio.get_running_loop()
        attaching: asyncio.Future[_AttachedTab] = loop.create_future()
        tab.attaching = attaching

        async def _attach() -> _AttachedTab:
            result = await self._call_extension_cmd({"type": "attach", "tabId": tab_id})
            target_id = f"tab-{tab_id}"
            if isinstance(result, dict):
                raw_target = result.get("targetId")
                if isinstance(raw_target, str) and raw_target:
                    target_id = raw_target
            session_id = f"myrm-tab-{tab_id}-{self._next_session_ordinal}"
            self._next_session_ordinal += 1
            attached = _AttachedTab(target_id=target_id, session_id=session_id)
            current = self._tabs.get(tab_id)
            if current is not tab:
                await self._call_extension_cmd({"type": "detach", "tabId": tab_id})
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

    def _target_info(self, info: RelayTabInfo, target_id: str) -> dict[str, object]:
        return {
            "targetId": target_id,
            "type": "page",
            "title": info.title,
            "url": info.url,
            "browserContextId": BROWSER_CONTEXT_ID,
            "attached": True,
            "canAccessOpener": False,
        }

    def _announce_attached(self, client: _CdpClient, tab_id: int, attached: _AttachedTab) -> None:
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
                "targetInfo": self._target_info(tab.info, attached.target_id),
                "waitingForDebugger": False,
            },
        }
        client.send(json.dumps(event))

    def _emit_detached(self, tab_id: int, attached: _AttachedTab) -> None:
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

    def _tab_by_target(self, target_id: str) -> _TabState | None:
        for tab in self._tabs.values():
            if tab.attached and tab.attached.target_id == target_id:
                return tab
        if target_id.startswith("tab-"):
            try:
                tab_id = int(target_id.removeprefix("tab-"))
            except ValueError:
                return None
            return self._tabs.get(tab_id)
        return None

    def _detach_all_when_idle(self) -> None:
        if self._clients or not self._call_extension:
            return
        for tab_id, tab in list(self._tabs.items()):
            if tab.attached:
                attached = tab.attached
                tab.attached = None
                self._emit_detached(tab_id, attached)
                asyncio.create_task(self._call_extension_cmd({"type": "detach", "tabId": tab_id}))

    def _fail_pending_extension_commands(self, message: str) -> None:
        for pending in self._pending_extension.values():
            if not pending.done():
                pending.set_exception(RuntimeError(message))
        self._pending_extension.clear()

    @staticmethod
    def _respond_ok(
        client: _CdpClient,
        req_id: int,
        session_id: str | None,
        result: object,
    ) -> None:
        payload: dict[str, object] = {"id": req_id, "result": result or {}}
        if session_id:
            payload["sessionId"] = session_id
        client.send(json.dumps(payload))

    @staticmethod
    def _respond_error(
        client: _CdpClient,
        req_id: int,
        session_id: str | None,
        message: str,
        code: int = -32000,
    ) -> None:
        payload: dict[str, object] = {
            "id": req_id,
            "error": {"message": message, "code": code},
        }
        if session_id:
            payload["sessionId"] = session_id
        client.send(json.dumps(payload))


def build_extension_call_extension(
    bridge: ExtensionCdpRelayBridge,
    send_to_extension: SendToExtension,
) -> CallExtension:
    async def call_extension(command: RelayCommand) -> object:
        seq = bridge._next_seq  # noqa: SLF001 — intentional coupling for seq ownership
        bridge._next_seq += 1
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[object] = loop.create_future()
        bridge._pending_extension[seq] = fut
        await send_to_extension({"type": "relay", "seq": seq, "command": command})
        try:
            return await asyncio.wait_for(fut, timeout=RELAY_COMMAND_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            bridge._pending_extension.pop(seq, None)
            raise RuntimeError(f"extension relay command timed out: {command['type']}") from exc

    return call_extension
