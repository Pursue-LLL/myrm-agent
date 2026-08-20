"""SSE HITL timeout auto-resume must inject runtime context before resuming the stream.

The timeout resumes (clarification / directory / approval) are unattended agent
continuations; they must carry execution_mode and disabled_skill_roots exactly like
the primary loop so disabled skill directories stay filtered.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.execution_cache.types import ExecutionMode
from app.services.agent.streaming_support import sse_helpers


def _capture_stream_calls() -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    async def capturing_stream(*_args: object, **_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        calls.append(_kwargs)
        if False:
            yield {}

    return calls, capturing_stream


@pytest.mark.asyncio
async def test_clarification_timeout_resume_injects_runtime_context() -> None:
    calls, capturing_stream = _capture_stream_calls()
    scheduler = MagicMock()
    params = MagicMock()
    params.model_copy.return_value = params

    with (
        patch(
            "app.services.agent.streaming_support.sse_helpers.ApprovalTimeoutScheduler.get",
            return_value=scheduler,
        ),
        patch("app.services.agent.streaming.ai_agent_service_stream", capturing_stream),
        patch(
            "app.services.agent.runtime_context.resolve_stream_execution_mode",
            return_value=ExecutionMode.POOLED,
        ),
        patch(
            "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
            new_callable=AsyncMock,
            return_value=["skills/prebuilt/off"],
        ),
    ):
        sse_helpers.schedule_clarification_timeout("chat-clarify-1", params)
        resume_callback = scheduler.schedule.call_args.kwargs["resume_callback"]
        await resume_callback({})

    assert len(calls) == 1
    extra_context = calls[0].get("extra_context")
    assert isinstance(extra_context, dict)
    assert extra_context["execution_mode"] == "pooled"
    assert extra_context["disabled_skill_roots"] == ["skills/prebuilt/off"]


@pytest.mark.asyncio
async def test_directory_timeout_resume_injects_runtime_context() -> None:
    calls, capturing_stream = _capture_stream_calls()
    scheduler = MagicMock()
    params = MagicMock()
    params.model_copy.return_value = params

    with (
        patch(
            "app.services.agent.streaming_support.sse_helpers.ApprovalTimeoutScheduler.get",
            return_value=scheduler,
        ),
        patch("app.services.agent.streaming.ai_agent_service_stream", capturing_stream),
        patch(
            "app.services.agent.runtime_context.resolve_stream_execution_mode",
            return_value=ExecutionMode.POOLED,
        ),
        patch(
            "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
            new_callable=AsyncMock,
            return_value=["skills/prebuilt/off"],
        ),
    ):
        sse_helpers.schedule_directory_timeout("chat-dir-1", params)
        resume_callback = scheduler.schedule.call_args.kwargs["resume_callback"]
        await resume_callback({})

    assert len(calls) == 1
    extra_context = calls[0].get("extra_context")
    assert isinstance(extra_context, dict)
    assert extra_context["execution_mode"] == "pooled"
    assert extra_context["disabled_skill_roots"] == ["skills/prebuilt/off"]


@pytest.mark.asyncio
async def test_approval_timeout_resume_injects_runtime_context() -> None:
    calls, capturing_stream = _capture_stream_calls()
    scheduler = MagicMock()
    params = MagicMock()
    params.model_copy.return_value = params

    with (
        patch(
            "app.services.agent.streaming_support.sse_helpers.ApprovalTimeoutScheduler.get",
            return_value=scheduler,
        ),
        patch("app.services.agent.streaming.ai_agent_service_stream", capturing_stream),
        patch(
            "app.services.agent.runtime_context.resolve_stream_execution_mode",
            return_value=ExecutionMode.POOLED,
        ),
        patch(
            "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
            new_callable=AsyncMock,
            return_value=["skills/prebuilt/off"],
        ),
    ):
        sse_helpers.schedule_approval_timeout(
            "chat-approval-1",
            {"seconds": 300, "behavior": "deny"},
            params,
        )
        resume_callback = scheduler.schedule.call_args.kwargs["resume_callback"]
        await resume_callback({})

    assert len(calls) == 1
    extra_context = calls[0].get("extra_context")
    assert isinstance(extra_context, dict)
    assert extra_context["execution_mode"] == "pooled"
    assert extra_context["disabled_skill_roots"] == ["skills/prebuilt/off"]
