"""SlackChannel contract compliance, placeholder and assistant thread status."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelSendError,
    RateLimitError,
)
from app.channels.providers.slack import SlackChannel
from app.channels.types import (
    OutboundMessage,
)
from tests.channels.channel_test_base import ChannelTestBase
from tests.channels.providers.slack.support import err_json, make_channel, ok_json


class TestSlackChannel(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return SlackChannel(
            bot_token="xoxb-test-token-for-unit-test",
            app_token="xapp-test-token-for-unit-test",
        )


class TestSlackPlaceholder:
    """The placeholder is a posted message that is edited in place; it is never a Slack stream.

    A Slack stream only appends, while the router replaces the placeholder text with stage labels, previews that
    end in a progress percentage, and the final reply.
    """

    @staticmethod
    async def _flow(previews: list[str], *, thread_id: str | None = "9.9") -> list[tuple[str, dict[str, object]]]:
        """Placeholder, progress edits and final reply in the order the router sends them; every Slack call."""
        ch = make_channel()
        calls: list[tuple[str, dict[str, object]]] = []

        async def record(url: str, *, json: dict[str, object], **_: object) -> httpx.Response:
            calls.append((url.rsplit("/", 1)[-1], json))
            return ok_json({"ts": "1.1"})

        reply = OutboundMessage(channel="slack", recipient_id="D1", content="The answer is 42.", user_id="U1")
        with patch.object(ch._api._http, "post", side_effect=record):
            ts = await ch.send_placeholder("D1", "Thinking...", thread_id=thread_id)
            assert ts == "1.1"
            for preview in previews:
                await ch.edit_message("D1", ts, preview)
            await ch.edit_placeholder_message("D1", ts, reply)
        return calls

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "previews",
        [[], ["Searching the web", "The answer [40% (~3s left)]", "The answer is 4 [80%]"]],
        ids=["no-preview", "labels-then-growing-preview"],
    )
    async def test_the_placeholder_is_edited_in_place_into_the_final_reply(self, previews: list[str]) -> None:
        calls = await self._flow(previews)

        assert [name for name, _ in calls] == [
            "assistant.threads.setStatus",
            "chat.postMessage",
            *["chat.update"] * (len(previews) + 1),
            "assistant.threads.setStatus",
        ]
        assert calls[1][1]["text"] == "Thinking..."
        assert [body["text"] for name, body in calls if name == "chat.update"] == [*previews, "The answer is 42."]

    @pytest.mark.asyncio
    async def test_a_thread_placeholder_replies_in_the_thread(self) -> None:
        calls = await self._flow([])

        assert calls[1][1] == {"channel": "D1", "text": "Thinking...", "thread_ts": "9.9"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "raised"),
        [
            ("cant_update_message", ChannelSendError),
            ("message_not_found", ChannelSendError),
            ("edit_window_closed", ChannelSendError),
            ("ratelimited", RateLimitError),
            ("token_revoked", ChannelAuthError),
        ],
    )
    async def test_an_edit_that_slack_rejects_is_raised_not_swallowed(self, error: str, raised: type[Exception]) -> None:
        ch = make_channel()
        reply = OutboundMessage(channel="slack", recipient_id="D1", content="The answer is 42.", user_id="U1")
        rejected = err_json(error, headers={"Retry-After": "5"})

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=rejected):
            with pytest.raises(raised):
                await ch.edit_placeholder_message("D1", "1.1", reply)
            with pytest.raises(raised):
                await ch.edit_message("D1", "1.1", "Searching the web")

    @pytest.mark.asyncio
    async def test_a_rejected_edit_keeps_the_retry_hints_of_a_rejected_send(self) -> None:
        ch = make_channel()
        rate_limited = err_json("ratelimited", headers={"Retry-After": "5"})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=rate_limited):
            with pytest.raises(RateLimitError) as limited:
                await ch.edit_message("D1", "1.1", "text")
        assert limited.value.retry_after == 5.0

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=err_json("internal_error")):
            with pytest.raises(ChannelSendError) as failed:
                await ch.edit_message("D1", "1.1", "text")
        assert failed.value.retriable is True

    @pytest.mark.asyncio
    async def test_the_thread_of_a_placeholder_is_one_the_bot_took_part_in(self) -> None:
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json({"ts": "1.1"})):
            await ch.send_placeholder("D1", "Thinking...", thread_id="9.9")

        assert ch._thread_tracker.contains("9.9")

    @pytest.mark.asyncio
    async def test_a_placeholder_outside_a_thread_sets_no_status(self) -> None:
        calls = await self._flow([], thread_id=None)

        assert [name for name, _ in calls] == ["chat.postMessage", "chat.update"]
        assert "thread_ts" not in calls[0][1]

    @pytest.mark.asyncio
    async def test_edit_message_uses_update(self) -> None:
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json()) as mock_post:
            await ch.edit_message("C_CHAN", "9999.0001", "Updated text")

        call_args = mock_post.call_args
        assert "chat.update" in str(call_args)

    @pytest.mark.asyncio
    async def test_edit_placeholder_message_uses_update(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="Final answer",
            user_id="U_USER",
        )
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json()) as mock_post:
            await ch.edit_placeholder_message("C_CHAN", "9999.0001", msg)

        call_args = mock_post.call_args
        assert "chat.update" in str(call_args)


class TestSlackAssistantThreadStatus:
    """Tests for assistant.threads.setStatus integration."""

    @pytest.mark.asyncio
    async def test_send_placeholder_sets_status(self) -> None:
        """send_placeholder with thread_id should call setStatus('is thinking...')."""
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json({"ts": "1234.5678"})) as mock_post:
            await ch.send_placeholder("C_CHAN", "thinking...", thread_id="1111.0000")

        calls = [str(c) for c in mock_post.call_args_list]
        assert any("assistant.threads.setStatus" in c for c in calls)
        assert ch._active_thread_status["C_CHAN"] == "1111.0000"

    @pytest.mark.asyncio
    async def test_send_placeholder_without_thread_skips_status(self) -> None:
        """send_placeholder without thread_id should NOT call setStatus."""
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json({"ts": "9999.0001"})) as mock_post:
            await ch.send_placeholder("C_CHAN", "thinking...")

        calls = [str(c) for c in mock_post.call_args_list]
        assert not any("assistant.threads.setStatus" in c for c in calls)
        assert len(ch._active_thread_status) == 0

    @pytest.mark.asyncio
    async def test_send_clears_status(self) -> None:
        """send() should clear assistant status after completion."""
        ch = make_channel()
        ch._active_thread_status["C_CHAN"] = "1111.0000"
        msg = OutboundMessage(channel="slack", recipient_id="C_CHAN", content="Hello", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json({"ts": "1.1"})) as mock_post:
            await ch.send(msg)

        assert "C_CHAN" not in ch._active_thread_status
        calls = [str(c) for c in mock_post.call_args_list]
        set_status_calls = [c for c in calls if "assistant.threads.setStatus" in c]
        assert len(set_status_calls) == 1
        assert '""' in set_status_calls[0] or "''" in set_status_calls[0]

    @pytest.mark.asyncio
    async def test_send_no_status_to_clear(self) -> None:
        """send() with no active status should not call setStatus."""
        ch = make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C_CHAN", content="Hello", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json({"ts": "1.1"})) as mock_post:
            await ch.send(msg)

        calls = [str(c) for c in mock_post.call_args_list]
        assert not any("assistant.threads.setStatus" in c for c in calls)

    @pytest.mark.asyncio
    async def test_edit_placeholder_clears_status_after_the_update(self) -> None:
        """edit_placeholder_message clears the status once the final reply is in place."""
        ch = make_channel()
        ch._active_thread_status["C_CHAN"] = "1111.0000"
        msg = OutboundMessage(channel="slack", recipient_id="C_CHAN", content="Final", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json()) as mock_post:
            await ch.edit_placeholder_message("C_CHAN", "1234.5678", msg)

        assert "C_CHAN" not in ch._active_thread_status
        calls = [str(c) for c in mock_post.call_args_list]
        assert any("assistant.threads.setStatus" in c for c in calls)

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_delete_message_clears_status(self) -> None:
        """delete_message should clear assistant status if active."""
        ch = make_channel()
        ch._active_thread_status["C_CHAN"] = "1111.0000"
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json()) as mock_post:
            await ch.delete_message("C_CHAN", "1234.5678")

        assert "C_CHAN" not in ch._active_thread_status
        calls = [str(c) for c in mock_post.call_args_list]
        assert any("chat.delete" in c for c in calls)
        assert any("assistant.threads.setStatus" in c for c in calls)

    @pytest.mark.asyncio
    async def test_clear_assistant_status_idempotent(self) -> None:
        """_clear_assistant_status should be safe to call when no status is active."""
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock) as mock_post:
            await ch._clear_assistant_status("C_CHAN")
        mock_post.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_set_thread_status(self) -> None:
        """api.set_thread_status should call the correct Slack API endpoint."""
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json()) as mock_post:
            result = await ch._api.set_thread_status("C_CHAN", "1111.0000", "is thinking...")
        assert result is True
        call_args = mock_post.call_args
        assert "assistant.threads.setStatus" in str(call_args)
        payload = call_args.kwargs.get("json", {})
        assert payload["channel_id"] == "C_CHAN"
        assert payload["thread_ts"] == "1111.0000"
        assert payload["status"] == "is thinking..."

    @pytest.mark.asyncio
    async def test_api_set_thread_status_failure(self) -> None:
        """api.set_thread_status should return False on failure."""
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=err_json("not_allowed")):
            result = await ch._api.set_thread_status("C_CHAN", "1111.0000", "thinking")
        assert result is False

    @pytest.mark.asyncio
    async def test_api_set_thread_status_exception(self) -> None:
        """api.set_thread_status should return False on exception."""
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=Exception("network")):
            result = await ch._api.set_thread_status("C_CHAN", "1111.0000", "thinking")
        assert result is False
