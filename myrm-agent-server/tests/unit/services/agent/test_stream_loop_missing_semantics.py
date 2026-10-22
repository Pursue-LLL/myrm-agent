"""Unit tests for stream_loop MissingSemantics gate interception."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.api import (
    MissingSemanticsBlockedError,
    MissingSemanticsContract,
    MissingSemanticsPolicy,
    SemanticsCategory,
)

from app.services.agent.stream_session.stream_loop import (
    ApprovalTimeoutHolder,
    ClarificationTimeoutHolder,
    iter_agent_stream_chunks,
)

_MESSAGE_ID = "msg_missing_sem_123"


def _make_session() -> MagicMock:
    session = MagicMock()
    session.request.resume_value = None
    session.request.use_workflow = False
    session.request.workflow_template_id = None
    session.request.action_mode = "fast"
    session.request.ephemeral_subagents = None
    session.request.blueprint_id = None
    session.request.mention_references = None
    session.request.agent_config = None
    session.params.enable_web_search = True
    session.params.message_id = _MESSAGE_ID
    session.routing_tier = "simple"
    session.extra_context = {}
    session.cancel_token.is_cancelled = False
    session.collector = MagicMock()
    return session


async def _collect_chunks(exc: Exception) -> list[str]:
    async def _failing_stream(*args: object, **kwargs: object) -> AsyncIterator[dict[str, str]]:
        raise exc
        yield {}

    with patch(
        "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
        _failing_stream,
    ):
        return [
            chunk
            async for chunk in iter_agent_stream_chunks(_make_session(), ApprovalTimeoutHolder(), ClarificationTimeoutHolder())
        ]


def _blocked_payload(chunks: list[str]) -> dict[str, str]:
    """Return the structured `missing_semantics_blocked` SSE payload."""
    for chunk in chunks:
        if "missing_semantics_blocked" in chunk and '"type"' in chunk:
            data_line = next(line for line in chunk.splitlines() if line.startswith("data:"))
            payload = json.loads(data_line.removeprefix("data:").strip())
            if payload.get("type") == "missing_semantics_blocked":
                return payload
    raise AssertionError("no missing_semantics_blocked payload emitted")


@pytest.mark.asyncio
async def test_iter_agent_stream_chunks_intercepts_missing_semantics_blocked() -> None:
    """stream_loop must intercept MissingSemanticsBlockedError and emit structured error + message chunks."""
    contract = MissingSemanticsContract(
        category=SemanticsCategory.SANDBOX_ISOLATION,
        policy=MissingSemanticsPolicy.FAIL_CLOSED,
        error_code="ERR_MISSING_SANDBOX_ISOLATION",
        user_message="Sandbox container isolation provider is unavailable",
        remediation_hint="Ensure the Docker/Sandbox daemon is running.",
    )
    chunks = await _collect_chunks(MissingSemanticsBlockedError(contract=contract, detail="Docker offline"))

    assert any("missing_semantics_blocked" in c for c in chunks)
    assert any("ERR_MISSING_SANDBOX_ISOLATION" in c for c in chunks)
    assert any("Docker offline" in c or "Sandbox container isolation provider" in c for c in chunks)
    assert any("fail_closed" in c for c in chunks)


@pytest.mark.asyncio
async def test_iter_agent_stream_chunks_intercepts_contractless_missing_semantics_blocked() -> None:
    """Decorator-raised blocks carry no contract; the handler must still emit the structured gate error."""
    exc = MissingSemanticsBlockedError(
        component_name="sandbox_isolation",
        action="run_code",
        repair_hint="Start the sandbox daemon.",
    )
    assert exc.contract is None

    chunks = await _collect_chunks(exc)

    payload = _blocked_payload(chunks)
    assert payload["error_code"] == "ERR_MISSING_SANDBOX_ISOLATION"
    assert payload["category"] == "sandbox_isolation"
    assert payload["policy"] == "fail_closed"
    assert payload["remediation_hint"] == "Start the sandbox daemon."
    assert payload["messageId"] == _MESSAGE_ID
    assert any('"completion_status"' in c and "missing_semantics_blocked" in c for c in chunks)
