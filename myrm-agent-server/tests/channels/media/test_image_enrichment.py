"""Tests for image_enrichment module — image download, compression, and base64 encoding."""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.media.image_enrichment import (
    MAX_IMAGE_BYTES,
    _compress_image,
    _download_and_cache,
    _download_via_channel_api,
    _download_via_http,
    _read_local_file,
    _save_to_cache,
    _sniff_mime,
    enrich_image_inbound,
    has_image_attachment,
)
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
)


def _make_msg(
    *,
    media: tuple[MediaAttachment, ...] = (),
    metadata: dict[str, object] | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="hello",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        media=media,
        metadata=metadata or {},
    )


class TestHasImageAttachment:
    def test_no_media(self) -> None:
        assert has_image_attachment(_make_msg()) is False

    def test_audio_only(self) -> None:
        msg = _make_msg(media=(MediaAttachment(media_type=MediaType.AUDIO),))
        assert has_image_attachment(msg) is False

    def test_image_present(self) -> None:
        msg = _make_msg(media=(MediaAttachment(media_type=MediaType.IMAGE),))
        assert has_image_attachment(msg) is True

    def test_mixed_media(self) -> None:
        msg = _make_msg(
            media=(
                MediaAttachment(media_type=MediaType.DOCUMENT),
                MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.jpg"),
            )
        )
        assert has_image_attachment(msg) is True


class TestSniffMime:
    def test_jpeg(self) -> None:
        assert _sniff_mime(b"\xff\xd8\xff\xe0more") == "image/jpeg"

    def test_png(self) -> None:
        assert _sniff_mime(b"\x89PNG\r\n\x1a\nmore") == "image/png"

    def test_webp(self) -> None:
        assert _sniff_mime(b"RIFF\x00\x00\x00\x00WEBP") == "image/webp"

    def test_gif(self) -> None:
        assert _sniff_mime(b"GIF89adata") == "image/gif"

    def test_unknown(self) -> None:
        assert _sniff_mime(b"\x00\x00\x00\x00") is None

    def test_too_short(self) -> None:
        assert _sniff_mime(b"\xff") is None


class TestEnrichImageInbound:
    @pytest.mark.asyncio
    async def test_no_image_returns_original(self) -> None:
        msg = _make_msg(media=(MediaAttachment(media_type=MediaType.AUDIO),))
        result = await enrich_image_inbound(msg, None)
        assert result is msg

    @pytest.mark.asyncio
    async def test_empty_media_returns_original(self) -> None:
        msg = _make_msg()
        result = await enrich_image_inbound(msg, None)
        assert result is msg

    @pytest.mark.asyncio
    async def test_image_url_download_success(self) -> None:
        jpeg_header = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/photo.jpg")
        msg = _make_msg(media=(att,))

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=jpeg_header,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/photo.jpg"),
        ):
            result = await enrich_image_inbound(msg, None)

        assert result is not msg
        image_data_list = result.metadata.get("image_data_list")
        assert isinstance(image_data_list, list)
        assert len(image_data_list) == 1
        assert image_data_list[0]["mime_type"] == "image/jpeg"
        assert image_data_list[0]["data_url"] == "file:///tmp/cache/photo.jpg"

    @pytest.mark.asyncio
    async def test_image_download_failure_returns_original(self) -> None:
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/bad.jpg")
        msg = _make_msg(media=(att,))

        with patch(
            "app.channels.media.image_enrichment._download_via_http",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await enrich_image_inbound(msg, None)

        assert result is msg

    @pytest.mark.asyncio
    async def test_caps_at_max_images(self) -> None:
        jpeg_header = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        atts = tuple(MediaAttachment(media_type=MediaType.IMAGE, url=f"https://example.com/img{i}.jpg") for i in range(6))
        msg = _make_msg(media=atts)

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=jpeg_header,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/img.jpg"),
        ):
            result = await enrich_image_inbound(msg, None)

        image_data_list = result.metadata.get("image_data_list")
        assert isinstance(image_data_list, list)
        assert len(image_data_list) == 4  # MAX_IMAGES_PER_MESSAGE


class TestDownloadAndCache:
    @pytest.mark.asyncio
    async def test_url_download_produces_file_url(self) -> None:
        raw = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.jpg")
        msg = _make_msg(media=(att,))

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=raw,
            ),
            patch(
                "app.channels.media.image_enrichment._save_to_cache",
                return_value="/tmp/cache/abcdef.jpg",
            ),
        ):
            result = await _download_and_cache(att, msg, None)

        assert result is not None
        assert result["data_url"] == "file:///tmp/cache/abcdef.jpg"
        assert result["mime_type"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_cache_failure_falls_back_to_base64(self) -> None:
        raw = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.jpg")
        msg = _make_msg(media=(att,))

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=raw,
            ),
            patch(
                "app.channels.media.image_enrichment._save_to_cache",
                return_value=None,
            ),
        ):
            result = await _download_and_cache(att, msg, None)

        assert result is not None
        assert result["data_url"].startswith("data:image/jpeg;base64,")
        decoded = base64.b64decode(result["data_url"].split(",", 1)[1])
        assert decoded == raw

    @pytest.mark.asyncio
    async def test_channel_api_fallback(self) -> None:
        """When photo_file_id is set, downloads via channel API."""
        raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        att = MediaAttachment(media_type=MediaType.IMAGE)
        msg = _make_msg(media=(att,), metadata={"photo_file_id": "file123"})

        mock_client = AsyncMock()
        mock_client.get_file.return_value = {"file_path": "/tmp/photo.png"}
        mock_client.download_file.return_value = raw

        mock_channel = type("Ch", (), {"_client": mock_client})()

        def get_channel_fn(name: str) -> object:
            return mock_channel

        with patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/img.png"):
            result = await _download_and_cache(att, msg, get_channel_fn)

        assert result is not None
        assert result["mime_type"] == "image/png"
        mock_client.get_file.assert_awaited_once_with("file123")

    @pytest.mark.asyncio
    async def test_sniff_overrides_misleading_platform_mime(self) -> None:
        """Discord can report image/webp for files that are actually PNG.
        Magic bytes sniffing must win over platform-declared mime_type.
        """
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        att = MediaAttachment(
            media_type=MediaType.IMAGE,
            url="https://cdn.discordapp.com/sticker.webp",
            mime_type="image/webp",
        )
        msg = _make_msg(media=(att,))

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=png_bytes,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/img.png"),
        ):
            result = await _download_and_cache(att, msg, None)

        assert result is not None
        assert result["mime_type"] == "image/png", "Sniffed MIME (image/png) should override platform-declared image/webp"

    @pytest.mark.asyncio
    async def test_compression_used_when_smaller(self) -> None:
        """Compression result is used if smaller than original."""
        raw = b"\xff\xd8\xff\xe0" + b"\x00" * 200
        smaller_compressed = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/big.jpg")
        msg = _make_msg(media=(att,))

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=raw,
            ),
            patch(
                "app.channels.media.image_enrichment._compress_image",
                return_value=smaller_compressed,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/img.jpg"),
        ):
            result = await _download_and_cache(att, msg, None)

        assert result is not None
        assert result["data_url"] == "file:///tmp/cache/img.jpg"

    @pytest.mark.asyncio
    async def test_compression_not_used_when_larger(self) -> None:
        """Original bytes are kept if compression makes them larger."""
        raw = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        larger_compressed = b"\xff\xd8\xff\xe0" + b"\x00" * 200
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/small.jpg")
        msg = _make_msg(media=(att,))

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=raw,
            ),
            patch(
                "app.channels.media.image_enrichment._compress_image",
                return_value=larger_compressed,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/orig.jpg"),
        ):
            result = await _download_and_cache(att, msg, None)

        assert result is not None
        assert result["data_url"] == "file:///tmp/cache/orig.jpg"

    @pytest.mark.asyncio
    async def test_too_large_after_compression_returns_none(self) -> None:
        """If image is still too large after compression, returns None."""
        oversized = b"\xff\xd8\xff\xe0" + b"\x00" * (MAX_IMAGE_BYTES + 100)
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/huge.jpg")
        msg = _make_msg(media=(att,))

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=oversized,
            ),
            patch(
                "app.channels.media.image_enrichment._compress_image",
                return_value=None,
            ),
        ):
            result = await _download_and_cache(att, msg, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_local_file_path_download(self) -> None:
        """Image downloaded from local path produces cached file URL."""
        jpeg_header = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        att = MediaAttachment(media_type=MediaType.IMAGE, path="/tmp/test_photo.jpg")
        msg = _make_msg(media=(att,))

        with (
            patch(
                "app.channels.media.image_enrichment._read_local_file",
                return_value=jpeg_header,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/local.jpg"),
        ):
            result = await _download_and_cache(att, msg, None)

        assert result is not None
        assert result["data_url"] == "file:///tmp/cache/local.jpg"

    @pytest.mark.asyncio
    async def test_non_image_mime_fallback_to_jpeg(self) -> None:
        """When sniffed MIME is not image/*, falls back to image/jpeg."""
        unknown_bytes = b"\x00\x00\x00\x00" + b"\x00" * 50
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/file", mime_type="application/octet-stream")
        msg = _make_msg(media=(att,))

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=unknown_bytes,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/unknown.jpg"),
        ):
            result = await _download_and_cache(att, msg, None)

        assert result is not None
        assert result["mime_type"] == "image/jpeg"


class TestReadLocalFile:
    def test_reads_existing_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
            path = f.name
        try:
            result = _read_local_file(path)
            assert result is not None
            assert len(result) == 54
        finally:
            Path(path).unlink()

    def test_nonexistent_file_returns_none(self) -> None:
        result = _read_local_file("/nonexistent/path/to/image.jpg")
        assert result is None

    def test_oversized_file_returns_none(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\x00" * 100)
            path = f.name
        try:
            with patch(
                "app.channels.media.image_enrichment.MAX_IMAGE_BYTES",
                10,
            ):
                result = _read_local_file(path)
            assert result is None
        finally:
            Path(path).unlink()

    def test_read_exception_returns_none(self) -> None:
        with (
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.read_bytes", side_effect=PermissionError("Access denied")),
        ):
            result = _read_local_file("/protected/image.jpg")
        assert result is None


class TestCompressImage:
    def test_compression_failure_returns_none(self) -> None:
        with patch(
            "app.channels.media.image_enrichment.image_compressor",
            create=True,
        ) as mock_mod:
            mock_mod.compress.side_effect = RuntimeError("PIL not available")
            with patch(
                "myrm_agent_harness.utils.media.image_compressor.image_compressor",
                mock_mod,
            ):
                result = _compress_image(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
        assert result is None

    def test_compression_success_returns_bytes(self) -> None:
        compressed = b"\xff\xd8\xff\xe0compressed"
        with patch(
            "myrm_agent_harness.utils.media.image_compressor.image_compressor.compress",
            return_value=compressed,
        ):
            result = _compress_image(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        assert result == compressed


class TestDownloadViaChannelApi:
    @pytest.mark.asyncio
    async def test_none_get_channel_fn(self) -> None:
        result = await _download_via_channel_api("file123", "telegram", None)
        assert result is None

    @pytest.mark.asyncio
    async def test_channel_without_client(self) -> None:
        def get_ch(name: str) -> object:
            return object()

        result = await _download_via_channel_api("file123", "telegram", get_ch)
        assert result is None

    @pytest.mark.asyncio
    async def test_client_without_required_methods(self) -> None:
        ch = type("Ch", (), {"_client": object()})()

        def get_ch(name: str) -> object:
            return ch

        result = await _download_via_channel_api("file123", "telegram", get_ch)
        assert result is None

    @pytest.mark.asyncio
    async def test_client_get_file_returns_empty_path(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_file.return_value = {"file_path": ""}
        ch = type("Ch", (), {"_client": mock_client})()

        def get_ch(name: str) -> object:
            return ch

        result = await _download_via_channel_api("file123", "telegram", get_ch)
        assert result is None

    @pytest.mark.asyncio
    async def test_client_exception_returns_none(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_file.side_effect = RuntimeError("API error")
        ch = type("Ch", (), {"_client": mock_client})()

        def get_ch(name: str) -> object:
            return ch

        result = await _download_via_channel_api("file123", "telegram", get_ch)
        assert result is None


class TestDownloadViaHttp:
    @pytest.mark.asyncio
    async def test_http_error_returns_none(self) -> None:
        with patch("app.channels.media.image_enrichment.httpx.AsyncClient") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await _download_via_http("https://example.com/missing.jpg")
        assert result is None

    @pytest.mark.asyncio
    async def test_http_success_returns_data(self) -> None:
        payload = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        with patch("app.channels.media.image_enrichment.httpx.AsyncClient") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.content = payload
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await _download_via_http("https://cdn.example.com/img.jpg")
        assert result == payload

    @pytest.mark.asyncio
    async def test_http_oversized_returns_none(self) -> None:
        oversized = b"\x00" * (MAX_IMAGE_BYTES * 2 + 1)
        with patch("app.channels.media.image_enrichment.httpx.AsyncClient") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.content = oversized
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await _download_via_http("https://example.com/huge.jpg")
        assert result is None


class TestEnrichExceptionHandling:
    @pytest.mark.asyncio
    async def test_download_exception_is_caught(self) -> None:
        """Exception during download is caught; message returned unchanged."""
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/err.jpg")
        msg = _make_msg(media=(att,))

        with patch(
            "app.channels.media.image_enrichment._download_via_http",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Connection reset"),
        ):
            result = await enrich_image_inbound(msg, None)

        assert result is msg


class TestPartialSuccessEnrichment:
    @pytest.mark.asyncio
    async def test_partial_success_keeps_successful_images(self) -> None:
        """When 3 images are sent but 1 fails, result contains 2 successful ones."""
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        atts = (
            MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/ok1.jpg"),
            MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/bad.jpg"),
            MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/ok2.jpg"),
        )
        msg = _make_msg(media=atts)

        call_count = 0

        async def _mock_http(url: str) -> bytes | None:
            nonlocal call_count
            call_count += 1
            if "bad" in url:
                return None
            return jpeg

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                side_effect=_mock_http,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/ok.jpg"),
        ):
            result = await enrich_image_inbound(msg, None)

        assert result is not msg
        image_data_list = result.metadata.get("image_data_list")
        assert isinstance(image_data_list, list)
        assert len(image_data_list) == 2

    @pytest.mark.asyncio
    async def test_original_content_preserved(self) -> None:
        """Enrichment does not modify the original message content."""
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.jpg")
        msg = _make_msg(media=(att,))

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=jpeg,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/img.jpg"),
        ):
            result = await enrich_image_inbound(msg, None)

        assert result.content == "hello"
        assert msg.content == "hello"


class TestChannelApiFallbackToUrl:
    @pytest.mark.asyncio
    async def test_channel_api_fails_falls_back_to_url(self) -> None:
        """When photo_file_id exists but channel API fails, falls back to URL download."""
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/fallback.jpg")
        msg = _make_msg(media=(att,), metadata={"photo_file_id": "file_abc"})

        mock_client = AsyncMock()
        mock_client.get_file.side_effect = RuntimeError("Telegram API down")
        mock_channel = type("Ch", (), {"_client": mock_client})()

        def get_ch(name: str) -> object:
            return mock_channel

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=jpeg,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/fb.jpg"),
        ):
            result = await _download_and_cache(att, msg, get_ch)

        assert result is not None
        assert result["data_url"] == "file:///tmp/cache/fb.jpg"

    @pytest.mark.asyncio
    async def test_channel_not_found_falls_back_to_url(self) -> None:
        """When get_channel_fn returns None for the channel, falls back to URL."""
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/photo.jpg")
        msg = _make_msg(media=(att,), metadata={"photo_file_id": "file_xyz"})

        def get_ch(name: str) -> None:
            return None

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=jpeg,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/ch.jpg"),
        ):
            result = await _download_and_cache(att, msg, get_ch)

        assert result is not None
        assert result["mime_type"] == "image/jpeg"


class TestCompressionNoneKeepsOriginal:
    @pytest.mark.asyncio
    async def test_compress_returns_none_uses_original(self) -> None:
        """When _compress_image returns None (failure), original bytes are cached."""
        raw = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.jpg")
        msg = _make_msg(media=(att,))

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=raw,
            ),
            patch(
                "app.channels.media.image_enrichment._compress_image",
                return_value=None,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/orig.jpg"),
        ):
            result = await _download_and_cache(att, msg, None)

        assert result is not None
        assert result["data_url"] == "file:///tmp/cache/orig.jpg"


class TestNoUrlNoPathNoFileId:
    @pytest.mark.asyncio
    async def test_no_source_returns_none(self) -> None:
        """Attachment with no URL, path, or file_id returns None."""
        att = MediaAttachment(media_type=MediaType.IMAGE)
        msg = _make_msg(media=(att,))

        result = await _download_and_cache(att, msg, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_enrichment_with_no_source_returns_original(self) -> None:
        """Full enrichment with source-less attachment returns original message."""
        att = MediaAttachment(media_type=MediaType.IMAGE)
        msg = _make_msg(media=(att,))

        result = await enrich_image_inbound(msg, None)
        assert result is msg


class TestGif87aMime:
    def test_gif87a_detected(self) -> None:
        assert _sniff_mime(b"GIF87adata") == "image/gif"


class TestImmutability:
    @pytest.mark.asyncio
    async def test_original_metadata_not_mutated(self) -> None:
        """Original message metadata dict is not mutated."""
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        original_meta: dict[str, object] = {"existing_key": "value"}
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.jpg")
        msg = _make_msg(media=(att,), metadata=original_meta)

        with (
            patch(
                "app.channels.media.image_enrichment._download_via_http",
                new_callable=AsyncMock,
                return_value=jpeg,
            ),
            patch("app.channels.media.image_enrichment._save_to_cache", return_value="/tmp/cache/img.jpg"),
        ):
            result = await enrich_image_inbound(msg, None)

        assert "image_data_list" not in msg.metadata
        assert "image_data_list" in result.metadata
        assert result.metadata["existing_key"] == "value"
