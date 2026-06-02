"""SlackChannel contract compliance + streaming / upload / lifecycle / inbound tests."""

from __future__ import annotations

import asyncio
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
from app.channels.providers.slack.helpers import (
    build_blocks,
    parse_block_action,
    parse_media_attachments,
    strip_mention,
    verify_slack_signature,
)
from app.channels.types import (
    ActionButton,
    ChannelStatus,
    MediaAttachment,
    OutboundMessage,
    SelectMenu,
    SelectOption,
)

from .channel_test_base import ChannelTestBase


def _make_channel() -> SlackChannel:
    ch = SlackChannel(bot_token="xoxb-test", app_token="xapp-test")
    ch._bot_user_id = "U_BOT"
    ch._team_id = "T_TEAM"
    return ch


def _ok_json(extra: dict[str, object] | None = None) -> httpx.Response:
    body: dict[str, object] = {"ok": True}
    if extra:
        body.update(extra)
    return httpx.Response(200, json=body)


def _err_json(error: str = "some_error", headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(200, json={"ok": False, "error": error}, headers=headers or {})


class TestSlackChannel(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return SlackChannel(
            bot_token="xoxb-test-token-for-unit-test",
            app_token="xapp-test-token-for-unit-test",
        )


class TestSlackNativeStreaming:
    """Tests for chat.startStream / appendStream / stopStream flow."""

    @pytest.mark.asyncio
    async def test_send_placeholder_uses_start_stream_with_thread(self) -> None:
        ch = _make_channel()
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json({"ts": "1234.5678"})
        ) as mock_post:
            ts = await ch.send_placeholder("C_CHAN", "thinking...", thread_id="1111.0000")

        assert ts == "1234.5678"
        assert "1234.5678" in ch._stream_sent
        call_args = mock_post.call_args
        assert "chat.startStream" in str(call_args)

    @pytest.mark.asyncio
    async def test_send_placeholder_fallback_without_thread(self) -> None:
        ch = _make_channel()
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json({"ts": "9999.0001"})
        ) as mock_post:
            ts = await ch.send_placeholder("C_CHAN", "thinking...")

        assert ts == "9999.0001"
        assert "9999.0001" not in ch._stream_sent
        call_args = mock_post.call_args
        assert "chat.postMessage" in str(call_args)

    @pytest.mark.asyncio
    async def test_send_placeholder_fallback_on_stream_error(self) -> None:
        ch = _make_channel()
        responses = [
            _ok_json(),                       # setStatus succeeds
            _err_json("not_allowed"),         # startStream fails
            _ok_json({"ts": "5555.0001"}),    # postMessage fallback
        ]
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=responses):
            ts = await ch.send_placeholder("C_CHAN", "thinking...", thread_id="1111.0000")

        assert ts == "5555.0001"
        assert "5555.0001" not in ch._stream_sent

    @pytest.mark.asyncio
    async def test_edit_message_uses_append_stream(self) -> None:
        ch = _make_channel()
        ch._stream_sent["1234.5678"] = "Hello"
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as mock_post:
            await ch.edit_message("C_CHAN", "1234.5678", "Hello world")

        assert ch._stream_sent["1234.5678"] == "Hello world"
        call_args = mock_post.call_args
        assert "chat.appendStream" in str(call_args)
        payload = call_args.kwargs.get("json", {})
        assert payload["markdown_text"] == " world"

    @pytest.mark.asyncio
    async def test_edit_message_fallback_on_non_prefix(self) -> None:
        """When new text is not a prefix extension, fall back to chat.update."""
        ch = _make_channel()
        ch._stream_sent["1234.5678"] = "Hello"
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as mock_post:
            await ch.edit_message("C_CHAN", "1234.5678", "Completely different")

        assert "1234.5678" not in ch._stream_sent
        call_args = mock_post.call_args
        assert "chat.update" in str(call_args)

    @pytest.mark.asyncio
    async def test_edit_message_fallback_on_append_failure(self) -> None:
        ch = _make_channel()
        ch._stream_sent["1234.5678"] = "Hello"
        responses = [_err_json("stream_expired"), _ok_json()]
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=responses):
            await ch.edit_message("C_CHAN", "1234.5678", "Hello world")

        assert "1234.5678" not in ch._stream_sent

    @pytest.mark.asyncio
    async def test_edit_message_no_stream_uses_update(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as mock_post:
            await ch.edit_message("C_CHAN", "9999.0001", "Updated text")

        call_args = mock_post.call_args
        assert "chat.update" in str(call_args)

    @pytest.mark.asyncio
    async def test_edit_placeholder_message_uses_stop_stream(self) -> None:
        ch = _make_channel()
        ch._stream_sent["1234.5678"] = "partial"
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="Final answer",
            user_id="U_USER",
        )
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as mock_post:
            await ch.edit_placeholder_message("C_CHAN", "1234.5678", msg)

        assert "1234.5678" not in ch._stream_sent
        call_args = mock_post.call_args
        assert "chat.stopStream" in str(call_args)

    @pytest.mark.asyncio
    async def test_edit_placeholder_message_fallback_no_stream(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="Final answer",
            user_id="U_USER",
        )
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as mock_post:
            await ch.edit_placeholder_message("C_CHAN", "9999.0001", msg)

        call_args = mock_post.call_args
        assert "chat.update" in str(call_args)

    @pytest.mark.asyncio
    async def test_edit_placeholder_message_stop_stream_failure_fallback(self) -> None:
        ch = _make_channel()
        ch._stream_sent["1234.5678"] = "partial"
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="Final answer",
            user_id="U_USER",
        )
        responses = [_err_json("stream_expired"), _ok_json()]
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=responses):
            await ch.edit_placeholder_message("C_CHAN", "1234.5678", msg)

        assert "1234.5678" not in ch._stream_sent


class TestSlackAssistantThreadStatus:
    """Tests for assistant.threads.setStatus integration."""

    @pytest.mark.asyncio
    async def test_send_placeholder_sets_status(self) -> None:
        """send_placeholder with thread_id should call setStatus('is thinking...')."""
        ch = _make_channel()
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json({"ts": "1234.5678"})
        ) as mock_post:
            await ch.send_placeholder("C_CHAN", "thinking...", thread_id="1111.0000")

        calls = [str(c) for c in mock_post.call_args_list]
        assert any("assistant.threads.setStatus" in c for c in calls)
        assert "C_CHAN" in ch._active_thread_status or "1234.5678" in ch._stream_sent

    @pytest.mark.asyncio
    async def test_send_placeholder_without_thread_skips_status(self) -> None:
        """send_placeholder without thread_id should NOT call setStatus."""
        ch = _make_channel()
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json({"ts": "9999.0001"})
        ) as mock_post:
            await ch.send_placeholder("C_CHAN", "thinking...")

        calls = [str(c) for c in mock_post.call_args_list]
        assert not any("assistant.threads.setStatus" in c for c in calls)
        assert len(ch._active_thread_status) == 0

    @pytest.mark.asyncio
    async def test_send_clears_status(self) -> None:
        """send() should clear assistant status after completion."""
        ch = _make_channel()
        ch._active_thread_status["C_CHAN"] = "1111.0000"
        msg = OutboundMessage(channel="slack", recipient_id="C_CHAN", content="Hello", user_id="U")
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json({"ts": "1.1"})
        ) as mock_post:
            await ch.send(msg)

        assert "C_CHAN" not in ch._active_thread_status
        calls = [str(c) for c in mock_post.call_args_list]
        set_status_calls = [c for c in calls if "assistant.threads.setStatus" in c]
        assert len(set_status_calls) == 1
        assert '""' in set_status_calls[0] or "''" in set_status_calls[0]

    @pytest.mark.asyncio
    async def test_send_no_status_to_clear(self) -> None:
        """send() with no active status should not call setStatus."""
        ch = _make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C_CHAN", content="Hello", user_id="U")
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json({"ts": "1.1"})
        ) as mock_post:
            await ch.send(msg)

        calls = [str(c) for c in mock_post.call_args_list]
        assert not any("assistant.threads.setStatus" in c for c in calls)

    @pytest.mark.asyncio
    async def test_edit_placeholder_clears_status_on_stop_stream(self) -> None:
        """edit_placeholder_message should clear status after stop_stream succeeds."""
        ch = _make_channel()
        ch._stream_sent["1234.5678"] = "partial"
        ch._active_thread_status["C_CHAN"] = "1111.0000"
        msg = OutboundMessage(channel="slack", recipient_id="C_CHAN", content="Final", user_id="U")
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()
        ) as mock_post:
            await ch.edit_placeholder_message("C_CHAN", "1234.5678", msg)

        assert "C_CHAN" not in ch._active_thread_status
        calls = [str(c) for c in mock_post.call_args_list]
        assert any("assistant.threads.setStatus" in c for c in calls)

    @pytest.mark.asyncio
    async def test_edit_placeholder_clears_status_on_fallback(self) -> None:
        """edit_placeholder_message should clear status even on fallback to edit_message."""
        ch = _make_channel()
        ch._active_thread_status["C_CHAN"] = "1111.0000"
        msg = OutboundMessage(channel="slack", recipient_id="C_CHAN", content="Final", user_id="U")
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()
        ) as mock_post:
            await ch.edit_placeholder_message("C_CHAN", "9999.0001", msg)

        assert "C_CHAN" not in ch._active_thread_status
        calls = [str(c) for c in mock_post.call_args_list]
        assert any("assistant.threads.setStatus" in c for c in calls)

    @pytest.mark.asyncio
    async def test_delete_message_clears_status(self) -> None:
        """delete_message should clear assistant status if active."""
        ch = _make_channel()
        ch._active_thread_status["C_CHAN"] = "1111.0000"
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()
        ) as mock_post:
            await ch.delete_message("C_CHAN", "1234.5678")

        assert "C_CHAN" not in ch._active_thread_status
        calls = [str(c) for c in mock_post.call_args_list]
        assert any("chat.delete" in c for c in calls)
        assert any("assistant.threads.setStatus" in c for c in calls)

    @pytest.mark.asyncio
    async def test_clear_assistant_status_idempotent(self) -> None:
        """_clear_assistant_status should be safe to call when no status is active."""
        ch = _make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock) as mock_post:
            await ch._clear_assistant_status("C_CHAN")
        mock_post.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_set_thread_status(self) -> None:
        """api.set_thread_status should call the correct Slack API endpoint."""
        ch = _make_channel()
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()
        ) as mock_post:
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
        ch = _make_channel()
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json("not_allowed")
        ):
            result = await ch._api.set_thread_status("C_CHAN", "1111.0000", "thinking")
        assert result is False

    @pytest.mark.asyncio
    async def test_api_set_thread_status_exception(self) -> None:
        """api.set_thread_status should return False on exception."""
        ch = _make_channel()
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, side_effect=Exception("network")
        ):
            result = await ch._api.set_thread_status("C_CHAN", "1111.0000", "thinking")
        assert result is False


class TestSlackFileUpload:
    """Tests for the 3-step external upload flow."""

    @pytest.mark.asyncio
    async def test_upload_file_3step_flow(self, tmp_path: object) -> None:
        import pathlib

        test_file = pathlib.Path(str(tmp_path)) / "test.txt"
        test_file.write_text("hello")

        ch = _make_channel()
        attachment = MediaAttachment(
            media_type="document",
            path=str(test_file),
            filename="test.txt",
        )

        step1_resp = _ok_json({"upload_url": "https://files.slack.com/upload/xxx", "file_id": "F123"})
        put_resp = httpx.Response(200)
        step3_resp = _ok_json()

        with (
            patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=[step1_resp, step3_resp]),
            patch.object(ch._api._http, "put", new_callable=AsyncMock, return_value=put_resp) as mock_put,
        ):
            await ch._api.upload_file("C_CHAN", attachment, None)

        mock_put.assert_called_once()
        put_call = mock_put.call_args
        assert "https://files.slack.com/upload/xxx" in str(put_call)

    @pytest.mark.asyncio
    async def test_upload_file_step1_failure(self) -> None:
        import pathlib
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"data")
            fpath = f.name

        ch = _make_channel()
        attachment = MediaAttachment(media_type="document", path=fpath, filename="f.txt")

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json("not_allowed")):
            await ch._api.upload_file("C_CHAN", attachment, None)

        pathlib.Path(fpath).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_upload_file_empty_attachment(self) -> None:
        ch = _make_channel()
        attachment = MediaAttachment(media_type="document")
        await ch._api.upload_file("C_CHAN", attachment, None)


class TestSlackFetchBotInfo:
    """Test that auth_test captures bot_user_id and team_id."""

    @pytest.mark.asyncio
    async def test_auth_test_captures_team_id(self) -> None:
        ch = _make_channel()
        ch._team_id = ""
        resp = _ok_json({"user_id": "U_BOT2", "team_id": "T_NEW"})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=resp):
            info = await ch._api.auth_test()

        assert info["user_id"] == "U_BOT2"
        assert info["team_id"] == "T_NEW"


class TestSlackHelpers:
    """Tests for pure-function helpers."""

    def test_strip_mention_removes_bot_id(self) -> None:
        assert strip_mention("<@U_BOT> hello world", "U_BOT") == "hello world"

    def test_strip_mention_no_bot_id(self) -> None:
        assert strip_mention("hello world", "") == "hello world"

    def test_strip_mention_no_match(self) -> None:
        assert strip_mention("hello world", "U_OTHER") == "hello world"

    def test_verify_signature_valid(self) -> None:
        import hashlib as _hashlib
        import hmac as _hmac

        secret = "test_secret"
        body = b'{"event":"test"}'
        ts = "1234567890"
        basestring = f"v0:{ts}:{body.decode('utf-8')}"
        sig = "v0=" + _hmac.new(secret.encode(), basestring.encode(), _hashlib.sha256).hexdigest()
        assert verify_slack_signature(secret, body, ts, sig) is True

    def test_verify_signature_invalid(self) -> None:
        assert verify_slack_signature("secret", b"body", "123", "v0=wrong") is False

    def test_verify_signature_no_secret(self) -> None:
        assert verify_slack_signature("", b"body", "123", "anything") is True

    def test_parse_block_action_valid(self) -> None:
        payload: dict[str, object] = {
            "user": {"id": "U_USER", "name": "testuser"},
            "channel": {"id": "C_CHAN"},
            "actions": [{"action_id": "btn_1", "type": "button"}],
            "message": {"ts": "1234.5678"},
            "trigger_id": "T_TRIGGER",
        }
        result = parse_block_action(payload, "U_BOT")
        assert result is not None
        assert result["user_id"] == "U_USER"
        assert result["content"] == "btn_1"

    def test_parse_block_action_ignores_bot(self) -> None:
        payload: dict[str, object] = {
            "user": {"id": "U_BOT"},
            "actions": [{"action_id": "btn_1", "type": "button"}],
        }
        assert parse_block_action(payload, "U_BOT") is None

    def test_build_blocks_empty(self) -> None:
        msg = OutboundMessage(channel="slack", recipient_id="C", content="text", user_id="U")
        assert build_blocks(msg) is None

    def test_build_blocks_with_button(self) -> None:
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C",
            content="text",
            user_id="U",
            components=((ActionButton(label="Click", action_id="btn_1"),),),
        )
        blocks = build_blocks(msg)
        assert blocks is not None
        assert len(blocks) == 1
        assert blocks[0]["type"] == "actions"
        elements = blocks[0]["elements"]
        assert isinstance(elements, list)
        assert len(elements) == 1
        assert elements[0]["type"] == "button"
        assert elements[0]["action_id"] == "act:btn_1"

    def test_build_blocks_with_button_url(self) -> None:
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C",
            content="text",
            user_id="U",
            components=((ActionButton(label="Open", action_id="btn_url", url="https://example.com"),),),
        )
        blocks = build_blocks(msg)
        assert blocks is not None
        assert blocks[0]["elements"][0]["url"] == "https://example.com"

    def test_build_blocks_with_select_menu(self) -> None:
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C",
            content="text",
            user_id="U",
            components=(
                (
                    SelectMenu(
                        action_id="sel_1",
                        placeholder="Pick one",
                        options=(
                            SelectOption(label="A", value="a"),
                            SelectOption(label="B", value="b"),
                        ),
                    ),
                ),
            ),
        )
        blocks = build_blocks(msg)
        assert blocks is not None
        el = blocks[0]["elements"][0]
        assert el["type"] == "static_select"
        assert el["action_id"] == "sel:sel_1"
        assert len(el["options"]) == 2

    def test_parse_media_attachments(self) -> None:
        event: dict[str, object] = {
            "files": [
                {"mimetype": "image/png", "name": "pic.png", "url_private": "https://files.slack.com/pic.png"},
                {"mimetype": "application/pdf", "name": "doc.pdf", "url_private": "https://files.slack.com/doc.pdf"},
            ]
        }
        result = parse_media_attachments(event)
        assert len(result) == 2
        assert result[0].filename == "pic.png"
        assert result[0].mime_type == "image/png"
        assert result[1].filename == "doc.pdf"

    def test_parse_media_attachments_no_files(self) -> None:
        assert parse_media_attachments({}) == []

    def test_parse_media_attachments_invalid_files(self) -> None:
        assert parse_media_attachments({"files": "not_a_list"}) == []

    def test_parse_block_action_static_select(self) -> None:
        payload: dict[str, object] = {
            "user": {"id": "U_USER", "name": "testuser"},
            "channel": {"id": "C_CHAN"},
            "actions": [{"action_id": "sel_1", "type": "static_select", "selected_option": {"value": "opt_a"}}],
            "message": {"ts": "1234.5678"},
            "trigger_id": "T_TRIGGER",
        }
        result = parse_block_action(payload, "U_BOT")
        assert result is not None
        assert result["content"] == "opt_a"

    def test_parse_block_action_no_actions(self) -> None:
        payload: dict[str, object] = {
            "user": {"id": "U_USER"},
            "actions": [],
        }
        assert parse_block_action(payload, "U_BOT") is None

    def test_parse_block_action_no_user(self) -> None:
        payload: dict[str, object] = {
            "user": "not_a_dict",
            "actions": [{"action_id": "btn_1", "type": "button"}],
        }
        assert parse_block_action(payload, "U_BOT") is None


class TestSlackDiagnostics:
    """Tests for collect_issues and thread_tracker_metrics."""

    def test_collect_issues_missing_both_tokens(self) -> None:
        ch = SlackChannel(bot_token="", app_token="")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert "Bot Token" in issues[0].message
        assert "App-Level Token" in issues[0].message

    def test_collect_issues_missing_app_token(self) -> None:
        ch = SlackChannel(bot_token="xoxb-test", app_token="")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert "App-Level Token" in issues[0].message

    def test_collect_issues_healthy(self) -> None:
        ch = _make_channel()
        issues = ch.collect_issues()
        assert len(issues) == 0

    def test_collect_issues_runtime_error(self) -> None:
        ch = _make_channel()
        ch.health.last_error = "Connection timed out"
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].message == "Connection timed out"

    def test_thread_tracker_metrics(self) -> None:
        ch = _make_channel()
        metrics = ch.thread_tracker_metrics
        assert metrics.current_size == 0


class TestSlackLifecycle:
    """Tests for start/stop/health_check lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = SlackChannel(bot_token="xoxb-test")
        resp = _ok_json({"user_id": "U_BOT", "team_id": "T_TEAM"})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=resp):
            await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._bot_user_id == "U_BOT"
        assert ch._team_id == "T_TEAM"
        await ch._api._http.aclose()

    @pytest.mark.asyncio
    async def test_start_no_token(self) -> None:
        ch = SlackChannel(bot_token="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING
        await ch._api._http.aclose()

    @pytest.mark.asyncio
    async def test_start_auth_failure(self) -> None:
        ch = SlackChannel(bot_token="xoxb-test")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json("invalid_auth")):
            await ch.start()
        assert ch._status == ChannelStatus.ERROR
        await ch._api._http.aclose()

    @pytest.mark.asyncio
    async def test_start_with_socket_mode(self) -> None:
        ch = SlackChannel(bot_token="xoxb-test", app_token="xapp-test")
        resp = _ok_json({"user_id": "U_BOT", "team_id": "T_TEAM"})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=resp):
            await ch.start()
        assert ch._status == ChannelStatus.RUNNING
        assert ch._socket_task is not None
        ch._socket_task.cancel()
        try:
            await ch._socket_task
        except (asyncio.CancelledError, Exception):
            pass
        await ch._api._http.aclose()

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_stop_cancels_socket_task(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING

        async def _forever() -> None:
            await asyncio.sleep(999)

        ch._socket_task = asyncio.create_task(_forever())
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED
        assert ch._socket_task.cancelled() or ch._socket_task.done()

    @pytest.mark.asyncio
    async def test_health_check_ok(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()):
            assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_not_running(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_api_failure(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json()):
            assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=Exception("network")):
            assert await ch.health_check() is False


class TestSlackSend:
    """Tests for the send() method — text, blocks, media, error handling."""

    @pytest.mark.asyncio
    async def test_send_text_only(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C_CHAN", content="Hello", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json({"ts": "1.1"})):
            ts = await ch.send(msg)
        assert ts == "1.1"

    @pytest.mark.asyncio
    async def test_send_with_thread_ts(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="Reply",
            user_id="U",
            metadata={"thread_ts": "0.0"},
        )
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json({"ts": "2.2"})
        ) as mock_post:
            await ch.send(msg)
        payload = mock_post.call_args.kwargs.get("json", {})
        assert payload.get("thread_ts") == "0.0"

    @pytest.mark.asyncio
    async def test_send_with_reply_to_id(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="Reply",
            user_id="U",
            reply_to_id="parent.ts",
        )
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json({"ts": "3.3"})
        ) as mock_post:
            await ch.send(msg)
        payload = mock_post.call_args.kwargs.get("json", {})
        assert payload.get("thread_ts") == "parent.ts"

    @pytest.mark.asyncio
    async def test_send_with_blocks(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="Pick",
            user_id="U",
            components=((ActionButton(label="Go", action_id="go"),),),
        )
        with patch.object(
            ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json({"ts": "4.4"})
        ) as mock_post:
            await ch.send(msg)
        payload = mock_post.call_args.kwargs.get("json", {})
        assert "blocks" in payload

    @pytest.mark.asyncio
    async def test_send_with_media(self) -> None:
        import pathlib
        import tempfile

        ch = _make_channel()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"data")
            fpath = f.name

        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="",
            user_id="U",
            media=(MediaAttachment(media_type="document", path=fpath, filename="f.txt"),),
        )
        step1 = _ok_json({"upload_url": "https://up.slack.com/x", "file_id": "F1"})
        step3 = _ok_json()
        put_resp = httpx.Response(200)
        with (
            patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=[step1, step3]),
            patch.object(ch._api._http, "put", new_callable=AsyncMock, return_value=put_resp),
        ):
            await ch.send(msg)
        pathlib.Path(fpath).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_send_auth_error(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C", content="Hi", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json("token_revoked")):
            with pytest.raises(ChannelAuthError):
                await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_rate_limit_error(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C", content="Hi", user_id="U")
        resp = httpx.Response(200, json={"ok": False, "error": "ratelimited"}, headers={"Retry-After": "5"})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(RateLimitError):
                await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_retriable_error(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C", content="Hi", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json("internal_error")):
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)
            assert exc_info.value.retriable is True

    @pytest.mark.asyncio
    async def test_send_non_retriable_error(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C", content="Hi", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json("channel_not_found")):
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)
            assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_send_empty_content_with_media(self) -> None:
        """send() with no content but media should still upload files."""
        import pathlib
        import tempfile

        ch = _make_channel()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"data")
            fpath = f.name

        msg = OutboundMessage(
            channel="slack",
            recipient_id="C",
            content="",
            user_id="U",
            media=(MediaAttachment(media_type="document", path=fpath, filename="f.txt"),),
        )
        step1 = _ok_json({"upload_url": "https://up.slack.com/x", "file_id": "F1"})
        step3 = _ok_json()
        put_resp = httpx.Response(200)
        with (
            patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=[step1, step3]),
            patch.object(ch._api._http, "put", new_callable=AsyncMock, return_value=put_resp) as mock_put,
        ):
            result = await ch.send(msg)
        assert result is None
        mock_put.assert_called_once()
        pathlib.Path(fpath).unlink(missing_ok=True)


class TestSlackUploadExtended:
    """Extended upload tests for URL download path and edge cases."""

    @pytest.mark.asyncio
    async def test_upload_file_from_url(self) -> None:
        from unittest.mock import MagicMock

        ch = _make_channel()
        attachment = MediaAttachment(
            media_type="image",
            url="https://example.com/img.png",
            filename="img.png",
        )
        step1 = _ok_json({"upload_url": "https://up.slack.com/x", "file_id": "F2"})
        step3 = _ok_json()
        put_resp = httpx.Response(200)

        with (
            patch(
                "app.channels.media.downloader.MediaDownloader.download",
                new_callable=AsyncMock,
            ) as mock_download,
            patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=[step1, step3]),
            patch.object(ch._api._http, "put", new_callable=AsyncMock, return_value=put_resp) as mock_put,
        ):
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.data = b"image-bytes"
            mock_download.return_value = mock_result

            await ch._api.upload_file("C_CHAN", attachment, None)
        mock_put.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_file_put_failure(self) -> None:
        import pathlib
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"data")
            fpath = f.name

        ch = _make_channel()
        attachment = MediaAttachment(media_type="document", path=fpath, filename="f.txt")
        step1 = _ok_json({"upload_url": "https://up.slack.com/x", "file_id": "F3"})
        put_resp = httpx.Response(500)
        with (
            patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=step1),
            patch.object(ch._api._http, "put", new_callable=AsyncMock, return_value=put_resp),
        ):
            await ch._api.upload_file("C_CHAN", attachment, None)
        pathlib.Path(fpath).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_upload_file_with_thread_and_caption(self) -> None:
        import pathlib
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"data")
            fpath = f.name

        ch = _make_channel()
        attachment = MediaAttachment(
            media_type="document",
            path=fpath,
            filename="f.txt",
            caption="See this",
        )
        step1 = _ok_json({"upload_url": "https://up.slack.com/x", "file_id": "F4"})
        step3 = _ok_json()
        put_resp = httpx.Response(200)
        with (
            patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=[step1, step3]) as mock_post,
            patch.object(ch._api._http, "put", new_callable=AsyncMock, return_value=put_resp),
        ):
            await ch._api.upload_file("C_CHAN", attachment, "thread.ts")
        complete_call = mock_post.call_args_list[-1]
        payload = complete_call.kwargs.get("json", {})
        assert payload.get("initial_comment") == "See this"
        assert payload.get("thread_ts") == "thread.ts"
        pathlib.Path(fpath).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_upload_file_exception(self) -> None:
        ch = _make_channel()
        attachment = MediaAttachment(
            media_type="image",
            url="https://example.com/img.png",
            filename="img.png",
        )
        with patch.object(ch._api._http, "get", new_callable=AsyncMock, side_effect=Exception("network")):
            await ch._api.upload_file("C_CHAN", attachment, None)


class TestSlackDeleteReact:
    """Tests for delete_message and react_to_message."""

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as mock_post:
            await ch.delete_message("C_CHAN", "1234.5678")
        assert "chat.delete" in str(mock_post.call_args)

    @pytest.mark.asyncio
    async def test_delete_message_failure(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json()):
            await ch.delete_message("C_CHAN", "1234.5678")

    @pytest.mark.asyncio
    async def test_react_to_message(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as mock_post:
            await ch.react_to_message("C_CHAN", "1234.5678", ":thumbsup:")
        payload = mock_post.call_args.kwargs.get("json", {})
        assert payload["name"] == "thumbsup"

    @pytest.mark.asyncio
    async def test_react_to_message_empty_emoji(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock) as mock_post:
            await ch.react_to_message("C_CHAN", "1234.5678", "")
        mock_post.assert_not_called()

    @pytest.mark.asyncio
    async def test_react_to_message_failure(self) -> None:
        ch = _make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_err_json()):
            await ch.react_to_message("C_CHAN", "1234.5678", "wave")


class TestSlackInbound:
    """Tests for handle_event, _handle_block_actions, _parse_message_event."""

    @pytest.mark.asyncio
    async def test_handle_event_url_verification(self) -> None:
        ch = _make_channel()
        result = await ch.handle_event({"type": "url_verification", "challenge": "abc123"})
        assert result == {"challenge": "abc123"}

    @pytest.mark.asyncio
    async def test_handle_event_message(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        event_data: dict[str, object] = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U_USER",
                "text": "<@U_BOT> hello",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "1234.5678",
            },
        }
        result = await ch.handle_event(event_data)
        assert result is None
        assert len(emitted) == 1
        msg = emitted[0]
        assert msg.content == "hello"
        assert msg.sender_id == "U_USER"
        assert msg.mentioned is True

    @pytest.mark.asyncio
    async def test_handle_event_ignores_bot_message(self) -> None:
        ch = _make_channel()
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]
        event_data: dict[str, object] = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U_BOT",
                "text": "bot reply",
                "channel": "C_CHAN",
                "ts": "1234.5678",
            },
        }
        await ch.handle_event(event_data)
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_event_ignores_subtype(self) -> None:
        ch = _make_channel()
        ch._emit_inbound = AsyncMock()  # type: ignore[assignment]
        event_data: dict[str, object] = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "subtype": "message_changed",
                "user": "U_USER",
                "text": "edited",
                "channel": "C_CHAN",
                "ts": "1234.5678",
            },
        }
        await ch.handle_event(event_data)
        ch._emit_inbound.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_event_block_actions(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        payload: dict[str, object] = {
            "type": "block_actions",
            "user": {"id": "U_USER", "name": "testuser"},
            "channel": {"id": "C_CHAN"},
            "actions": [{"action_id": "approve", "type": "button"}],
            "message": {"ts": "1234.5678"},
            "trigger_id": "T_TRIGGER",
        }
        result = await ch.handle_event(payload)
        assert result is None
        assert len(emitted) == 1
        assert emitted[0].content == "approve"

    @pytest.mark.asyncio
    async def test_handle_event_invalid_event(self) -> None:
        ch = _make_channel()
        result = await ch.handle_event({"type": "event_callback", "event": "not_a_dict"})
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_message_event_with_thread(self) -> None:
        ch = _make_channel()
        event: dict[str, object] = {
            "type": "message",
            "user": "U_USER",
            "text": "reply in thread",
            "channel": "C_CHAN",
            "channel_type": "im",
            "ts": "2222.0001",
            "thread_ts": "1111.0000",
        }
        msg = await ch._parse_message_event(event)
        assert msg is not None
        assert msg.thread_id == "1111.0000"
        assert msg.reply_to_id == "1111.0000"
        assert msg.is_group is False

    @pytest.mark.asyncio
    async def test_parse_message_event_with_media(self) -> None:
        ch = _make_channel()
        event: dict[str, object] = {
            "type": "message",
            "user": "U_USER",
            "text": "",
            "channel": "C_CHAN",
            "channel_type": "channel",
            "ts": "3333.0001",
            "files": [
                {"mimetype": "image/jpeg", "name": "photo.jpg", "url_private": "https://files.slack.com/photo.jpg"}
            ],
        }
        msg = await ch._parse_message_event(event)
        assert msg is not None
        assert len(msg.media) == 1
        assert msg.media[0].filename == "photo.jpg"

    @pytest.mark.asyncio
    async def test_parse_message_event_empty_text_no_media(self) -> None:
        ch = _make_channel()
        event: dict[str, object] = {
            "type": "message",
            "user": "U_USER",
            "text": "  ",
            "channel": "C_CHAN",
            "ts": "4444.0001",
        }
        msg = await ch._parse_message_event(event)
        assert msg is None

    def test_verify_request(self) -> None:
        ch = SlackChannel(bot_token="xoxb-test", signing_secret="mysecret")
        with patch(
            "app.channels.providers.slack.channel.verify_slack_signature",
            return_value=True,
        ):
            assert ch.verify_request(b"body", "123", "v0=sig") is True


class TestSlackMentionAnnotation:
    """Tests for _annotate_mentions."""

    @pytest.mark.asyncio
    async def test_annotate_mentions_no_mentions(self) -> None:
        ch = _make_channel()
        result = await ch._annotate_mentions("hello world")
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_annotate_mentions_empty_text(self) -> None:
        ch = _make_channel()
        result = await ch._annotate_mentions("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_annotate_mentions_with_resolution(self) -> None:
        ch = _make_channel()
        with patch.object(
            ch._user_resolver,
            "resolve_batch",
            new_callable=AsyncMock,
            return_value={"UABC": "Alice"},
        ):
            result = await ch._annotate_mentions("Hey <@UABC> check this")
        assert result == "Hey <@UABC> (Alice) check this"

    @pytest.mark.asyncio
    async def test_annotate_mentions_resolution_fails(self) -> None:
        ch = _make_channel()
        with patch.object(
            ch._user_resolver,
            "resolve_batch",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await ch._annotate_mentions("Hey <@UABC> check this")
        assert result == "Hey <@UABC> check this"

    @pytest.mark.asyncio
    async def test_annotate_mentions_deduplicates(self) -> None:
        ch = _make_channel()
        with patch.object(
            ch._user_resolver,
            "resolve_batch",
            new_callable=AsyncMock,
            return_value={"UABC": "Alice"},
        ) as mock_resolve:
            await ch._annotate_mentions("<@UABC> and <@UABC> again")
        args = mock_resolve.call_args[0][0]
        assert args == ["UABC"]

    @pytest.mark.asyncio
    async def test_annotate_mentions_limit(self) -> None:
        ch = _make_channel()
        ch._mention_annotation_limit = 2
        many_mentions = " ".join(f"<@U{i:04d}>" for i in range(5))
        with patch.object(
            ch._user_resolver,
            "resolve_batch",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_resolve:
            await ch._annotate_mentions(many_mentions)
        args = mock_resolve.call_args[0][0]
        assert len(args) == 2


class TestSlackBlockActionsTimestamp:
    """Tests for _handle_block_actions timestamp parsing."""

    @pytest.mark.asyncio
    async def test_block_action_uses_message_ts(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        payload: dict[str, object] = {
            "type": "block_actions",
            "user": {"id": "U_USER", "name": "test"},
            "channel": {"id": "C_CHAN"},
            "actions": [{"action_id": "btn", "type": "button"}],
            "message": {"ts": "1700000000.000"},
            "trigger_id": "T_TRIG",
        }
        await ch.handle_event(payload)
        assert len(emitted) == 1
        assert emitted[0].sent_at == 1700000000.0

    @pytest.mark.asyncio
    async def test_block_action_invalid_ts(self) -> None:
        ch = _make_channel()
        emitted: list[object] = []
        ch._emit_inbound = AsyncMock(side_effect=lambda msg: emitted.append(msg))  # type: ignore[assignment]
        payload: dict[str, object] = {
            "type": "block_actions",
            "user": {"id": "U_USER", "name": "test"},
            "channel": {"id": "C_CHAN"},
            "actions": [{"action_id": "btn", "type": "button"}],
            "message": {"ts": "not_a_number"},
            "trigger_id": "T_TRIG",
        }
        await ch.handle_event(payload)
        assert len(emitted) == 1


class TestSlackThreadTracker:
    """Tests for ThreadTracker LRU cache and metrics."""

    def test_add_and_contains(self) -> None:
        from app.channels.providers.slack.thread_tracker import ThreadTracker

        tracker = ThreadTracker(max_size=3)
        tracker.add("t1")
        tracker.add("t2")
        assert tracker.contains("t1") is True
        assert tracker.contains("t3") is False

    def test_lru_eviction(self) -> None:
        from app.channels.providers.slack.thread_tracker import ThreadTracker

        tracker = ThreadTracker(max_size=2)
        tracker.add("t1")
        tracker.add("t2")
        tracker.add("t3")  # evicts t1
        assert tracker.contains("t1") is False
        assert tracker.contains("t2") is True
        assert tracker.contains("t3") is True

    def test_metrics_hit_rate(self) -> None:
        from app.channels.providers.slack.thread_tracker import ThreadTracker

        tracker = ThreadTracker()
        tracker.add("t1")
        tracker.contains("t1")  # hit
        tracker.contains("t2")  # miss
        assert tracker.metrics.hit_count == 1
        assert tracker.metrics.miss_count == 1
        assert tracker.metrics.get_hit_rate() == 0.5

    def test_metrics_zero_division(self) -> None:
        from app.channels.providers.slack.thread_tracker import ThreadTrackerMetrics

        metrics = ThreadTrackerMetrics()
        assert metrics.get_hit_rate() == 0.0

    def test_move_to_end_on_add(self) -> None:
        from app.channels.providers.slack.thread_tracker import ThreadTracker

        tracker = ThreadTracker(max_size=2)
        tracker.add("t1")
        tracker.add("t2")
        tracker.add("t1")  # move t1 to end
        tracker.add("t3")  # evicts t2 (oldest)
        assert tracker.contains("t1") is True
        assert tracker.contains("t2") is False
        assert tracker.contains("t3") is True


class TestSlackThreadAutoReply:
    """Tests for thread auto-reply (Task #60) — replies without @mention."""

    @pytest.mark.asyncio
    async def test_thread_reply_bot_initiated_no_mention(self) -> None:
        """Thread initiated by bot → replies auto-respond without @mention."""
        ch = _make_channel()

        # Mock _fetch_thread_parent to return bot as sender
        parent_resp = _ok_json(
            {
                "messages": [
                    {
                        "user": "U_BOT",
                        "text": "Bot started this thread",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=parent_resp):
            event: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply without mention",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            msg = await ch._parse_message_event(event)

        assert msg is not None
        assert msg.mentioned is True  # Auto-reply enabled
        assert msg.content == "reply without mention"

    @pytest.mark.asyncio
    async def test_thread_reply_parent_has_mention_no_current_mention(self) -> None:
        """Parent has @mention → replies auto-respond without @mention."""
        ch = _make_channel()

        parent_resp = _ok_json(
            {
                "messages": [
                    {
                        "user": "U_USER",
                        "text": "<@U_BOT> please help",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=parent_resp):
            event: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "follow up question",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0002",
                "thread_ts": "1111.0000",
            }
            msg = await ch._parse_message_event(event)

        assert msg is not None
        assert msg.mentioned is True
        assert msg.content == "follow up question"

    @pytest.mark.asyncio
    async def test_thread_reply_unrelated_thread_requires_mention(self) -> None:
        """Unrelated thread (not bot-initiated, no parent @mention) → requires @mention."""
        ch = _make_channel()

        parent_resp = _ok_json(
            {
                "messages": [
                    {
                        "user": "U_OTHER",
                        "text": "unrelated topic",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=parent_resp):
            event: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply without mention",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0003",
                "thread_ts": "1111.0000",
            }
            msg = await ch._parse_message_event(event)

        assert msg is not None
        assert msg.mentioned is False  # No auto-reply

    @pytest.mark.asyncio
    async def test_thread_reply_cache_hit(self) -> None:
        """LRU Cache: Second call should not trigger API request."""
        ch = _make_channel()

        parent_resp = _ok_json(
            {
                "messages": [
                    {
                        "user": "U_BOT",
                        "text": "Bot started",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        mock_post = AsyncMock(return_value=parent_resp)
        with patch.object(ch._api._http, "post", mock_post):
            # First call: API request
            event1: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 1",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            msg1 = await ch._parse_message_event(event1)
            assert msg1 is not None
            assert msg1.mentioned is True

            # Second call: Cache hit (no API request)
            event2: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 2",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0002",
                "thread_ts": "1111.0000",
            }
            msg2 = await ch._parse_message_event(event2)
            assert msg2 is not None
            assert msg2.mentioned is True

        # Verify 2 API calls (parent fetch + users.info on first event, all cached on second)
        # First event: 1 conversations.history + 1 users.info = 2 calls
        # Second event: both cached = 0 calls
        # Total: 2 calls
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_thread_reply_cache_ttl_expired(self) -> None:
        """LRU Cache: Expired cache should trigger new API request."""
        ch = _make_channel()
        ch._cache_ttl = 0.1  # 100ms TTL for test

        parent_resp = _ok_json(
            {
                "messages": [
                    {
                        "user": "U_BOT",
                        "text": "Bot started",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        mock_post = AsyncMock(return_value=parent_resp)
        with patch.object(ch._api._http, "post", mock_post):
            event1: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 1",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            await ch._parse_message_event(event1)

            # Wait for TTL expiration
            await asyncio.sleep(0.15)

            event2: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 2",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0002",
                "thread_ts": "1111.0000",
            }
            await ch._parse_message_event(event2)

        # Verify 3 API calls
        # First event: 1 conversations.history + 1 users.info = 2 calls
        # Second event (after TTL): 1 conversations.history (expired) + 0 users.info (still valid, 1h TTL) = 1 call
        # Total: 3 calls
        assert mock_post.call_count == 3

    @pytest.mark.asyncio
    async def test_thread_reply_lru_eviction(self) -> None:
        """LRU Cache: Oldest entry should be evicted when cache exceeds max size."""
        ch = _make_channel()
        ch._cache_max_size = 2

        parent_resp = _ok_json(
            {
                "messages": [
                    {
                        "user": "U_BOT",
                        "text": "Bot message",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=parent_resp):
            # Add 3 entries (exceeds max_size=2)
            for i in range(3):
                event: dict[str, object] = {
                    "type": "message",
                    "user": "U_USER",
                    "text": f"reply {i}",
                    "channel": "C_CHAN",
                    "channel_type": "channel",
                    "ts": f"{2222 + i}.0001",
                    "thread_ts": f"{1111 + i}.0000",
                }
                await ch._parse_message_event(event)

        # Verify cache size does not exceed max_size
        assert len(ch._thread_parent_cache) <= ch._cache_max_size

    @pytest.mark.asyncio
    async def test_thread_reply_cache_none_result(self) -> None:
        """Cache should also store None results (failed API calls)."""
        ch = _make_channel()

        parent_resp = _ok_json({"messages": []})  # Empty messages (parent not found)

        mock_post = AsyncMock(return_value=parent_resp)
        with patch.object(ch._api._http, "post", mock_post):
            # First call: API request returns None
            event1: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 1",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            msg1 = await ch._parse_message_event(event1)
            assert msg1 is not None
            assert msg1.mentioned is False  # No parent found

            # Second call: Cache hit (no API request)
            event2: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 2",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0002",
                "thread_ts": "1111.0000",
            }
            msg2 = await ch._parse_message_event(event2)
            assert msg2 is not None
            assert msg2.mentioned is False

        # Verify only 1 API call (cache hit on second, even for None result)
        assert mock_post.call_count == 1

    @pytest.mark.asyncio
    async def test_thread_reply_sender_name_resolved(self) -> None:
        """Thread parent sender_name should be resolved via UserResolver."""
        ch = _make_channel()

        # Mock conversations.history response (parent message)
        parent_resp = _ok_json(
            {
                "messages": [
                    {
                        "user": "U_PARENT",
                        "text": "Parent message",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        # Mock users.info response (parent sender name)
        user_resp = _ok_json(
            {
                "user": {
                    "id": "U_PARENT",
                    "profile": {
                        "display_name": "Parent User",
                        "real_name": "Parent Real Name",
                    },
                }
            }
        )

        # Mock API: first call (conversations.history), second call (users.info)
        mock_post = AsyncMock(side_effect=[parent_resp, user_resp])

        with patch.object(ch._api._http, "post", mock_post):
            event: dict[str, object] = {
                "type": "message",
                "user": "U_REPLY",
                "text": "Reply to thread",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            msg = await ch._parse_message_event(event)

            # Verify InboundMessage has reply_to with sender_name
            assert msg is not None
            assert msg.reply_to is not None
            assert msg.reply_to.message_id == "1111.0000"
            assert msg.reply_to.content == "Parent message"
            assert msg.reply_to.sender_id == "U_PARENT"
            assert msg.reply_to.sender_name == "Parent User"  # Resolved via UserResolver!

        # Verify 2 API calls: conversations.history + users.info
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_thread_reply_sender_name_none_on_api_failure(self) -> None:
        """Thread parent sender_name should be None if API resolution fails."""
        ch = _make_channel()

        # Mock conversations.history response (parent message)
        parent_resp = _ok_json(
            {
                "messages": [
                    {
                        "user": "U_PARENT",
                        "text": "Parent message",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        # Mock users.info response (API failure)
        user_resp = _ok_json({"ok": False, "error": "user_not_found"})

        # Mock API: first call (conversations.history), second call (users.info fails)
        mock_post = AsyncMock(side_effect=[parent_resp, user_resp])

        with patch.object(ch._api._http, "post", mock_post):
            event: dict[str, object] = {
                "type": "message",
                "user": "U_REPLY",
                "text": "Reply to thread",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            msg = await ch._parse_message_event(event)

            # Verify InboundMessage has reply_to with sender_name=None (API failed)
            assert msg is not None
            assert msg.reply_to is not None
            assert msg.reply_to.message_id == "1111.0000"
            assert msg.reply_to.content == "Parent message"
            assert msg.reply_to.sender_id == "U_PARENT"
            assert msg.reply_to.sender_name is None  # API failed, no name available

        # Verify 2 API calls: conversations.history + users.info (failed)
        assert mock_post.call_count == 2
