"""CDP bridge: Playwright connectOverCDP ↔ extension chrome.debugger transport.

[INPUT]
- cdp_relay.browser_methods::BrowserMethods (POS: browser-scoped CDP methods)
- cdp_relay.models::CdpClient, CdpRequest (POS: relay state records)
- cdp_relay.protocol::RelayCdpCommand (POS: relay wire types)
- asyncio, json (POS: async CDP client orchestration)

[OUTPUT]
- ExtensionCdpRelayBridge: CDP client endpoint (framing, routing, readiness probe) over the relay layers

[POS]
Top layer of the server-side CDP relay bridge. Parses client frames, answers browser-scoped requests
itself and forwards session-scoped ones to the owning tab, except the ones that would take the user's
focus; the MV3 extension stays a chrome.debugger forwarder.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

from .browser_methods import BrowserMethods
from .models import CdpClient, CdpRequest
from .protocol import RelayCdpCommand

_AUTOMATION_PROBE_ID = 9001

# Forwarded, this makes Chrome activate the tab and bring its window to the front, which pulls the user out of
# whatever they are doing in another window or application. Which tab the Agent works in is the client's
# bookkeeping and needs no help from the browser, so the request is acknowledged and nothing else happens.
_FOCUS_TAKING_METHODS = frozenset({"Page.bringToFront"})


class ExtensionCdpRelayBridge(BrowserMethods):
    """Synthesizes CDP Target.* semantics server-side; extension stays a forwarder."""

    def attach_cdp_client(
        self,
        send: Callable[[str], None],
    ) -> tuple[Callable[[str], None], Callable[[], None]]:
        client = CdpClient(send=send)
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
            self._dispose_contexts_of(client)
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

    async def _handle_cdp_client_message(self, client: CdpClient, raw: str) -> None:
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
        raw_params = request.get("params")
        params: dict[str, object] = raw_params if isinstance(raw_params, dict) else {}
        try:
            if isinstance(session_id, str):
                if self._browser_sessions.get(session_id) is client:
                    await self._handle_browser_scoped(client, req_id, method, params, session_id)
                else:
                    await self._handle_session_scoped(client, req_id, method, params, session_id)
            else:
                await self._handle_browser_scoped(client, req_id, method, params, None)
        except Exception as exc:
            CdpRequest(client, req_id, method, params, session_id if isinstance(session_id, str) else None).error(str(exc))

    async def _handle_session_scoped(
        self,
        client: CdpClient,
        req_id: int,
        method: str,
        params: dict[str, object],
        session_id: str,
    ) -> None:
        request = CdpRequest(client, req_id, method, params, session_id)
        route = self._tab_by_session(session_id)
        if route is None:
            request.error(f"Session not found: {session_id}", -32001)
            return
        if method in _FOCUS_TAKING_METHODS:
            request.ok()
            return
        tab_id, is_child = route
        cmd: RelayCdpCommand = {
            "type": "cdp",
            "tabId": tab_id,
            "method": method,
            "params": params,
        }
        if is_child:
            cmd["sessionId"] = session_id
        request.ok(await self._call_extension_cmd(cmd))
