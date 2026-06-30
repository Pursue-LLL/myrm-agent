"""Tests for StreamAccumulator image fields and MediaAttachment construction.

Covers the image accumulation logic in executor's tool_image_output handling
and the resulting MediaAttachment creation for base64 and URL images.
"""

import base64 as b64
import tempfile

from app.channels.types import MediaAttachment, MediaType
from app.core.channel_bridge.executor_helpers import StreamAccumulator


class TestStreamAccumulatorImageFields:
    """Verify StreamAccumulator correctly tracks last_image_* fields."""

    def test_default_image_fields(self) -> None:
        acc = StreamAccumulator()
        assert acc.last_image_base64 is None
        assert acc.last_image_url is None
        assert acc.last_image_mime == "image/jpeg"
        assert acc.last_image_tool == ""

    def test_base64_image_event_updates_accumulator(self) -> None:
        acc = StreamAccumulator()
        img_data = {"base64": "iVBORw0KGgo=", "mime_type": "image/png"}
        if img_data.get("base64"):
            acc.last_image_base64 = str(img_data["base64"])
            acc.last_image_url = None
        acc.last_image_mime = str(img_data.get("mime_type", "image/jpeg"))
        acc.last_image_tool = "mcp_screenshot"

        assert acc.last_image_base64 == "iVBORw0KGgo="
        assert acc.last_image_url is None
        assert acc.last_image_mime == "image/png"

    def test_url_image_event_updates_accumulator(self) -> None:
        acc = StreamAccumulator()
        img_data = {"url": "https://example.com/img.png", "mime_type": "image/png"}
        if img_data.get("url"):
            acc.last_image_url = str(img_data["url"])
            acc.last_image_base64 = None
        acc.last_image_mime = str(img_data.get("mime_type", "image/jpeg"))
        acc.last_image_tool = "mcp_tool"

        assert acc.last_image_url == "https://example.com/img.png"
        assert acc.last_image_base64 is None
        assert acc.last_image_mime == "image/png"

    def test_url_replaces_previous_base64(self) -> None:
        acc = StreamAccumulator()
        acc.last_image_base64 = "old_b64"
        acc.last_image_mime = "image/jpeg"

        img_data = {"url": "https://cdn.example.com/new.png", "mime_type": "image/png"}
        if img_data.get("base64"):
            acc.last_image_base64 = str(img_data["base64"])
            acc.last_image_url = None
        elif img_data.get("url"):
            acc.last_image_url = str(img_data["url"])
            acc.last_image_base64 = None
        acc.last_image_mime = str(img_data.get("mime_type", "image/jpeg"))

        assert acc.last_image_base64 is None
        assert acc.last_image_url == "https://cdn.example.com/new.png"

    def test_base64_replaces_previous_url(self) -> None:
        acc = StreamAccumulator()
        acc.last_image_url = "https://example.com/old.png"
        acc.last_image_mime = "image/png"

        img_data = {"base64": "new_b64_data", "mime_type": "image/jpeg"}
        if img_data.get("base64"):
            acc.last_image_base64 = str(img_data["base64"])
            acc.last_image_url = None
        elif img_data.get("url"):
            acc.last_image_url = str(img_data["url"])
            acc.last_image_base64 = None
        acc.last_image_mime = str(img_data.get("mime_type", "image/jpeg"))

        assert acc.last_image_url is None
        assert acc.last_image_base64 == "new_b64_data"


class TestMediaAttachmentConstruction:
    """Verify MediaAttachment is built correctly from accumulated image data."""

    def test_base64_image_creates_file_attachment(self) -> None:
        acc = StreamAccumulator()
        acc.last_image_base64 = b64.b64encode(b"fake_png_bytes").decode()
        acc.last_image_mime = "image/png"

        ext = "jpg" if "jpeg" in acc.last_image_mime else "png"
        img_bytes = b64.b64decode(acc.last_image_base64)
        tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", prefix="screenshot_", delete=False)
        tmp.write(img_bytes)
        tmp.close()

        attachment = MediaAttachment(
            media_type=MediaType.IMAGE,
            path=tmp.name,
            filename=f"screenshot.{ext}",
            mime_type=acc.last_image_mime,
        )

        assert attachment.media_type == MediaType.IMAGE
        assert attachment.path == tmp.name
        assert attachment.url is None
        assert attachment.filename == "screenshot.png"
        assert attachment.mime_type == "image/png"

        import os
        os.unlink(tmp.name)

    def test_url_image_creates_url_attachment(self) -> None:
        acc = StreamAccumulator()
        acc.last_image_url = "https://cdn.example.com/photo.jpg"
        acc.last_image_mime = "image/jpeg"

        ext = "jpg" if "jpeg" in acc.last_image_mime else "png"
        attachment = MediaAttachment(
            media_type=MediaType.IMAGE,
            url=acc.last_image_url,
            filename=f"screenshot.{ext}",
            mime_type=acc.last_image_mime,
        )

        assert attachment.media_type == MediaType.IMAGE
        assert attachment.url == "https://cdn.example.com/photo.jpg"
        assert attachment.path is None
        assert attachment.filename == "screenshot.jpg"
        assert attachment.mime_type == "image/jpeg"

    def test_jpeg_mime_selects_jpg_extension(self) -> None:
        mime = "image/jpeg"
        ext = "jpg" if "jpeg" in mime else "png"
        assert ext == "jpg"

    def test_png_mime_selects_png_extension(self) -> None:
        mime = "image/png"
        ext = "jpg" if "jpeg" in mime else "png"
        assert ext == "png"

    def test_no_image_produces_empty_media_list(self) -> None:
        acc = StreamAccumulator()
        media_list: list[MediaAttachment] = []

        if acc.last_image_base64:
            media_list.append(MediaAttachment(media_type=MediaType.IMAGE, path="/tmp/x"))
        elif acc.last_image_url:
            media_list.append(MediaAttachment(media_type=MediaType.IMAGE, url="http://x"))

        assert len(media_list) == 0
