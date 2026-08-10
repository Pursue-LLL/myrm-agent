"""WeChat Official Account draft publishing (uploadimg + draft/add).

[INPUT]
- wechat_api_client::WeChatOfficialApiClient (POS: shared token client)
- compliance::wechat_compliance_scan (POS: draft-bound visible-text compliance scan)
- pathlib, re, httpx (HTML/image processing)

[OUTPUT]
- WeChatDraftResult: draft creation outcome (includes non-blocking compliance warnings)
- WeChatDraftService: upload inline images + create draft article

[POS]
Business-layer WeChat article draft pipeline. Inline content images upload before thumb to avoid orphan media.
Invoked from API HITL endpoint only; not an agent tool.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import httpx

from app.channels.providers.wechat.wechat_api_client import WeChatOfficialApiClient
from app.services.compliance.wechat_compliance_scan import (
    assert_wechat_draft_compliance_for_publish,
    compliance_hits_payload,
    extract_visible_text_from_html,
)

logger = logging.getLogger(__name__)

_IMG_SRC_RE = re.compile(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'][^>]*>)', re.IGNORECASE)
_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_BODY_INNER_RE = re.compile(r"<body[^>]*>(.*)</body>", re.IGNORECASE | re.DOTALL)
_MAX_DIGEST_LEN = 120
_MAX_AUTHOR_LEN = 8
_MAX_REMOTE_IMAGE_BYTES = 5_000_000


@dataclass(frozen=True, slots=True)
class WeChatDraftResult:
    media_id: str
    uploaded_image_count: int
    compliance_warnings: tuple[dict[str, object], ...] = ()


class _ImgSrcCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        for key, value in attrs:
            if key.lower() == "src" and value:
                self.sources.append(value)


class WeChatDraftService:
    """Publish HTML articles to the WeChat Official Account draft box."""

    def __init__(self, client: WeChatOfficialApiClient) -> None:
        self._client = client

    async def create_draft_from_html_file(
        self,
        html_path: Path,
        *,
        title: str,
        author: str = "",
        digest: str = "",
        cover_path: Path | None = None,
        locale: str = "zh",
    ) -> WeChatDraftResult:
        if not html_path.is_file():
            raise FileNotFoundError(f"HTML file not found: {html_path}")

        raw_html = html_path.read_text(encoding="utf-8")
        resolved_digest = _resolve_digest(raw_html, digest)
        resolved_author = _resolve_author(author)
        compliance_result = assert_wechat_draft_compliance_for_publish(
            raw_html,
            title=title,
            digest=resolved_digest,
            locale=locale,
        )
        compliance_warnings = tuple(
            hit
            for hit in compliance_hits_payload(compliance_result, locale=locale)
            if hit.get("highRisk") is not True
        )
        base_dir = html_path.parent

        processed_html, upload_count = await self._rewrite_inline_images(raw_html, base_dir)
        thumb_media_id = await self._resolve_thumb_media_id(
            raw_html,
            base_dir,
            cover_path=cover_path,
        )

        draft_content = _build_draft_content(processed_html)

        payload: dict[str, object] = {
            "articles": [
                {
                    "title": title.strip(),
                    "author": resolved_author,
                    "digest": resolved_digest[:_MAX_DIGEST_LEN],
                    "content": draft_content,
                    "content_source_url": "",
                    "thumb_media_id": thumb_media_id,
                    "need_open_comment": 0,
                    "only_fans_can_comment": 0,
                }
            ]
        }
        data = await self._client.post_json("draft/add", payload)
        media_id = data.get("media_id")
        if not isinstance(media_id, str) or not media_id:
            raise RuntimeError(f"WeChat draft/add returned no media_id: {data}")
        return WeChatDraftResult(
            media_id=media_id,
            uploaded_image_count=upload_count,
            compliance_warnings=compliance_warnings,
        )

    async def _rewrite_inline_images(self, html: str, base_dir: Path) -> tuple[str, int]:
        upload_count = 0

        async def replace_src(match: re.Match[str]) -> str:
            nonlocal upload_count
            prefix, src, suffix = match.group(1), match.group(2), match.group(3)
            if src.startswith(("http://", "https://")):
                wx_url = await self._upload_remote_content_image(src)
                if not wx_url:
                    raise ValueError(f"Failed to upload remote image to WeChat CDN: {src}")
                upload_count += 1
                return f"{prefix}{wx_url}{suffix}"
            if src.startswith("data:"):
                raise ValueError("Inline data: URI images are not supported for WeChat drafts")

            local_path = (base_dir / src).resolve()
            if not local_path.is_file():
                raise ValueError(f"Inline image not found: {local_path}")

            wx_url = await self._upload_local_content_image(local_path)
            upload_count += 1
            return f"{prefix}{wx_url}{suffix}"

        parts: list[str] = []
        last = 0
        for match in _IMG_SRC_RE.finditer(html):
            parts.append(html[last : match.start()])
            parts.append(await replace_src(match))
            last = match.end()
        parts.append(html[last:])
        return "".join(parts), upload_count

    async def _upload_local_content_image(self, path: Path) -> str:
        content = path.read_bytes()
        data = await self._client.post_multipart(
            "media/uploadimg",
            field_name="media",
            filename=path.name,
            content=content,
        )
        url = data.get("url")
        if not isinstance(url, str) or not url:
            raise RuntimeError(f"WeChat uploadimg failed for {path.name}: {data}")
        return url

    async def _upload_remote_content_image(self, url: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.get(url)
                if resp.status_code >= 400:
                    logger.warning("WeChat draft: failed to download image %s", url)
                    return None
                if len(resp.content) > _MAX_REMOTE_IMAGE_BYTES:
                    logger.warning("WeChat draft: remote image too large (%s bytes): %s", len(resp.content), url)
                    return None
                filename = url.rsplit("/", 1)[-1].split("?", 1)[0] or "image.png"
                data = await self._client.post_multipart(
                    "media/uploadimg",
                    field_name="media",
                    filename=filename,
                    content=resp.content,
                )
                wx_url = data.get("url")
                return wx_url if isinstance(wx_url, str) else None
        except Exception as exc:
            logger.warning("WeChat draft: remote image upload failed for %s: %s", url, exc)
            return None

    async def _resolve_thumb_media_id(
        self,
        html: str,
        base_dir: Path,
        *,
        cover_path: Path | None,
    ) -> str:
        candidate_paths: list[Path] = []
        if cover_path is not None:
            candidate_paths.append(cover_path.resolve())

        collector = _ImgSrcCollector()
        collector.feed(html)
        for src in collector.sources:
            if src.startswith(("http://", "https://", "data:")):
                continue
            local = (base_dir / src).resolve()
            if local.is_file():
                candidate_paths.append(local)

        if not candidate_paths:
            raise ValueError(
                "Cover image required: provide coverPath or include at least one local image in the HTML"
            )

        thumb_path = candidate_paths[0]
        if not thumb_path.is_file():
            raise FileNotFoundError(f"Cover image not found: {thumb_path}")

        data = await self._client.post_multipart(
            "media/upload",
            field_name="media",
            filename=thumb_path.name,
            content=thumb_path.read_bytes(),
            extra_params={"type": "thumb"},
        )
        media_id = data.get("media_id")
        if not isinstance(media_id, str) or not media_id:
            raise RuntimeError(f"WeChat thumb upload failed: {data}")
        return media_id


def _extract_head_style(html: str) -> str:
    blocks: list[str] = []
    for match in _STYLE_BLOCK_RE.finditer(html):
        css = match.group(1).strip()
        if css:
            blocks.append(css)
    return "\n".join(blocks)


def _extract_body_inner_html(html: str) -> str:
    match = _BODY_INNER_RE.search(html)
    if match:
        return match.group(1).strip()

    stripped = re.sub(r"(?is)<!DOCTYPE[^>]*>", "", html)
    stripped = re.sub(r"(?is)<head[^>]*>.*?</head>", "", stripped)
    stripped = re.sub(r"(?is)</?html[^>]*>", "", stripped)
    stripped = re.sub(r"(?is)</?body[^>]*>", "", stripped)
    return stripped.strip()


def _build_draft_content(processed_html: str) -> str:
    body = _extract_body_inner_html(processed_html)
    style = _extract_head_style(processed_html)
    if style:
        return f"<style>{style}</style>\n{body}"
    return body


def _resolve_author(author: str) -> str:
    return author.strip()[:_MAX_AUTHOR_LEN]


def _resolve_digest(html: str, user_digest: str) -> str:
    stripped = user_digest.strip()
    if stripped:
        return stripped[:_MAX_DIGEST_LEN]
    return _extract_digest(html)


def _extract_digest(html: str) -> str:
    visible = extract_visible_text_from_html(html)
    text = re.sub(r"\s+", " ", visible).strip()
    return text[:_MAX_DIGEST_LEN]
