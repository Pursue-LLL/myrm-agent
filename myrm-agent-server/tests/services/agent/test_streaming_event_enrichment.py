"""What the General Agent stream adds to an event before it reaches the client.

Real scenario: a tool asks for approval and the card the client shows carries the id of the filed approval; a browser
takeover request carries the link that opens the live browser on a phone; every event also carries the mascot status
the UI animates. An event whose fields have an unexpected shape must still reach the client animated, rather than
losing its status.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.streaming import ai_agent_service_stream


def _params() -> GeneralAgentParams:
    return GeneralAgentParams(
        query="hello",
        model_cfg=ModelConfig(model="gpt-4o-mini", api_key="test-key"),
        search_service_cfg=SearchServiceConfig(search_service="tavily"),
        chat_id="chat-enrichment",
        message_id="msg-enrichment",
    )


async def _stream(event: object) -> tuple[list[dict[str, object]], AsyncMock]:
    """Run the stream over one gateway event; return what it yielded and the approval-filing mock."""

    async def _execute_stream(*_args: object, **_kwargs: object) -> AsyncIterator[object]:
        yield event

    with (
        patch("app.services.budget.enforcer.should_block_execution", new_callable=AsyncMock, return_value=False),
        patch("app.services.budget.enforcer.reset_session_budget"),
        patch("app.services.agent.streaming.get_agent_gateway") as get_gateway,
        patch("app.services.agent.execution_cache.finalize_agent_session", new_callable=AsyncMock),
        patch(
            "app.services.approvals.registry.ApprovalRegistry.create_approval",
            new_callable=AsyncMock,
            return_value=MagicMock(id="approval-1"),
        ) as create_approval,
    ):
        get_gateway.return_value = MagicMock(execute_stream=_execute_stream)
        events = [chunk async for chunk in ai_agent_service_stream(_params())]
    return events, create_approval


class _EventObject:
    """A gateway event that is an object rather than a dict; only ``to_dict`` gives a copy that can carry the link."""

    def __init__(self, event_type: str, data: dict[str, object]) -> None:
        self.type = event_type
        self.data = data

    def to_dict(self) -> dict[str, object]:
        return {"type": self.type, "data": dict(self.data)}


def _approval(**data: object) -> dict[str, object]:
    return {"type": "approval_required", "data": {"action_type": "shell_execute", "reason": "run it", **data}}


def _of_type(events: list[dict[str, object]], event_type: str) -> dict[str, object]:
    (found,) = [event for event in events if event.get("type") == event_type]
    return found


@pytest.mark.asyncio
async def test_an_approval_is_filed_and_reaches_the_client_with_the_id_of_its_record() -> None:
    events, create_approval = await _stream(_approval())

    create_approval.assert_awaited_once()
    data = _of_type(events, "approval_required")["data"]
    assert isinstance(data, dict)
    assert data["approval_id"] == "approval-1"
    assert data["messageId"] == "msg-enrichment"


@pytest.mark.asyncio
async def test_an_event_whose_data_is_not_an_object_still_carries_its_mascot_status() -> None:
    events, _ = await _stream({"type": "tool_error", "data": "boom"})

    assert _of_type(events, "tool_error")["mascot_status"] == "dizzy"


@pytest.mark.asyncio
async def test_a_browser_takeover_request_reaches_the_client_with_its_live_assist_link() -> None:
    link = "https://assist.example/mobile/takeover/chat-enrichment?pair=token"
    request = {"type": "browser_takeover_requested", "data": {"reason": "Complete MFA", "url": "https://example.com"}}

    with patch(
        "app.services.agent.streaming_support.takeover_live_assist._create_takeover_live_assist_url",
        new_callable=AsyncMock,
        return_value=link,
    ):
        events, _ = await _stream(request)

    data = _of_type(events, "browser_takeover_requested")["data"]
    assert isinstance(data, dict)
    assert data["live_assist_url"] == link


@pytest.mark.asyncio
async def test_a_takeover_request_that_is_an_object_event_still_reaches_the_client_with_its_link() -> None:
    link = "https://assist.example/mobile/takeover/chat-enrichment?pair=token"
    request = _EventObject("browser_takeover_requested", {"reason": "Complete MFA", "url": "https://example.com"})

    with patch(
        "app.services.agent.streaming_support.takeover_live_assist._create_takeover_live_assist_url",
        new_callable=AsyncMock,
        return_value=link,
    ):
        events, _ = await _stream(request)

    data = _of_type(events, "browser_takeover_requested")["data"]
    assert isinstance(data, dict)
    assert data["live_assist_url"] == link
