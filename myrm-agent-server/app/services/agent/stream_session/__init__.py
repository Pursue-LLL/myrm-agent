"""Agent stream session orchestration entrypoint.

[INPUT]
- app.services.agent.params (POS: AgentRequest conversion)
- fastapi (POS: Request / StreamingResponse / JSONResponse transport types)

[OUTPUT]
- run_agent_stream: package-level facade forwarding to the orchestrator

[POS]
Service-layer stream orchestration entry. The facade lazy-imports the
orchestrator so importing this package never drags in its heavy dependency
chain at module load time; callers go through this facade, never through the
internal orchestrator module directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request
    from fastapi.responses import JSONResponse, StreamingResponse

    from app.services.agent.params import AgentRequest

__all__ = ["run_agent_stream"]


async def run_agent_stream(
    request: AgentRequest,
    http_request: Request,
) -> StreamingResponse | JSONResponse:
    """Run a streaming agent turn via the orchestrator (lazy-imported)."""
    from app.services.agent.stream_session.orchestrator import run_agent_stream as _run_agent_stream

    return await _run_agent_stream(request, http_request)
