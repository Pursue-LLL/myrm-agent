"""Agent stream session orchestration entrypoint."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

__all__ = ["run_agent_stream"]


def run_agent_stream(*args: Any, **kwargs: Any) -> Awaitable[Any]:
    """Lazy-import orchestrator to avoid package import-time side effects."""
    from app.services.agent.stream_session.orchestrator import run_agent_stream as _run_agent_stream

    return _run_agent_stream(*args, **kwargs)
