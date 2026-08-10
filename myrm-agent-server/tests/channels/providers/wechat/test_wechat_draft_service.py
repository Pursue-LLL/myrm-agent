"""Tests for WeChatDraftService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.channels.providers.wechat.draft_service import (
    WeChatDraftService,
    _build_draft_content,
    _extract_body_inner_html,
    _extract_digest,
    _resolve_author,
    _resolve_digest,
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
        '<body><h2 style="border-left: 4px solid #07c160;">Title</h2><p>Hello world</p></body></html>'
    )
    content = _build_draft_content(processed)
    assert "<!DOCTYPE" not in content
    assert "<html" not in content
    assert "<head" not in content
    assert "<style>h1 { color: red; }</style>" in content
    assert 'border-left: 4px solid #07c160' in content
    assert "<h2" in content
    assert _extract_digest("<h2>Title</h2><p>Hello world</p>") == "Title Hello world"


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
async def test_create_draft_returns_compliance_warnings_for_non_blocking_hits(
    html_with_local_image: tuple[Path, Path],
) -> None:
    html_path, _image = html_with_local_image
    html_path.write_text(
        '<html><body><p>这款茶能排毒养颜</p><img src="cover.png" alt="cover"></body></html>',
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
    result = await service.create_draft_from_html_file(html_path, title="Wellness")

    assert result.media_id == "draft_media_456"
    assert len(result.compliance_warnings) == 1
    assert result.compliance_warnings[0]["category"] == "medical_efficacy"
    assert result.compliance_warnings[0]["highRisk"] is False
    assert "排毒" in result.compliance_warnings[0]["terms"]


@pytest.mark.asyncio
async def test_create_draft_blocks_high_risk_title_with_clean_html(
    html_with_local_image: tuple[Path, Path],
) -> None:
    html_path, _image = html_with_local_image
    html_path.write_text(
        '<html><body><p>正常正文</p><img src="cover.png" alt="cover"></body></html>',
        encoding="utf-8",
    )
    client = AsyncMock(spec=WeChatOfficialApiClient)
    service = WeChatDraftService(client)

    from app.services.compliance.wechat_compliance_scan import WeChatComplianceBlockedError

    with pytest.raises(WeChatComplianceBlockedError):
        await service.create_draft_from_html_file(html_path, title="全国第一好茶")

    client.post_multipart.assert_not_called()
    client.post_json.assert_not_called()


@pytest.mark.asyncio
async def test_create_draft_blocks_high_risk_compliance(tmp_path: Path) -> None:
    html_path = tmp_path / "risky.html"
    html_path.write_text(
        "<html><body><p>保本理财，稳赚不赔</p></body></html>",
        encoding="utf-8",
    )
    client = AsyncMock(spec=WeChatOfficialApiClient)
    service = WeChatDraftService(client)

    from app.services.compliance.wechat_compliance_scan import WeChatComplianceBlockedError

    with pytest.raises(WeChatComplianceBlockedError):
        await service.create_draft_from_html_file(html_path, title="Risky")

    client.post_multipart.assert_not_called()
    client.post_json.assert_not_called()


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


@pytest.mark.asyncio
async def test_create_draft_auto_digest_omits_pre_code_high_risk_terms(
    html_with_local_image: tuple[Path, Path],
) -> None:
    html_path, _image = html_with_local_image
    html_path.write_text(
        "<html><body><p>正常教程</p>"
        "<pre><code>保本理财，稳赚不赔</code></pre>"
        '<img src="cover.png" alt="cover"></body></html>',
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
    result = await service.create_draft_from_html_file(html_path, title="Python教程")

    assert result.media_id == "draft_media_456"
    draft_payload = client.post_json.await_args.args[1]
    digest = str(draft_payload["articles"][0]["digest"])
    assert "保本" not in digest
    assert "正常教程" in digest


def test_extract_digest_skips_pre_code_blocks() -> None:
    html = (
        "<html><body><p>正常正文</p>"
        "<pre><code>保本理财，稳赚不赔</code></pre>"
        "</body></html>"
    )
    assert _extract_digest(html) == "正常正文"


def test_resolve_author_clamps_to_wechat_limit() -> None:
    assert _resolve_author("Myrm") == "Myrm"
    assert _resolve_author("某某科技有限公司部") == "某某科技有限公司"
    assert _resolve_author("123456789") == "12345678"


@pytest.mark.asyncio
async def test_create_draft_raises_when_html_file_missing(tmp_path: Path) -> None:
    client = AsyncMock(spec=WeChatOfficialApiClient)
    service = WeChatDraftService(client)

    with pytest.raises(FileNotFoundError, match="HTML file not found"):
        await service.create_draft_from_html_file(tmp_path / "missing.html", title="Missing")

    client.post_json.assert_not_called()


@pytest.mark.asyncio
async def test_create_draft_raises_when_wechat_returns_no_media_id(
    html_with_local_image: tuple[Path, Path],
) -> None:
    html_path, _image = html_with_local_image
    client = AsyncMock(spec=WeChatOfficialApiClient)
    client.post_multipart = AsyncMock(
        side_effect=[
            {"url": "https://mmbiz.qpic.cn/content-img"},
            {"media_id": "thumb_media_123"},
        ]
    )
    client.post_json = AsyncMock(return_value={"errcode": 0})

    service = WeChatDraftService(client)
    with pytest.raises(RuntimeError, match="no media_id"):
        await service.create_draft_from_html_file(html_path, title="Broken Draft")


@pytest.mark.asyncio
async def test_create_draft_rejects_inline_data_uri_image(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n")
    html_path = tmp_path / "data-uri.html"
    html_path.write_text(
        '<html><body><img src="data:image/png;base64,abc" alt="inline"></body></html>',
        encoding="utf-8",
    )
    client = AsyncMock(spec=WeChatOfficialApiClient)
    service = WeChatDraftService(client)

    with pytest.raises(ValueError, match="data: URI"):
        await service.create_draft_from_html_file(
            html_path,
            title="Data URI",
            cover_path=cover,
        )


@pytest.mark.asyncio
async def test_create_draft_raises_when_inline_local_image_missing(
    html_with_local_image: tuple[Path, Path],
) -> None:
    html_path, _image = html_with_local_image
    html_path.write_text(
        '<html><body><p>Body</p><img src="missing.png" alt="missing"></body></html>',
        encoding="utf-8",
    )
    client = AsyncMock(spec=WeChatOfficialApiClient)
    service = WeChatDraftService(client)

    with pytest.raises(ValueError, match="Inline image not found"):
        await service.create_draft_from_html_file(html_path, title="Missing Inline")


@pytest.mark.asyncio
async def test_create_draft_raises_when_uploadimg_returns_no_url(
    html_with_local_image: tuple[Path, Path],
) -> None:
    html_path, _image = html_with_local_image
    client = AsyncMock(spec=WeChatOfficialApiClient)
    client.post_multipart = AsyncMock(return_value={})
    service = WeChatDraftService(client)

    with pytest.raises(RuntimeError, match="uploadimg failed"):
        await service.create_draft_from_html_file(html_path, title="Upload Fail")


@pytest.mark.asyncio
async def test_create_draft_uses_explicit_cover_path(tmp_path: Path) -> None:
    cover = tmp_path / "explicit-cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n")
    html_path = tmp_path / "no-inline-images.html"
    html_path.write_text("<html><body><p>Text only article body here for digest.</p></body></html>", encoding="utf-8")

    client = AsyncMock(spec=WeChatOfficialApiClient)
    client.post_multipart = AsyncMock(return_value={"media_id": "thumb_from_cover"})
    client.post_json = AsyncMock(return_value={"media_id": "draft_media_789"})

    service = WeChatDraftService(client)
    result = await service.create_draft_from_html_file(
        html_path,
        title="Cover Path",
        cover_path=cover,
    )

    assert result.media_id == "draft_media_789"
    assert client.post_multipart.await_count == 1
    thumb_call = client.post_multipart.await_args_list[0]
    assert thumb_call.kwargs["extra_params"] == {"type": "thumb"}


@pytest.mark.asyncio
async def test_create_draft_uploads_remote_image_successfully(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n")
    html_path = tmp_path / "remote-success.html"
    html_path.write_text(
        '<html><body><p>Remote image article with enough visible text for digest extraction.</p>'
        '<img src="https://cdn.example.com/photo.png" alt="remote"></body></html>',
        encoding="utf-8",
    )

    class _FakeResponse:
        status_code = 200
        content = b"\x89PNGremote"

    class _FakeAsyncClient:
        def __init__(self, timeout: float = 30.0) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> _FakeResponse:
            assert url == "https://cdn.example.com/photo.png"
            return _FakeResponse()

    monkeypatch.setattr(
        "app.channels.providers.wechat.draft_service.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    client = AsyncMock(spec=WeChatOfficialApiClient)
    client.post_multipart = AsyncMock(
        side_effect=[
            {"url": "https://mmbiz.qpic.cn/remote-img"},
            {"media_id": "thumb_media_remote"},
        ]
    )
    client.post_json = AsyncMock(return_value={"media_id": "draft_remote"})

    service = WeChatDraftService(client)
    result = await service.create_draft_from_html_file(
        html_path,
        title="Remote OK",
        cover_path=cover,
    )

    assert result.media_id == "draft_remote"
    assert result.uploaded_image_count == 1
    draft_payload = client.post_json.await_args.args[1]
    assert "https://mmbiz.qpic.cn/remote-img" in str(draft_payload["articles"][0]["content"])


@pytest.mark.asyncio
async def test_create_draft_raises_when_thumb_upload_returns_no_media_id(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n")
    html_path = tmp_path / "thumb-fail.html"
    html_path.write_text("<html><body><p>Enough text for compliance scan to pass here.</p></body></html>", encoding="utf-8")

    client = AsyncMock(spec=WeChatOfficialApiClient)
    client.post_multipart = AsyncMock(return_value={})
    service = WeChatDraftService(client)

    with pytest.raises(RuntimeError, match="thumb upload failed"):
        await service.create_draft_from_html_file(
            html_path,
            title="Thumb Fail",
            cover_path=cover,
        )


@pytest.mark.asyncio
async def test_create_draft_uses_user_provided_digest(
    html_with_local_image: tuple[Path, Path],
) -> None:
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
    await service.create_draft_from_html_file(
        html_path,
        title="Custom Digest",
        digest="用户自定义摘要",
    )

    draft_payload = client.post_json.await_args.args[1]
    assert draft_payload["articles"][0]["digest"] == "用户自定义摘要"


def test_extract_body_inner_html_without_body_tag() -> None:
    html = "<div><p>No body wrapper</p></div>"
    body = _extract_body_inner_html(html)
    assert "No body wrapper" in body
    content = _build_draft_content(html)
    assert "No body wrapper" in content


def test_resolve_digest_prefers_user_value() -> None:
    html = "<html><body><p>Auto digest source text</p></body></html>"
    assert _resolve_digest(html, "  手工摘要  ") == "手工摘要"


@pytest.mark.asyncio
async def test_create_draft_raises_when_cover_path_missing(tmp_path: Path) -> None:
    html_path = tmp_path / "cover-missing.html"
    html_path.write_text("<html><body><p>正文</p></body></html>", encoding="utf-8")
    missing_cover = tmp_path / "missing-cover.png"
    client = AsyncMock(spec=WeChatOfficialApiClient)
    service = WeChatDraftService(client)

    with pytest.raises(FileNotFoundError, match="Cover image not found"):
        await service.create_draft_from_html_file(
            html_path,
            title="Missing Cover",
            cover_path=missing_cover,
        )
