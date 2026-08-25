"""Unit tests for stream_loop MissingSemantics gate interception."""

from __future__ import annotations

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


@pytest.mark.asyncio
async def test_iter_agent_stream_chunks_intercepts_missing_semantics_blocked() -> None:
    """stream_loop must intercept MissingSemanticsBlockedError and emit structured error + message chunks."""
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
    session.params.message_id = "msg_missing_sem_123"
    session.routing_tier = "simple"
    session.extra_context = {}
    session.cancel_token.is_cancelled = False
    session.collector = MagicMock()

    approval = ApprovalTimeoutHolder()
    clarification = ClarificationTimeoutHolder()

    contract = MissingSemanticsContract(
        category=SemanticsCategory.SANDBOX_ISOLATION,
        policy=MissingSemanticsPolicy.FAIL_CLOSED,
        error_code="ERR_MISSING_SANDBOX_ISOLATION",
        user_message="Sandbox container isolation provider is unavailable",
        remediation_hint="Ensure the Docker/Sandbox daemon is running.",
    )
    blocked_exc = MissingSemanticsBlockedError(contract=contract, detail="Docker offline")

    async def _failing_stream(*args, **kwargs):
        raise blocked_exc
        yield {}

    with patch(
        "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
        _failing_stream,
    ):
        chunks = []
        async for chunk in iter_agent_stream_chunks(session, approval, clarification):
            chunks.append(chunk)

        assert any("missing_semantics_blocked" in c for c in chunks)
        assert any("ERR_MISSING_SANDBOX_ISOLATION" in c for c in chunks)
        assert any("Docker offline" in c or "Sandbox container isolation provider" in c for c in chunks)
        assert any("fail_closed" in c for c in chunks)
