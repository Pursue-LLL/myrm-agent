"""Email outbound: attachment loading and MIME assembly."""

from __future__ import annotations

import email
import email.policy
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.media import MediaDownloadResult
from app.channels.providers.email import outbound
from app.channels.providers.email.outbound import LoadedAttachment, build_message, load_attachments
from app.channels.types import MediaAttachment, MediaType


def _parse(message: object) -> email.message.EmailMessage:
    return email.message_from_bytes(message.as_bytes(), policy=email.policy.default)  # type: ignore[attr-defined, return-value]


class TestBuildMessage:
    def test_message_without_attachments_stays_a_single_html_alternative(self) -> None:
        message, message_id = build_message("bot@example.com", "user@example.com", "Hi", "<p>Hello</p>", None, ())

        parsed = _parse(message)
        assert parsed.get_content_type() == "multipart/alternative"
        assert parsed["Message-ID"] == message_id
        assert (parsed["From"], parsed["To"], parsed["Subject"]) == ("bot@example.com", "user@example.com", "Hi")
        assert "In-Reply-To" not in parsed

    def test_reply_headers_thread_the_message(self) -> None:
        message, _ = build_message("a@x.com", "b@x.com", "Re: Hi", "<p>ok</p>", "<orig@x.com>", ())

        assert (message["In-Reply-To"], message["References"]) == ("<orig@x.com>", "<orig@x.com>")

    def test_attachments_ride_next_to_the_html_body(self) -> None:
        report = LoadedAttachment("report.pdf", "application/pdf", b"%PDF-1.7 data")
        message, _ = build_message("a@x.com", "b@x.com", "Report", "<p>Attached</p>", None, (report,))

        parsed = _parse(message)
        assert parsed.get_content_type() == "multipart/mixed"
        body, attachment = parsed.get_payload()
        assert body.get_content_type() == "multipart/alternative"
        assert body.get_payload()[0].get_content() == "<p>Attached</p>"
        assert attachment.get_content_type() == "application/pdf"
        assert attachment.get_filename() == "report.pdf"
        assert attachment.get_content_disposition() == "attachment"
        assert attachment.get_payload(decode=True) == b"%PDF-1.7 data"

    def test_non_ascii_filename_survives_the_round_trip(self) -> None:
        item = LoadedAttachment("季度报告.xlsx", "application/vnd.ms-excel", b"cells")
        message, _ = build_message("a@x.com", "b@x.com", "S", "<p>x</p>", None, (item,))

        attachment = _parse(message).get_payload()[1]
        assert attachment.get_filename() == "季度报告.xlsx"


class TestLoadAttachments:
    @pytest.mark.asyncio
    async def test_local_file_is_read_with_a_guessed_type(self, tmp_path: Path) -> None:
        path = tmp_path / "notes.txt"
        path.write_bytes(b"hello")

        loaded, failed = await load_attachments((MediaAttachment(media_type=MediaType.DOCUMENT, path=str(path)),))

        assert failed == []
        assert loaded == [LoadedAttachment("notes.txt", "text/plain", b"hello")]

    @pytest.mark.asyncio
    async def test_declared_filename_and_mime_type_win(self, tmp_path: Path) -> None:
        path = tmp_path / "tmpfile"
        path.write_bytes(b"x")
        attachment = MediaAttachment(
            media_type=MediaType.DOCUMENT, path=str(path), filename="summary.md", mime_type="text/markdown"
        )

        loaded, _ = await load_attachments((attachment,))

        assert (loaded[0].filename, loaded[0].mime_type) == ("summary.md", "text/markdown")

    @pytest.mark.asyncio
    async def test_unloadable_attachments_are_listed_not_raised(self, tmp_path: Path) -> None:
        good = tmp_path / "good.txt"
        good.write_bytes(b"ok")
        media = (
            MediaAttachment(media_type=MediaType.DOCUMENT, path=str(tmp_path / "missing.txt")),
            MediaAttachment(media_type=MediaType.DOCUMENT, path=str(good)),
            MediaAttachment(media_type=MediaType.DOCUMENT),
        )

        loaded, failed = await load_attachments(media)

        assert [item.filename for item in loaded] == ["good.txt"]
        assert failed == ["missing.txt", "document"]

    @pytest.mark.asyncio
    async def test_oversized_file_is_not_loaded(self, tmp_path: Path) -> None:
        path = tmp_path / "huge.bin"
        path.write_bytes(b"0123456789")

        with patch.object(outbound, "MAX_ATTACHMENT_BYTES", 5):
            loaded, failed = await load_attachments((MediaAttachment(media_type=MediaType.DOCUMENT, path=str(path)),))

        assert (loaded, failed) == ([], ["huge.bin"])

    @pytest.mark.asyncio
    async def test_url_attachment_is_downloaded_under_its_url_name(self) -> None:
        attachment = MediaAttachment(media_type=MediaType.DOCUMENT, url="https://files.example.com/a/doc.pdf")
        downloaded = MediaDownloadResult(
            success=True, data=b"%PDF", content_type="application/pdf", error=None, url=attachment.url or "", size_bytes=4
        )

        with patch("app.channels.media.downloader.MediaDownloader.download", new_callable=AsyncMock, return_value=downloaded):
            loaded, failed = await load_attachments((attachment,))

        assert failed == []
        assert loaded == [LoadedAttachment("doc.pdf", "application/pdf", b"%PDF")]

    @pytest.mark.asyncio
    async def test_failed_download_is_listed(self) -> None:
        attachment = MediaAttachment(media_type=MediaType.DOCUMENT, url="https://files.example.com/doc.pdf")
        failed_download = MediaDownloadResult(
            success=False, data=None, content_type=None, error=None, url=attachment.url or "", size_bytes=0
        )

        with patch(
            "app.channels.media.downloader.MediaDownloader.download", new_callable=AsyncMock, return_value=failed_download
        ):
            loaded, failed = await load_attachments((attachment,))

        assert (loaded, failed) == ([], ["https://files.example.com/doc.pdf"])
