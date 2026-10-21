"""An unexpected executor failure replies with member-safe wording; only the owner's direct chat is told what to fix.

Guests, paired members and group chats get the generic sentence for every error kind. The raw exception only
reaches the operator log, under the reference id the reply carries.
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.errors import FailoverReason, MyrmLLMError

from app.channels.routing.friendly_errors import is_error_reply
from app.channels.types import InboundMessage, OutboundMessage
from app.core.channel_bridge.agent_executor.executor import ChannelAgentExecutor

_EXECUTOR = "app.core.channel_bridge.agent_executor.executor"
_CAPABILITIES = "app.channels.routing.friendly_errors.get_deployment_capabilities"
_REF = re.compile(r" \[ref: ([0-9a-f]{8})\]$")
_RAW = "insufficient balance: key sk-live-secret-42 for https://internal.example/v1"


def _inbound(*, is_group: bool = False) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="hi",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="chat-1",
        user_id="user-1",
        is_group=is_group,
        mentioned=False,
        metadata={"locale": "en"},
    )


async def _reply(
    exc: Exception, *, user_id: str = "user-1", is_group: bool = False, platform_budget: bool = False
) -> OutboundMessage:
    with (
        patch(f"{_EXECUTOR}.prepare_channel_execution", new=AsyncMock(side_effect=exc)),
        patch(_CAPABILITIES, return_value=SimpleNamespace(uses_platform_budget=platform_budget)),
    ):
        replies = [event async for event in ChannelAgentExecutor().execute_stream(_inbound(is_group=is_group), user_id)]
    assert len(replies) == 1
    assert isinstance(replies[0], OutboundMessage)
    return replies[0]


@pytest.mark.asyncio
async def test_raw_exception_never_reaches_the_chat_and_is_logged_under_the_reference(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        reply = await _reply(RuntimeError(_RAW))

    assert "sk-live-secret-42" not in reply.content
    assert "internal.example" not in reply.content
    assert "[Error]" not in reply.content
    ref = _REF.search(reply.content)
    assert ref is not None
    logged = [r.getMessage() for r in caplog.records if "sk-live-secret-42" in r.getMessage()]
    assert len(logged) == 1
    assert f"[ref: {ref.group(1)}]" in logged[0]


@pytest.mark.asyncio
async def test_the_failure_reply_is_flagged_as_a_failed_turn() -> None:
    reply = await _reply(RuntimeError("boom"))

    assert is_error_reply(reply)


@pytest.mark.asyncio
async def test_owner_direct_chat_is_told_which_account_state_to_fix() -> None:
    byok = await _reply(Exception(_RAW))
    platform = await _reply(Exception(_RAW), platform_budget=True)

    assert "balance or quota" in byok.content
    assert "plan's credit" in platform.content
    assert "administrator" not in byok.content


@pytest.mark.asyncio
async def test_owner_is_pointed_to_settings_for_credentials_only_on_a_byok_deployment() -> None:
    byok = await _reply(Exception("invalid api key"))
    platform = await _reply(Exception("invalid api key"), platform_budget=True)

    assert "Settings > Model Services" in byok.content
    assert "Settings" not in platform.content
    assert "administrator" in platform.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "is_group"),
    [("guest_abc", False), ("paired_member_abc", False), ("user-1", True)],
    ids=["guest", "paired-member", "owner-in-group"],
)
async def test_untrusted_senders_and_groups_only_get_the_generic_wording(user_id: str, is_group: bool) -> None:
    reply = await _reply(Exception(_RAW), user_id=user_id, is_group=is_group)

    assert "balance" not in reply.content
    assert "plan" not in reply.content
    assert "administrator" in reply.content


@pytest.mark.asyncio
async def test_llm_error_diagnostics_only_reach_the_owner_direct_chat() -> None:
    def failure() -> MyrmLLMError:
        return MyrmLLMError(
            error_code=FailoverReason.BILLING,
            default_msg="billing",
            diagnostic_result={"user_message": "DIAGNOSTIC-WORDING", "resolution_steps": ["Check key sk-live-secret-42"]},
        )

    owner = await _reply(failure())
    guest = await _reply(failure(), user_id="guest_abc")

    assert "DIAGNOSTIC-WORDING" in owner.content
    assert "DIAGNOSTIC-WORDING" not in guest.content
    assert "sk-live-secret-42" not in guest.content
    assert is_error_reply(guest)
