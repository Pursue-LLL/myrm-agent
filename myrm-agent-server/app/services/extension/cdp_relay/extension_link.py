"""Server → extension command channel of the CDP relay.

[INPUT]
- cdp_relay.models::ExtensionIdentity (POS: relay state records)
- cdp_relay.protocol::RelayCommand, RELAY_COMMAND_TIMEOUT_S (POS: relay wire types)
- asyncio (POS: command round trip with timeout)

[OUTPUT]
- ExtensionLink: transport binding, pending-command bookkeeping, browser identity
- SendToExtension, CallExtension: transport callables

[POS]
Lowest layer of the relay bridge: owns the command round trip to the MV3 extension.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .models import ExtensionIdentity
from .protocol import RELAY_COMMAND_TIMEOUT_S, RelayCommand

SendToExtension = Callable[[dict[str, object]], Awaitable[None]]
CallExtension = Callable[[RelayCommand], Awaitable[object]]


class ExtensionLink:
    """Sends relay commands to the extension and resolves them from the extension's replies."""

    def __init__(self) -> None:
        self._pending_extension: dict[int, asyncio.Future[object]] = {}
        self._next_seq = 1
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

    def make_extension_caller(self, send_to_extension: SendToExtension) -> CallExtension:
        """Bind this link to the extension WebSocket sender; each call is matched to its reply by sequence number."""

        async def call_extension(command: RelayCommand) -> object:
            seq = self._next_seq
            self._next_seq += 1
            loop = asyncio.get_running_loop()
            fut: asyncio.Future[object] = loop.create_future()
            self._pending_extension[seq] = fut
            try:
                await send_to_extension({"type": "relay", "seq": seq, "command": command})
                return await asyncio.wait_for(fut, timeout=RELAY_COMMAND_TIMEOUT_S)
            except asyncio.TimeoutError as exc:
                raise RuntimeError(f"extension relay command timed out: {command['type']}") from exc
            finally:
                self._pending_extension.pop(seq, None)

        return call_extension

    async def handle_extension_result(self, seq: int, result: object) -> None:
        pending = self._pending_extension.pop(seq, None)
        if pending and not pending.done():
            pending.set_result(result)

    async def handle_extension_error(self, seq: int, message: str) -> None:
        pending = self._pending_extension.pop(seq, None)
        if pending and not pending.done():
            pending.set_exception(RuntimeError(message))

    async def _call_extension_cmd(self, command: RelayCommand) -> object:
        if self._call_extension is None:
            raise RuntimeError("Browser extension is not connected to CDP relay")
        return await self._call_extension(command)

    def _fail_pending_extension_commands(self, message: str) -> None:
        for pending in self._pending_extension.values():
            if not pending.done():
                pending.set_exception(RuntimeError(message))
        self._pending_extension.clear()
