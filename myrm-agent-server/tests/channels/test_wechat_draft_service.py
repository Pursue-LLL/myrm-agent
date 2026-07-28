"""Tests for WeChatDraftService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.channels.providers.wechat.draft_service import (
    WeChatDraftService,
    _build_draft_content,
    _extract_digest,
)
from app.channels.providers.wechat.wechat_api_client import WeChatOfficialApiClient


@pytest.fixture
def html_with_local_image(tmp_path: Path) -> tuple[Path, Path]:
    image = tmp_path / "cover.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    html_path = tmp_path / "article.wechat.html"
    html_path.write_text(
        '<html><body><h1>Title</h1><p>Hello</p><img src="cover.png" alt="cover"></body></html>',
        encoding="utf-8",
    )
    return html_path, image


@pytest.mark.asyncio
async def test_create_draft_uploads_images_and_calls_draft_add(html_with_local_image: tuple[Path, Path]) -> None:
    html_path, _image = html_with_local_image
    client = AsyncMock(spec=WeChatOfficialApiClient)
    client.post_multipart = AsyncMock(
        side_effect=[
            {"url": "https://mmbiz.qpic.cn/content-img"},
            {"media_id": "thumb_media_123"},
        ]
    )
    client.post_json = AsyncMock(return_value={"media_id": "draft_media_456"})

    service = WeChatDraftService(client)
    result = await service.create_draft_from_html_file(html_path, title="Test Article")

    assert result.media_id == "draft_media_456"
    assert result.uploaded_image_count == 1
    assert client.post_multipart.await_count == 2
    draft_payload = client.post_json.await_args.args[1]
    content = draft_payload["articles"][0]["content"]
    assert "https://mmbiz.qpic.cn/content-img" in str(content)
    assert draft_payload["articles"][0]["thumb_media_id"] == "thumb_media_123"


def test_build_draft_content_uses_body_with_embedded_style() -> None:
    processed = (
        "<!DOCTYPE html><html><head><style>h1 { color: red; }</style></head>"
        "<body><h1>Title</h1><p>Hello world</p></body></html>"
    )
    content = _build_draft_content(processed)
    assert "<!DOCTYPE" not in content
    assert "<html" not in content
    assert "<head" not in content
    assert "<style>h1 { color: red; }</style>" in content
    assert "<h1>Title</h1>" in content
    assert _extract_digest("<h1>Title</h1><p>Hello world</p>") == "Title Hello world"


@pytest.mark.asyncio
async def test_create_draft_content_excludes_document_wrapper(tmp_path: Path) -> None:
    image = tmp_path / "cover.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    html_path = tmp_path / "styled.wechat.html"
    html_path.write_text(
        "<!DOCTYPE html><html><head><style>body { font-family: serif; }</style></head>"
        '<body><p>Article body</p><img src="cover.png" alt="cover"></body></html>',
        encoding="utf-8",
    )
    client = AsyncMock(spec=WeChatOfficialApiClient)
    client.post_multipart = AsyncMock(
        side_effect=[
            {"url": "https://mmbiz.qpic.cn/content-img"},
            {"media_id": "thumb_media_123"},
        ]
    )
    client.post_json = AsyncMock(return_value={"media_id": "draft_media_456"})

    service = WeChatDraftService(client)
    await service.create_draft_from_html_file(html_path, title="Styled Article")

    draft_payload = client.post_json.await_args.args[1]
    content = str(draft_payload["articles"][0]["content"])
    digest = str(draft_payload["articles"][0]["digest"])
    assert "<!DOCTYPE" not in content
    assert "<html" not in content
    assert "<style>body { font-family: serif; }</style>" in content
    assert "Article body" in content
    assert "font-family" not in digest


@pytest.mark.asyncio
async def test_create_draft_requires_cover_when_no_images(tmp_path: Path) -> None:
    html_path = tmp_path / "plain.html"
    html_path.write_text("<html><body><p>No images</p></body></html>", encoding="utf-8")
    client = AsyncMock(spec=WeChatOfficialApiClient)
    service = WeChatDraftService(client)

    with pytest.raises(ValueError, match="Cover image required"):
        await service.create_draft_from_html_file(html_path, title="No Cover")


@pytest.mark.asyncio
async def test_create_draft_fails_when_remote_image_upload_fails(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n")
    html_path = tmp_path / "remote.wechat.html"
    html_path.write_text(
        '<html><body><img src="https://example.com/photo.png" alt="remote"></body></html>',
        encoding="utf-8",
    )
    client = AsyncMock(spec=WeChatOfficialApiClient)
    service = WeChatDraftService(client)
    service._upload_remote_content_image = AsyncMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Failed to upload remote image"):
        await service.create_draft_from_html_file(
            html_path,
            title="Remote Fail",
            cover_path=cover,
        )

    client.post_multipart.assert_not_called()
