"""A WebSocket stand-in for driving the extension bridge's receive loop in unit tests."""

from __future__ import annotations

from starlette.websockets import WebSocketDisconnect, WebSocketState


class FakeWs:
    """Queues the frames the extension "sends" and records what the server sends back."""

    client_state = WebSocketState.CONNECTED

    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)
        self.sent: list[str] = []

    async def receive_text(self) -> str:
        if not self.messages:
            raise WebSocketDisconnect()
        return self.messages.pop(0)

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self) -> None:
        self.client_state = WebSocketState.DISCONNECTED
