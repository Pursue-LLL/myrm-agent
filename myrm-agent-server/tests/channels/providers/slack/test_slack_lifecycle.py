"""SlackChannel helpers, bot-info fetch, diagnostics and start/stop lifecycle."""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

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
    OutboundMessage,
    SelectMenu,
    SelectOption,
)
from tests.channels.providers.slack.support import err_json, make_channel, ok_json


class TestSlackFetchBotInfo:
    """Test that auth_test captures bot_user_id and team_id."""

    @pytest.mark.asyncio
    async def test_auth_test_captures_team_id(self) -> None:
        ch = make_channel()
        ch._team_id = ""
        resp = ok_json({"user_id": "U_BOT2", "team_id": "T_NEW"})
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
        assert cast("list[dict[str, object]]", blocks[0]["elements"])[0]["url"] == "https://example.com"

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
        el = cast("list[dict[str, object]]", blocks[0]["elements"])[0]
        assert el["type"] == "static_select"
        assert el["action_id"] == "sel:sel_1"
        assert len(cast("list[object]", el["options"])) == 2

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
        ch = make_channel()
        issues = ch.collect_issues()
        assert len(issues) == 0

    def test_collect_issues_runtime_error(self) -> None:
        ch = make_channel()
        ch.health.last_error = "Connection timed out"
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].message == "Connection timed out"

    def test_thread_tracker_metrics(self) -> None:
        ch = make_channel()
        metrics = ch.thread_tracker_metrics
        assert metrics.current_size == 0


class TestSlackLifecycle:
    """Tests for start/stop/health_check lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        ch = SlackChannel(bot_token="xoxb-test")
        resp = ok_json({"user_id": "U_BOT", "team_id": "T_TEAM"})
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
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=err_json("invalid_auth")):
            await ch.start()
        assert ch._status == ChannelStatus.ERROR
        await ch._api._http.aclose()

    @pytest.mark.asyncio
    async def test_start_with_socket_mode(self) -> None:
        ch = SlackChannel(bot_token="xoxb-test", app_token="xapp-test")
        resp = ok_json({"user_id": "U_BOT", "team_id": "T_TEAM"})
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
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_stop_cancels_socket_task(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING

        async def _forever() -> None:
            await asyncio.sleep(999)

        ch._socket_task = asyncio.create_task(_forever())
        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED
        assert ch._socket_task.cancelled() or ch._socket_task.done()

    @pytest.mark.asyncio
    async def test_health_check_ok(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json()):
            assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_not_running(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_api_failure(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=err_json()):
            assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=Exception("network")):
            assert await ch.health_check() is False
