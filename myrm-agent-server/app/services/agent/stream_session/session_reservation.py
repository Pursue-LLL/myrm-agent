"""Chat session gateway reservation for agent-stream orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.agent.gateway import AgentBusyError, get_agent_gateway


@dataclass(slots=True)
class ChatSessionReservation:
    """Reserve a chat session in AgentGateway before persist; release on early exit."""

    chat_id: str | None = None
    _active: bool = False
    _transferred: bool = False

    def try_reserve(self, chat_id: str | None, *, message_id: str | None) -> AgentBusyError | None:
        if not chat_id:
            return None
        try:
            get_agent_gateway().reserve_session(
                chat_id,
                active_message_id=message_id,
            )
        except AgentBusyError as exc:
            return exc
        self.chat_id = chat_id
        self._active = True
        return None

    def transfer_to_stream(self) -> None:
        """Ownership moves to gateway.execute_stream lifecycle."""
        self._transferred = True

    def release(self) -> None:
        if self._active and not self._transferred and self.chat_id:
            get_agent_gateway().release_session(self.chat_id)
        self._active = False
