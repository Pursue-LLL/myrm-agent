"""SlackChannel outbound: send, file upload, attachment failures, delete and react."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelSendError,
    RateLimitError,
)
from app.channels.types import (
    ActionButton,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)
from tests.channels.providers.slack.support import err_json, make_channel, ok_json


class TestSlackFileUpload:
    """Tests for the 3-step external upload flow."""

    @pytest.mark.asyncio
    async def test_upload_file_3step_flow(self, tmp_path: object) -> None:
        import pathlib

        test_file = pathlib.Path(str(tmp_path)) / "test.txt"
        test_file.write_text("hello")

        ch = make_channel()
        attachment = MediaAttachment(
            media_type=MediaType.DOCUMENT,
            path=str(test_file),
            filename="test.txt",
        )

        step1_resp = ok_json({"upload_url": "https://files.slack.com/upload/xxx", "file_id": "F123"})
        put_resp = httpx.Response(200)
        step3_resp = ok_json()

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

        ch = make_channel()
        attachment = MediaAttachment(media_type=MediaType.DOCUMENT, path=fpath, filename="f.txt")

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=err_json("not_allowed")):
            await ch._api.upload_file("C_CHAN", attachment, None)

        pathlib.Path(fpath).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_upload_file_empty_attachment(self) -> None:
        ch = make_channel()
        attachment = MediaAttachment(media_type=MediaType.DOCUMENT)
        await ch._api.upload_file("C_CHAN", attachment, None)


class TestSlackSend:
    """Tests for the send() method — text, blocks, media, error handling."""

    @pytest.mark.asyncio
    async def test_send_text_only(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C_CHAN", content="Hello", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json({"ts": "1.1"})):
            ts = await ch.send(msg)
        assert ts == "1.1"

    @pytest.mark.asyncio
    async def test_send_with_thread_ts(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="Reply",
            user_id="U",
            metadata={"thread_ts": "0.0"},
        )
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json({"ts": "2.2"})) as mock_post:
            await ch.send(msg)
        payload = mock_post.call_args.kwargs.get("json", {})
        assert payload.get("thread_ts") == "0.0"

    @pytest.mark.asyncio
    async def test_send_with_reply_to_id(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="Reply",
            user_id="U",
            reply_to_id="parent.ts",
        )
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json({"ts": "3.3"})) as mock_post:
            await ch.send(msg)
        payload = mock_post.call_args.kwargs.get("json", {})
        assert payload.get("thread_ts") == "parent.ts"

    @pytest.mark.asyncio
    async def test_send_with_blocks(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="Pick",
            user_id="U",
            components=((ActionButton(label="Go", action_id="go"),),),
        )
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json({"ts": "4.4"})) as mock_post:
            await ch.send(msg)
        payload = mock_post.call_args.kwargs.get("json", {})
        assert "blocks" in payload

    @pytest.mark.asyncio
    async def test_send_with_media(self) -> None:
        import pathlib
        import tempfile

        ch = make_channel()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"data")
            fpath = f.name

        msg = OutboundMessage(
            channel="slack",
            recipient_id="C_CHAN",
            content="",
            user_id="U",
            media=(MediaAttachment(media_type=MediaType.DOCUMENT, path=fpath, filename="f.txt"),),
        )
        step1 = ok_json({"upload_url": "https://up.slack.com/x", "file_id": "F1"})
        step3 = ok_json()
        put_resp = httpx.Response(200)
        with (
            patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=[step1, step3]),
            patch.object(ch._api._http, "put", new_callable=AsyncMock, return_value=put_resp),
        ):
            await ch.send(msg)
        pathlib.Path(fpath).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_send_auth_error(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C", content="Hi", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=err_json("token_revoked")):
            with pytest.raises(ChannelAuthError):
                await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_rate_limit_error(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C", content="Hi", user_id="U")
        resp = httpx.Response(200, json={"ok": False, "error": "ratelimited"}, headers={"Retry-After": "5"})
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(RateLimitError):
                await ch.send(msg)

    @pytest.mark.asyncio
    async def test_send_retriable_error(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C", content="Hi", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=err_json("internal_error")):
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)
            assert exc_info.value.retriable is True

    @pytest.mark.asyncio
    async def test_send_non_retriable_error(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C", content="Hi", user_id="U")
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=err_json("channel_not_found")):
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(msg)
            assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_send_empty_content_with_media(self) -> None:
        """send() with no content but media should still upload files."""
        import pathlib
        import tempfile

        ch = make_channel()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"data")
            fpath = f.name

        msg = OutboundMessage(
            channel="slack",
            recipient_id="C",
            content="",
            user_id="U",
            media=(MediaAttachment(media_type=MediaType.DOCUMENT, path=fpath, filename="f.txt"),),
        )
        step1 = ok_json({"upload_url": "https://up.slack.com/x", "file_id": "F1"})
        step3 = ok_json()
        put_resp = httpx.Response(200)
        with (
            patch.object(ch._api._http, "post", new_callable=AsyncMock, side_effect=[step1, step3]),
            patch.object(ch._api._http, "put", new_callable=AsyncMock, return_value=put_resp) as mock_put,
        ):
            result = await ch.send(msg)
        assert result is None
        mock_put.assert_called_once()
        pathlib.Path(fpath).unlink(missing_ok=True)


class TestSlackSendAttachmentFailures:
    """A file Slack does not take is reported, never silently dropped."""

    @staticmethod
    def _doc(name: str = "f.txt") -> MediaAttachment:
        return MediaAttachment(media_type=MediaType.DOCUMENT, path=f"/tmp/{name}", filename=name)

    @pytest.mark.asyncio
    async def test_failed_upload_after_delivered_text_is_a_partial_delivery(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C", content="Report", user_id="U", media=(self._doc("a.pdf"),))
        with (
            patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json({"ts": "1.1"})),
            patch.object(ch._api, "upload_file", new_callable=AsyncMock, return_value=False),
            pytest.raises(ChannelSendError) as excinfo,
        ):
            await ch.send(msg)

        assert excinfo.value.failed_attachments == ("a.pdf",)
        assert (excinfo.value.accepted, excinfo.value.retriable) == (True, False)

    @pytest.mark.asyncio
    async def test_files_only_message_whose_upload_failed_delivered_nothing(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C", content="", user_id="U", media=(self._doc("a.pdf"),))
        with (
            patch.object(ch._api, "upload_file", new_callable=AsyncMock, return_value=False),
            pytest.raises(ChannelSendError) as excinfo,
        ):
            await ch.send(msg)

        assert (excinfo.value.accepted, excinfo.value.retriable) == (False, True)

    @pytest.mark.asyncio
    async def test_every_attachment_is_attempted(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(
            channel="slack", recipient_id="C", content="", user_id="U", media=(self._doc("a.pdf"), self._doc("b.pdf"))
        )
        upload = AsyncMock(side_effect=[False, True])
        with patch.object(ch._api, "upload_file", upload), pytest.raises(ChannelSendError) as excinfo:
            await ch.send(msg)

        assert upload.await_count == 2
        assert excinfo.value.failed_attachments == ("a.pdf",)

    @pytest.mark.asyncio
    async def test_assistant_status_is_cleared_even_when_delivery_fails(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(channel="slack", recipient_id="C", content="", user_id="U", media=(self._doc(),))
        with (
            patch.object(ch._api, "upload_file", new_callable=AsyncMock, return_value=False),
            patch.object(ch, "_clear_assistant_status", new_callable=AsyncMock) as clear,
            pytest.raises(ChannelSendError),
        ):
            await ch.send(msg)

        clear.assert_awaited_once_with("C")


class TestSlackUploadExtended:
    """Extended upload tests for URL download path and edge cases."""

    @pytest.mark.asyncio
    async def test_upload_file_from_url(self) -> None:
        from unittest.mock import MagicMock

        ch = make_channel()
        attachment = MediaAttachment(
            media_type=MediaType.IMAGE,
            url="https://example.com/img.png",
            filename="img.png",
        )
        step1 = ok_json({"upload_url": "https://up.slack.com/x", "file_id": "F2"})
        step3 = ok_json()
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

        ch = make_channel()
        attachment = MediaAttachment(media_type=MediaType.DOCUMENT, path=fpath, filename="f.txt")
        step1 = ok_json({"upload_url": "https://up.slack.com/x", "file_id": "F3"})
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

        ch = make_channel()
        attachment = MediaAttachment(
            media_type=MediaType.DOCUMENT,
            path=fpath,
            filename="f.txt",
            caption="See this",
        )
        step1 = ok_json({"upload_url": "https://up.slack.com/x", "file_id": "F4"})
        step3 = ok_json()
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
        ch = make_channel()
        attachment = MediaAttachment(
            media_type=MediaType.IMAGE,
            url="https://example.com/img.png",
            filename="img.png",
        )
        with patch.object(ch._api._http, "get", new_callable=AsyncMock, side_effect=Exception("network")):
            await ch._api.upload_file("C_CHAN", attachment, None)


class TestSlackDeleteReact:
    """Tests for delete_message and react_to_message."""

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json()) as mock_post:
            await ch.delete_message("C_CHAN", "1234.5678")
        assert "chat.delete" in str(mock_post.call_args)

    @pytest.mark.asyncio
    async def test_delete_message_failure(self) -> None:
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=err_json()):
            await ch.delete_message("C_CHAN", "1234.5678")

    @pytest.mark.asyncio
    async def test_react_to_message(self) -> None:
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=ok_json()) as mock_post:
            await ch.react_to_message("C_CHAN", "1234.5678", ":thumbsup:")
        payload = mock_post.call_args.kwargs.get("json", {})
        assert payload["name"] == "thumbsup"

    @pytest.mark.asyncio
    async def test_react_to_message_empty_emoji(self) -> None:
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock) as mock_post:
            await ch.react_to_message("C_CHAN", "1234.5678", "")
        mock_post.assert_not_called()

    @pytest.mark.asyncio
    async def test_react_to_message_failure(self) -> None:
        ch = make_channel()
        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=err_json()):
            with pytest.raises(ChannelSendError, match="reactions.add failed"):
                await ch.react_to_message("C_CHAN", "1234.5678", "wave")
