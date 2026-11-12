"""Relay-internal records: connected CDP clients, attached tabs, one CDP request and the extension identity.

[INPUT]
- cdp_relay.protocol::RelayTabInfo (POS: relay wire types)
- json, asyncio (POS: JSON-RPC framing, attach future)

[OUTPUT]
- CdpClient, AttachedTab, TabState, ExtensionIdentity: relay state records
- CdpRequest: one parsed client request that knows how to answer itself

[POS]
Plain records shared by the relay bridge layers. The only behaviour is JSON-RPC response framing.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field

from .protocol import RelayTabInfo


@dataclass
class CdpClient:
    """One Playwright connection on the loopback /cdp socket."""

    send: Callable[[str], None]
    auto_attach: bool = False
    announced_sessions: set[str] = field(default_factory=set)


@dataclass
class AttachedTab:
    target_id: str
    session_id: str


@dataclass
class TabState:
    info: RelayTabInfo
    attached: AttachedTab | None = None
    attaching: asyncio.Future[AttachedTab] | None = None
    # Virtual browser context the Agent opened this tab in; None = the shared default context.
    context_id: str | None = None


@dataclass
class ExtensionIdentity:
    user_agent: str = ""
    browser_version: str = ""


@dataclass(frozen=True, slots=True)
class CdpRequest:
    """A client request: where it came from, what it asks, and the replies it is owed."""

    client: CdpClient
    req_id: int
    method: str
    params: dict[str, object]
    session_id: str | None

    def ok(self, result: object = None) -> None:
        payload: dict[str, object] = {"id": self.req_id, "result": result or {}}
        if self.session_id:
            payload["sessionId"] = self.session_id
        self.client.send(json.dumps(payload))

    def error(self, message: str, code: int = -32000) -> None:
        payload: dict[str, object] = {"id": self.req_id, "error": {"message": message, "code": code}}
        if self.session_id:
            payload["sessionId"] = self.session_id
        self.client.send(json.dumps(payload))
