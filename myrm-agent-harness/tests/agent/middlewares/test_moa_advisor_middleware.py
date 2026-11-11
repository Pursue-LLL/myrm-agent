"""Tests for moa_advisor_middleware — skip gates and transient injection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import create_moa_advisor_middleware
from myrm_agent_harness.core.message_origin import is_user_authored_human_message
from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import (
    MoAOverlayConfig,
)
from myrm_agent_harness.toolkits.llms.consensus.types import ReferenceResponse


@pytest.mark.asyncio
async def test_middleware_skips_when_unattended() -> None:
    mock_llm = MagicMock()
    middleware = create_moa_advisor_middleware(
        [mock_llm],
        config=MoAOverlayConfig(),
        unattended=True,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))

    with patch(
        "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
        new_callable=AsyncMock,
    ) as run_mock:
        await middleware.awrap_model_call(request, handler)
        run_mock.assert_not_called()
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_middleware_emits_overlay_active_before_fanout() -> None:
    mock_llm = MagicMock(model_name="ref-a")
    middleware = create_moa_advisor_middleware(
        [mock_llm],
        config=MoAOverlayConfig(min_successful=1, fanout="user_turn"),
        unattended=False,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))
    active_mock = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware._emit_overlay_active",
            active_mock,
        ),
    ):
        await middleware.awrap_model_call(request, handler)

    active_mock.assert_awaited_once()
    assert active_mock.await_args.args[0] == ["ref-a"]
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_middleware_emits_ref_done_via_callback() -> None:
    mock_llm = MagicMock()
    middleware = create_moa_advisor_middleware(
        [mock_llm],
        config=MoAOverlayConfig(min_successful=1),
        unattended=False,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))

    refs = [
        ReferenceResponse(
            model="ref-a",
            content="Advice A",
            elapsed_seconds=0.5,
            success=True,
        ),
        ReferenceResponse(
            model="ref-b",
            content="Advice B",
            elapsed_seconds=0.6,
            success=True,
        ),
    ]
    emit_mock = AsyncMock()

    async def run_with_callback(_messages, *, on_ref_done=None):
        if on_ref_done is not None:
            for ref in refs:
                await on_ref_done(ref)
        return refs

    with (
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
            side_effect=run_with_callback,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware._emit_ref_done",
            emit_mock,
        ),
    ):
        await middleware.awrap_model_call(request, handler)

    assert emit_mock.await_count == 2
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_middleware_injects_advisor_block_on_success() -> None:
    mock_llm = MagicMock()
    middleware = create_moa_advisor_middleware(
        [mock_llm],
        config=MoAOverlayConfig(min_successful=1),
        unattended=False,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))

    refs = [
        ReferenceResponse(
            model="ref-a",
            content="Use incremental approach",
            elapsed_seconds=0.5,
            success=True,
        )
    ]

    with (
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
            new_callable=AsyncMock,
            return_value=refs,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware._emit_ref_done",
            new_callable=AsyncMock,
        ),
    ):
        await middleware.awrap_model_call(request, handler)

    handler.assert_awaited_once()
    passed_request = handler.await_args.args[0]
    first_msg, last_msg = passed_request.messages
    assert first_msg.content == "hello"
    assert isinstance(last_msg, HumanMessage)
    assert "Use incremental approach" in str(last_msg.content)
    assert not is_user_authored_human_message(last_msg)


@pytest.mark.asyncio
async def test_middleware_emits_overlay_skipped_on_insufficient_refs() -> None:
    mock_llm = MagicMock(model_name="ref-a")
    middleware = create_moa_advisor_middleware(
        [mock_llm],
        config=MoAOverlayConfig(min_successful=2, fanout="user_turn"),
        unattended=False,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))
    skip_mock = AsyncMock()

    refs = [
        ReferenceResponse(
            model="ref-a",
            content="Advice A",
            elapsed_seconds=0.5,
            success=True,
        ),
        ReferenceResponse(
            model="ref-b",
            content="",
            elapsed_seconds=0.6,
            success=False,
        ),
    ]

    with (
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
            new_callable=AsyncMock,
            return_value=refs,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware._emit_overlay_skipped",
            skip_mock,
        ),
    ):
        await middleware.awrap_model_call(request, handler)

    skip_mock.assert_awaited_once_with("insufficient_refs")
    handler.assert_awaited_once()
    passed_request = handler.await_args.args[0]
    last_msg = passed_request.messages[-1]
    assert last_msg.content == "hello"


@pytest.mark.asyncio
async def test_injection_empty_skips_override() -> None:
    """When injection block is empty, the model is sent the conversation untouched."""
    from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
        create_moa_advisor_middleware as _create,
    )

    mock_llm = MagicMock()
    middleware = _create(
        [mock_llm],
        config=MoAOverlayConfig(min_successful=1),
        unattended=False,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))
    refs = [
        ReferenceResponse(
            model="ref-a",
            content="Advice",
            elapsed_seconds=0.5,
            success=True,
        )
    ]

    with (
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
            new_callable=AsyncMock,
            return_value=refs,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.build_advisor_injection_block",
            return_value="",
        ),
    ):
        await middleware.awrap_model_call(request, handler)

    handler.assert_awaited_once()
    passed_request = handler.await_args.args[0]
    assert passed_request.messages == request.messages


@pytest.mark.asyncio
async def test_middleware_privacy_redaction_applied() -> None:
    """When privacy_filter is enabled and privacy_redactor is supplied, reference output must be redacted."""
    from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
        create_moa_advisor_middleware as _create,
    )

    mock_llm = MagicMock()
    fake_redactor = MagicMock(side_effect=lambda text: text.replace("sk-secret1234567890", "[redacted secret]"))

    middleware = _create(
        [mock_llm],
        config=MoAOverlayConfig(min_successful=1, privacy_filter="full"),
        unattended=False,
        privacy_redactor=fake_redactor,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))

    raw_content = "Here is my key: sk-secret1234567890 for testing."
    refs = [
        ReferenceResponse(
            model="ref-a",
            content=raw_content,
            elapsed_seconds=0.5,
            success=True,
        )
    ]

    with patch(
        "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
        new_callable=AsyncMock,
        return_value=refs,
    ):
        await middleware.awrap_model_call(request, handler)

    handler.assert_awaited_once()
    passed_request = handler.await_args.args[0]
    last_msg = passed_request.messages[-1]
    assert "[redacted secret]" in str(last_msg.content)
    assert "sk-secret1234567890" not in str(last_msg.content)
    assert fake_redactor.called


@pytest.mark.asyncio
async def test_middleware_preserves_prefix_cache_in_tool_loop() -> None:
    mock_llm = MagicMock(model_name="ref-a")
    middleware = create_moa_advisor_middleware(
        [mock_llm],
        config=MoAOverlayConfig(fanout="per_iteration"),
        unattended=False,
    )

    h0 = HumanMessage(content="Do task", id="h0")
    ai1 = AIMessage(content="", id="ai1")
    t2 = ToolMessage(content="error result", tool_call_id="c1", id="t2")
    request = ModelRequest(messages=[h0, ai1, t2], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))

    refs = [
        ReferenceResponse(
            model="ref-a",
            content="Try a different flag",
            elapsed_seconds=0.2,
            success=True,
        ),
    ]

    with (
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
            new_callable=AsyncMock,
            return_value=refs,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware._emit_ref_done",
            new_callable=AsyncMock,
        ),
    ):
        await middleware.awrap_model_call(request, handler)

    handler.assert_awaited_once()
    passed_request = handler.await_args.args[0]
    # Verify index 0 was NOT touched (preserving prompt cache)
    assert passed_request.messages[0].content == "Do task"
    assert passed_request.messages[1] is ai1
    assert passed_request.messages[2] is t2
    # Verify tail has the advisor guidance
    assert len(passed_request.messages) == 4
    last_msg = passed_request.messages[3]
    assert isinstance(last_msg, HumanMessage)
    assert "Try a different flag" in str(last_msg.content)
