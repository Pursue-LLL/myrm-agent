
from app.channels.media.video_enrichment import (
    enrich_video_inbound,
    has_video_attachment,
)
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
)


def _make_msg(
    media: list[MediaAttachment] | None = None,
    content: str = "Hello",
) -> InboundMessage:
    return InboundMessage(
        channel="discord",
        sender_id="user123",
        content=content,
        media=media or [],
        metadata={},
    )


class TestHasVideoAttachment:
    def test_no_media(self):
        msg = _make_msg()
        assert has_video_attachment(msg) is False

    def test_image_only(self):
        msg = _make_msg(
            media=[
                MediaAttachment(
                    media_type=MediaType.IMAGE,
                    url="https://example.com/img.png",
                )
            ]
        )
        assert has_video_attachment(msg) is False

    def test_video_present(self):
        msg = _make_msg(
            media=[
                MediaAttachment(
                    media_type=MediaType.VIDEO,
                    url="https://example.com/clip.mp4",
                    filename="clip.mp4",
                )
            ]
        )
        assert has_video_attachment(msg) is True

    def test_mixed_media(self):
        msg = _make_msg(
            media=[
                MediaAttachment(media_type=MediaType.IMAGE, url="img.png"),
                MediaAttachment(media_type=MediaType.VIDEO, url="vid.mp4"),
            ]
        )
        assert has_video_attachment(msg) is True


class TestEnrichVideoInbound:
    def test_no_video_returns_unchanged(self):
        msg = _make_msg(content="Hello")
        result = enrich_video_inbound(msg)
        assert result.content == "Hello"
        assert "video_attachments" not in result.metadata

    def test_single_video_enrichment(self):
        msg = _make_msg(
            content="Check this out",
            media=[
                MediaAttachment(
                    media_type=MediaType.VIDEO,
                    url="https://cdn.example.com/clip.mp4",
                    filename="clip.mp4",
                    mime_type="video/mp4",
                )
            ],
        )
        result = enrich_video_inbound(msg)

        assert "video_attachments" in result.metadata
        assert result.metadata["has_video"] is True
        assert len(result.metadata["video_attachments"]) == 1

        att_info = result.metadata["video_attachments"][0]
        assert att_info["url"] == "https://cdn.example.com/clip.mp4"
        assert att_info["filename"] == "clip.mp4"
        assert att_info["mime_type"] == "video/mp4"

        assert "[Video: clip.mp4]" in result.content
        assert "Check this out" in result.content

    def test_video_with_caption(self):
        msg = _make_msg(
            content="",
            media=[
                MediaAttachment(
                    media_type=MediaType.VIDEO,
                    url="https://example.com/v.mov",
                    filename="meeting.mov",
                    caption="Q3 Planning",
                )
            ],
        )
        result = enrich_video_inbound(msg)
        assert "[Video: meeting.mov — Q3 Planning]" in result.content

    def test_multiple_videos(self):
        msg = _make_msg(
            content="Two clips",
            media=[
                MediaAttachment(
                    media_type=MediaType.VIDEO,
                    url="https://example.com/a.mp4",
                    filename="a.mp4",
                ),
                MediaAttachment(
                    media_type=MediaType.VIDEO,
                    url="https://example.com/b.mp4",
                    filename="b.mp4",
                ),
            ],
        )
        result = enrich_video_inbound(msg)
        assert len(result.metadata["video_attachments"]) == 2
        assert "[Video: a.mp4]" in result.content
        assert "[Video: b.mp4]" in result.content
        assert "Two clips" in result.content

    def test_video_without_filename(self):
        msg = _make_msg(
            content="",
            media=[
                MediaAttachment(
                    media_type=MediaType.VIDEO,
                    url="https://example.com/unnamed.webm",
                )
            ],
        )
        result = enrich_video_inbound(msg)
        assert "[Video: video_1]" in result.content

    def test_immutability(self):
        msg = _make_msg(
            content="Original",
            media=[
                MediaAttachment(
                    media_type=MediaType.VIDEO,
                    url="https://example.com/v.mp4",
                    filename="v.mp4",
                )
            ],
        )
        result = enrich_video_inbound(msg)
        assert msg.content == "Original"
        assert "video_attachments" not in msg.metadata
        assert result is not msg
