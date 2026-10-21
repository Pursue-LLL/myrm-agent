"""Mattermost attachment delivery: files ride with the first post, failures are reported after it."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.mattermost import MattermostChannel
from app.channels.types import MediaAttachment, MediaType, OutboundMessage


def _channel() -> MattermostChannel:
    ch = MattermostChannel(server_url="https://mm.example.com", access_token="test-token")
    ch._bot_id = "bot_user_id"
    ch._api._bot_user_id = "bot_user_id"
    return ch


def _message(*media: MediaAttachment, content: str = "") -> OutboundMessage:
    return OutboundMessage(channel="mattermost", recipient_id="ch_1", content=content, user_id="u1", media=media)


def _file(tmp_path: Path, name: str = "report.pdf") -> MediaAttachment:
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4 body")
    return MediaAttachment(media_type=MediaType.DOCUMENT, path=str(path))


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://mm.example.com/api/v4/files")
    return httpx.HTTPStatusError("rejected", request=request, response=httpx.Response(status, request=request))


class TestFilesRideWithTheFirstPost:
    @pytest.mark.asyncio
    async def test_local_file_is_uploaded_from_disk(self, tmp_path: Path) -> None:
        ch = _channel()
        with (
            patch.object(ch._api, "upload_file", new_callable=AsyncMock, return_value="f1") as upload,
            patch.object(ch._api, "create_post", new_callable=AsyncMock, return_value={"id": "p1"}) as post,
        ):
            result = await ch.send(_message(_file(tmp_path), content="Here you go"))

        assert result == "p1"
        upload.assert_awaited_once_with("ch_1", "report.pdf", b"%PDF-1.4 body")
        assert post.await_args.kwargs["file_ids"] == ["f1"]

    @pytest.mark.asyncio
    async def test_files_only_message_is_one_post_carrying_the_files(self, tmp_path: Path) -> None:
        ch = _channel()
        with (
            patch.object(ch._api, "upload_file", new_callable=AsyncMock, side_effect=["f1", "f2"]),
            patch.object(ch._api, "create_post", new_callable=AsyncMock, return_value={"id": "p9"}) as post,
        ):
            result = await ch.send(_message(_file(tmp_path, "a.pdf"), _file(tmp_path, "b.pdf")))

        assert result == "p9"
        post.assert_awaited_once()
        assert post.await_args.args[1] == ""
        assert post.await_args.kwargs["file_ids"] == ["f1", "f2"]

    @pytest.mark.asyncio
    async def test_files_go_only_with_the_first_of_several_text_chunks(self, tmp_path: Path) -> None:
        ch = _channel()
        with (
            patch("app.channels.providers.mattermost.channel.render", return_value=["one", "two"]),
            patch.object(ch._api, "upload_file", new_callable=AsyncMock, return_value="f1"),
            patch.object(ch._api, "create_post", new_callable=AsyncMock, side_effect=[{"id": "p1"}, {"id": "p2"}]) as post,
        ):
            await ch.send(_message(_file(tmp_path), content="long text"))

        assert [c.kwargs["file_ids"] for c in post.await_args_list] == [["f1"], None]

    @pytest.mark.asyncio
    async def test_empty_message_without_media_is_a_no_op(self) -> None:
        ch = _channel()
        with patch.object(ch._api, "create_post", new_callable=AsyncMock) as post:
            assert await ch.send(_message()) is None
        post.assert_not_awaited()


class TestFailedUploadsAreReportedAfterThePost:
    @pytest.mark.asyncio
    async def test_one_bad_file_does_not_block_the_text_or_the_other_file(self, tmp_path: Path) -> None:
        ch = _channel()
        good = _file(tmp_path, "good.pdf")
        missing = MediaAttachment(media_type=MediaType.DOCUMENT, path=str(tmp_path / "gone.pdf"))
        with (
            patch.object(ch._api, "upload_file", new_callable=AsyncMock, return_value="f1"),
            patch.object(ch._api, "create_post", new_callable=AsyncMock, return_value={"id": "p1"}) as post,
        ):
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(_message(missing, good, content="Report"))

        assert post.await_args.kwargs["file_ids"] == ["f1"]
        assert exc_info.value.accepted is True
        assert exc_info.value.failed_attachments == ("gone.pdf",)
        assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_unreadable_file_without_text_is_a_permanent_unaccepted_failure(self, tmp_path: Path) -> None:
        ch = _channel()
        missing = MediaAttachment(media_type=MediaType.DOCUMENT, path=str(tmp_path / "gone.pdf"))
        with patch.object(ch._api, "create_post", new_callable=AsyncMock) as post:
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(_message(missing))

        post.assert_not_awaited()
        assert exc_info.value.accepted is False
        assert exc_info.value.retriable is False
        assert exc_info.value.failed_attachments == ("gone.pdf",)

    @pytest.mark.asyncio
    async def test_attachment_without_a_source_is_permanent(self) -> None:
        ch = _channel()
        with patch.object(ch._api, "create_post", new_callable=AsyncMock, return_value={"id": "p1"}):
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(_message(MediaAttachment(media_type=MediaType.IMAGE), content="pic"))

        assert exc_info.value.accepted is True
        assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("status", "retriable"), [(500, True), (429, True), (403, False), (413, False)])
    async def test_upload_rejection_is_classified_by_status(self, tmp_path: Path, status: int, retriable: bool) -> None:
        ch = _channel()
        with (
            patch.object(ch._api, "upload_file", new_callable=AsyncMock, side_effect=_status_error(status)),
            patch.object(ch._api, "create_post", new_callable=AsyncMock) as post,
        ):
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(_message(_file(tmp_path)))

        post.assert_not_awaited()
        assert exc_info.value.retriable is retriable
        assert exc_info.value.accepted is False

    @pytest.mark.asyncio
    async def test_upload_without_file_id_is_reported(self, tmp_path: Path) -> None:
        ch = _channel()
        with (
            patch.object(ch._api, "upload_file", new_callable=AsyncMock, return_value=""),
            patch.object(ch._api, "create_post", new_callable=AsyncMock, return_value={"id": "p1"}),
        ):
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(_message(_file(tmp_path), content="text"))

        assert exc_info.value.accepted is True
        assert exc_info.value.failed_attachments == ("report.pdf",)

    @pytest.mark.asyncio
    async def test_unreachable_url_is_a_retriable_failure(self) -> None:
        ch = _channel()
        failed_download = AsyncMock(return_value=type("R", (), {"success": False, "data": None})())
        with (
            patch("app.channels.media.downloader.MediaDownloader.download", failed_download),
            patch.object(ch._api, "create_post", new_callable=AsyncMock) as post,
        ):
            with pytest.raises(ChannelSendError) as exc_info:
                await ch.send(_message(MediaAttachment(media_type=MediaType.IMAGE, url="https://x.example/p.png")))

        post.assert_not_awaited()
        assert exc_info.value.retriable is True
        assert exc_info.value.accepted is False
        assert exc_info.value.failed_attachments == ("https://x.example/p.png",)
