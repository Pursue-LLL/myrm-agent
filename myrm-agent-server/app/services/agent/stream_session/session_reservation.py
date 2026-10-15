"""Chat session gateway reservation for agent-stream orchestration.

[INPUT]
- app.services.agent.gateway::get_agent_gateway (POS: session reserve/release lifecycle)
- myrm_agent_harness.agent.middlewares.approval.scheduler::ApprovalTimeoutScheduler (POS: reopens the interrupt of a resume that never reached the graph)

[OUTPUT]
- ChatSessionReservation: reserve before persist, transfer to stream, release on early exit
- release_unstreamed_reservation: clear a reservation the stream never took over

[POS]
Orchestrator helper for idempotent agent-stream session locking without leaking gateway state.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

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


def release_unstreamed_reservation(chat_id: str, *, was_resume: bool) -> None:
    """Release a reservation that never reached ``execute_stream``.

    A resume that never reached the graph left its interrupt unanswered, so the interrupt is
    reopened for a manual answer instead of staying claimed by the request that failed.
    """
    if get_agent_gateway().release_if_reserved_only(chat_id) and was_resume:
        ApprovalTimeoutScheduler.get().reopen(chat_id)
