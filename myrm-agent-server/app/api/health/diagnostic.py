from __future__ import annotations

from fastapi import APIRouter
from myrm_agent_harness.agent.middlewares._session_context import get_terminal_errors
from pydantic import BaseModel

router = APIRouter()


class DiagnosticStatus(BaseModel):
    is_hardened: bool = True
    terminal_errors: list[str]
    circuit_breaker_active: bool


@router.get("/status", response_model=DiagnosticStatus)
async def get_diagnostic_status() -> DiagnosticStatus:
    """Returns the current hardened diagnostic state of the agent engine."""
    registry = get_terminal_errors()
    registry._load()
    errors = list(registry.get_all())

    return DiagnosticStatus(terminal_errors=errors, circuit_breaker_active=len(errors) > 0)
