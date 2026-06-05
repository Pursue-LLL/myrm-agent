"""Tests for feishu cards, callback parser, streaming merge, and API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.channels.providers.feishu.api import FeishuClient
from app.channels.providers.feishu.cards import (
    build_component_card as build_feishu_card,
)
from app.channels.providers.feishu.cards import (
    merge_streaming_text,
    parse_card_action,
)
from app.channels.types import OutboundMessage
from app.channels.types.components import (
    ActionButton,
    ButtonStyle,
    QuickReply,
    SelectMenu,
    SelectOption,
)


def _make_msg(
    *,
    components: tuple[tuple[ActionButton | SelectMenu, ...], ...] = (),
    quick_replies: tuple[QuickReply, ...] = (),
    content: str = "hello",
) -> OutboundMessage:
    return OutboundMessage(
        channel="feishu",
        recipient_id="oc_test",
        content=content,
        user_id="u1",
        components=components,
        quick_replies=quick_replies,
    )


class TestBuildFeishuCard:
    def test_returns_none_without_components(self) -> None:
        msg = _make_msg()
        assert build_feishu_card(msg, "text") is None

    def test_quick_reply_generates_button(self) -> None:
        msg = _make_msg(quick_replies=(QuickReply(label="Yes", text="yes"),))
        card = build_feishu_card(msg, "Choose:")
        assert card is not None
        elements = card["elements"]
        assert isinstance(elements, list)
        assert len(elements) == 2
        assert elements[0]["tag"] == "markdown"
        assert elements[0]["content"] == "Choose:"
        action_elem = elements[1]
        assert action_elem["tag"] == "action"
        actions = action_elem["actions"]
        assert isinstance(actions, list)
        assert len(actions) == 1
        btn = actions[0]
        assert btn["tag"] == "button"
        assert btn["value"]["type"] == "qr"
        assert btn["value"]["data"] == "yes"

    def test_action_button_with_url(self) -> None:
        btn = ActionButton(label="Open", action_id="x", url="https://example.com")
        msg = _make_msg(components=((btn,),))
        card = build_feishu_card(msg, "")
        assert card is not None
        actions = card["elements"][0]["actions"]
        assert actions[0]["url"] == "https://example.com"
        assert actions[0]["tag"] == "button"

    def test_action_button_primary_style(self) -> None:
        btn = ActionButton(label="Go", action_id="go:1", style=ButtonStyle.PRIMARY)
        msg = _make_msg(components=((btn,),))
        card = build_feishu_card(msg, "text")
        actions = card["elements"][1]["actions"]
        assert actions[0]["type"] == "primary"
        assert actions[0]["value"]["type"] == "act"
        assert actions[0]["value"]["action_id"] == "go:1"

    def test_select_menu(self) -> None:
        sel = SelectMenu(
            action_id="pick",
            placeholder="Choose...",
            options=(SelectOption(label="A", value="a"), SelectOption(label="B", value="b")),
        )
        msg = _make_msg(components=((sel,),))
        card = build_feishu_card(msg, "")
        actions = card["elements"][0]["actions"]
        assert actions[0]["tag"] == "select_static"
        assert len(actions[0]["options"]) == 2
        assert actions[0]["options"][0]["value"] == "sel:a"

    def test_wide_screen_mode_enabled(self) -> None:
        msg = _make_msg(quick_replies=(QuickReply(label="X", text="x"),))
        card = build_feishu_card(msg, "")
        assert card["config"]["wide_screen_mode"] is True

    def test_empty_text_no_markdown_element(self) -> None:
        msg = _make_msg(quick_replies=(QuickReply(label="X", text="x"),))
        card = build_feishu_card(msg, "")
        assert card["elements"][0]["tag"] == "action"


class TestParseCardAction:
    def test_parse_quick_reply(self) -> None:
        event = {
            "operator": {"open_id": "ou_user1"},
            "action": {"tag": "button", "value": {"type": "qr", "data": "yes"}},
            "context": {"open_chat_id": "oc_chat1", "open_message_id": "om_msg1"},
        }
        result = parse_card_action(event)
        assert result is not None
        sender_id, chat_id, content, metadata = result
        assert sender_id == "ou_user1"
        assert chat_id == "oc_chat1"
        assert content == "yes"
        assert metadata["callback_type"] == "qr"
        assert metadata["card_message_id"] == "om_msg1"

    def test_parse_action_button(self) -> None:
        event = {
            "operator": {"open_id": "ou_user2"},
            "action": {"tag": "button", "value": {"type": "act", "action_id": "approve:req-123"}},
            "context": {"open_chat_id": "oc_chat2", "open_message_id": "om_msg2"},
        }
        result = parse_card_action(event)
        assert result is not None
        _, _, content, metadata = result
        assert content == "approve:req-123"
        assert metadata["callback_type"] == "act"

    def test_parse_select_with_option(self) -> None:
        event = {
            "operator": {"open_id": "ou_user3"},
            "action": {
                "tag": "select_static",
                "value": {"type": "sel", "action_id": "pick"},
                "option": "sel:option_a",
            },
            "context": {"open_chat_id": "oc_chat3", "open_message_id": "om_msg3"},
        }
        result = parse_card_action(event)
        assert result is not None
        _, _, content, _ = result
        assert content == "option_a"

    def test_returns_none_without_operator(self) -> None:
        event = {"action": {"value": {"type": "qr", "data": "x"}}}
        assert parse_card_action(event) is None

    def test_returns_none_without_action(self) -> None:
        event = {"operator": {"open_id": "ou_x"}}
        assert parse_card_action(event) is None

    def test_returns_none_without_value(self) -> None:
        event = {"operator": {"open_id": "ou_x"}, "action": {"tag": "button"}}
        assert parse_card_action(event) is None


class TestStreamingMerge:
    def test_empty_previous(self) -> None:
        assert merge_streaming_text("", "hello") == "hello"

    def test_empty_next(self) -> None:
        assert merge_streaming_text("hello", "") == "hello"

    def test_next_starts_with_previous(self) -> None:
        assert merge_streaming_text("这", "这是一段") == "这是一段"

    def test_previous_starts_with_next(self) -> None:
        assert merge_streaming_text("这是一段", "这是") == "这是一段"

    def test_partial_overlap(self) -> None:
        assert merge_streaming_text("revision_id: 552", "2，一点变化都没有") == ("revision_id: 552，一点变化都没有")

    def test_no_overlap_fallback(self) -> None:
        assert merge_streaming_text("abc", "xyz") == "abcxyz"

    def test_identical(self) -> None:
        assert merge_streaming_text("hello", "hello") == "hello"


class TestFeishuClient:
    @pytest.mark.asyncio
    async def test_upload_image_success(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": {"image_key": "img_k"}}

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = mock_resp
        client._http = mock_http

        result = await client.upload_image(b"fake_image")
        assert result == "img_k"

    @pytest.mark.asyncio
    async def test_upload_image_failure(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        mock_resp = MagicMock()
        mock_resp.is_success = False
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"code": 500, "msg": "error"}

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = mock_resp
        client._http = mock_http

        result = await client.upload_image(b"fake_image")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_message_success(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": {"message_id": "om_123"}}

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = mock_resp
        client._http = mock_http

        result = await client.send_message("oc_chat", "text", '{"text":"hi"}')
        assert result == "om_123"

    @pytest.mark.asyncio
    async def test_verify_connectivity(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")
        assert await client.verify_connectivity() is True

    def test_is_configured(self) -> None:
        assert FeishuClient("a", "b").is_configured is True
        assert FeishuClient("", "").is_configured is False

    @pytest.mark.asyncio
    async def test_ensure_token_refresh(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "code": 0,
            "tenant_access_token": "new_tok",
            "expire": 7200,
        }
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = resp
        client._http = mock_http

        token = await client.ensure_token()
        assert token == "new_tok"
        assert client._token == "new_tok"

    @pytest.mark.asyncio
    async def test_ensure_token_cached(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "cached"
        client._token_expires_at = float("inf")
        token = await client.ensure_token()
        assert token == "cached"

    @pytest.mark.asyncio
    async def test_ensure_token_auth_error_http(self) -> None:
        from app.channels.providers.feishu.sdk.exceptions import FeishuAuthError

        client = FeishuClient("app_id", "app_secret")
        resp = MagicMock()
        resp.status_code = 401
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = resp
        client._http = mock_http

        with pytest.raises(FeishuAuthError):
            await client.ensure_token()

    @pytest.mark.asyncio
    async def test_ensure_token_auth_error_code(self) -> None:
        from app.channels.providers.feishu.sdk.exceptions import FeishuAuthError

        client = FeishuClient("app_id", "app_secret")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"code": 99999, "msg": "invalid app"}
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = resp
        client._http = mock_http

        with pytest.raises(FeishuAuthError):
            await client.ensure_token()

    @pytest.mark.asyncio
    async def test_fetch_bot_info(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"bot": {"open_id": "ou_bot1"}}
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.get.return_value = resp
        client._http = mock_http

        result = await client.fetch_bot_info()
        assert result == "ou_bot1"

    @pytest.mark.asyncio
    async def test_send_message_rate_limited(self) -> None:
        from app.channels.providers.feishu.sdk.exceptions import FeishuRateLimitError

        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 429
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = resp
        client._http = mock_http

        with pytest.raises(FeishuRateLimitError):
            await client.send_message("oc_chat", "text", '{"text":"hi"}')

    @pytest.mark.asyncio
    async def test_send_message_server_error(self) -> None:
        from app.channels.providers.feishu.sdk.exceptions import FeishuSendError

        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 500
        resp.is_success = False
        resp.json.return_value = {"code": 500, "msg": "Internal Server Error"}
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = resp
        client._http = mock_http

        with pytest.raises(FeishuSendError):
            await client.send_message("oc_chat", "text", '{"text":"hi"}')

    @pytest.mark.asyncio
    async def test_send_message_api_code_error(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.json.return_value = {"code": 99999, "msg": "invalid param"}
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = resp
        client._http = mock_http

        result = await client.send_message("oc_chat", "text", '{"text":"hi"}')
        assert result is None

    @pytest.mark.asyncio
    async def test_edit_message_success(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.json.return_value = {"code": 0}
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.put.return_value = resp
        client._http = mock_http

        result = await client.edit_message("om_123", "text", '{"text":"edited"}')
        assert result is True

    @pytest.mark.asyncio
    async def test_edit_message_failure(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.json.return_value = {"code": 99999, "msg": "not found"}
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.put.return_value = resp
        client._http = mock_http

        result = await client.edit_message("om_123", "text", '{"text":"edited"}')
        assert result is False

    @pytest.mark.asyncio
    async def test_patch_message_success(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.patch.return_value = resp
        client._http = mock_http

        result = await client.patch_message("om_123", "interactive", '{"card":"data"}')
        assert result is True

    @pytest.mark.asyncio
    async def test_patch_message_failure(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 400
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.patch.return_value = resp
        client._http = mock_http

        result = await client.patch_message("om_123", "interactive", '{"card":"data"}')
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_message_success(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.json.return_value = {"code": 0}
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.delete.return_value = resp
        client._http = mock_http

        result = await client.delete_message("om_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_message_failure(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.json.return_value = {"code": 99999, "msg": "not found"}
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.delete.return_value = resp
        client._http = mock_http

        result = await client.delete_message("om_123")
        assert result is False

    @pytest.mark.asyncio
    async def test_download_image_success(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"image_bytes"
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.get.return_value = resp
        client._http = mock_http

        result = await client.download_image("img_key_1")
        assert result == b"image_bytes"

    @pytest.mark.asyncio
    async def test_download_image_failure(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 404
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.get.return_value = resp
        client._http = mock_http

        result = await client.download_image("img_key_missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_download_message_resource_success(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"resource_data"
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.get.return_value = resp
        client._http = mock_http

        result = await client.download_message_resource("om_msg1", "fk_1")
        assert result == b"resource_data"

    @pytest.mark.asyncio
    async def test_download_message_resource_failure(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 500
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.get.return_value = resp
        client._http = mock_http

        result = await client.download_message_resource("om_msg1", "fk_1")
        assert result is None

    @pytest.mark.asyncio
    async def test_upload_file_success(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.json.return_value = {"code": 0, "data": {"file_key": "fk_new"}}
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = resp
        client._http = mock_http

        result = await client.upload_file(b"file_data", "report.pdf")
        assert result == "fk_new"

    @pytest.mark.asyncio
    async def test_upload_file_failure(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.json.return_value = {"code": 99999, "msg": "upload failed"}
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = resp
        client._http = mock_http

        result = await client.upload_file(b"file_data", "report.pdf")
        assert result is None

    @pytest.mark.asyncio
    async def test_download_url_success(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"img_data"
        resp.raise_for_status = MagicMock()
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.get.return_value = resp
        client._http = mock_http

        result = await client.download_url("https://example.com/img.png")
        assert result == b"img_data"

    @pytest.mark.asyncio
    async def test_download_url_failure(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.get.side_effect = httpx.HTTPStatusError(
            "404",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        client._http = mock_http

        result = await client.download_url("https://example.com/missing.png")
        assert result is None

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        client._http = mock_http

        await client.close()
        mock_http.aclose.assert_called_once()
        assert client._http is None

    @pytest.mark.asyncio
    async def test_close_already_closed(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._http = None
        await client.close()

    def test_safe_json_non_json(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        resp = MagicMock()
        resp.is_success = True
        resp.json.side_effect = ValueError("not json")
        result = client._safe_json(resp, "test_op")
        assert result["code"] == -1

    def test_safe_json_non_dict(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = [1, 2, 3]
        result = client._safe_json(resp, "test_op")
        assert result["code"] == -1

    def test_use_lark_api(self) -> None:
        client = FeishuClient("a", "b", use_lark=True)
        assert "larksuite" in client.api_base

    def test_get_http_creates_new(self) -> None:
        client = FeishuClient("a", "b")
        http = client._get_http()
        assert http is not None
        assert client._http is http

    @pytest.mark.asyncio
    async def test_send_message_reply_in_thread(self) -> None:
        client = FeishuClient("app_id", "app_secret")
        client._token = "tok"
        client._token_expires_at = float("inf")

        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.json.return_value = {"code": 0, "data": {"message_id": "om_thread"}}
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post.return_value = resp
        client._http = mock_http

        result = await client.send_message("oc_chat", "text", '{"text":"hi"}', reply_in_thread=True)
        assert result == "om_thread"
