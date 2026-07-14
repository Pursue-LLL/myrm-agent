"""Transport contract and raw CDP request loop for chat UI sessions."""

from __future__ import annotations

import asyncio
import json
from typing import Protocol

class CdpSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...


class CdpChatTransport:
    """Single WebSocket CDP session for chat UI automation."""

    def __init__(self, ws: CdpSocket, *, mid: list[int] | None = None) -> None:
        self._ws = ws
        self._mid = mid if mid is not None else [0]

    async def bridge_chat_id(self, *, recv_timeout: float = 15.0) -> str | None:
        from cdp_chat_support import BRIDGE_CHAT_ID_JS

        result = await self.evaluate(
            BRIDGE_CHAT_ID_JS,
            await_promise=False,
            recv_timeout=recv_timeout,
        )
        if isinstance(result, str) and result.strip():
            return result.strip()
        return None

    async def resolve_chat_id(
        self,
        *,
        path: str | None = None,
        hint: str | None = None,
        recv_timeout: float = 15.0,
    ) -> str | None:
        from cdp_chat_support import chat_id_from_path

        if hint and hint.strip():
            return hint.strip()
        if path:
            chat_id = chat_id_from_path(path)
            if chat_id:
                return chat_id
        return await self.bridge_chat_id(recv_timeout=recv_timeout)

    async def evaluate(
        self,
        expression: str,
        *,
        await_promise: bool = True,
        recv_timeout: float = 60.0,
    ) -> object:
        self._mid[0] += 1
        await self._ws.send(
            json.dumps(
                {
                    "id": self._mid[0],
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": await_promise,
                    },
                }
            )
        )
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=recv_timeout)
            result = json.loads(raw)
            if result.get("id") != self._mid[0]:
                continue
            if "exceptionDetails" in result:
                raise RuntimeError(f"CDP eval failed: {result['exceptionDetails']}")
            payload = result.get("result", {}).get("result", {})
            if "value" in payload:
                return payload["value"]
            return payload.get("description")

    async def cdp(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        recv_timeout: float = 30.0,
    ) -> dict[str, object]:
        self._mid[0] += 1
        await self._ws.send(
            json.dumps({"id": self._mid[0], "method": method, "params": params or {}})
        )
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=recv_timeout)
            result = json.loads(raw)
            if result.get("id") != self._mid[0]:
                continue
            if "error" in result:
                raise RuntimeError(f"CDP {method} failed: {result['error']}")
            payload = result.get("result")
            return payload if isinstance(payload, dict) else {}

