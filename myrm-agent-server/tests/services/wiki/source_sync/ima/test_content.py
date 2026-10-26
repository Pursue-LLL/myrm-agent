"""Item resolution: which stack handles each ima media type, and how lossy outcomes are named."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from myrm_agent_harness.toolkits.web_fetch.extractors import WEIXIN_BODY_TRUNCATED_MARKER
from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.services.wiki.source_sync.ima import content as content_module
from app.services.wiki.source_sync.ima.content import (
    ImaContent,
    ImaDuplicate,
    ImaUnsupported,
    render_document,
    resolve_kb_item,
    resolve_note,
)
from app.services.wiki.source_sync.ima.errors import ImaPageUnavailableError
from app.services.wiki.source_sync.ima.ledger import LedgerRow
from app.services.wiki.source_sync.ima.models import ImaMediaInfo

from .support import FakeIma, as_client

WEB_URL = "https://mp.weixin.qq.com/s/abc"
COS_URL = "https://b.cos.ap-guangzhou.myqcloud.com/f"


def row(title: str = "Doc", media_type: int | None = 7) -> LedgerRow:
    return LedgerRow(
        item_key="kb_abc123def456",
        container_id="kb1",
        container_name="Lib",
        remote_id="m1",
        title=title,
        folder_path="Sub",
        media_type=media_type,
        remote_version="m1",
        synced_version="",
        status="pending",
        fidelity="",
        fidelity_notes=(),
        raw_path="",
        attempts=0,
        error_kind="",
    )


async def covered(_note_id: str) -> bool:
    return False


async def _resolve(fake: FakeIma, tmp_path: Path, *, item: LedgerRow | None = None, note_covered=covered):
    return await resolve_kb_item(
        as_client(fake),
        item or row(),
        structure=WikiStructure(base_dir=tmp_path),
        raw_relative="ima/Lib/Doc-abc123de.md",
        note_covered=note_covered,
    )


def test_render_document_is_deterministic_and_carries_provenance() -> None:
    body = ImaContent(body="text", lossy=("plain_text",), source_url="https://x/y", type_label="note")
    first = render_document(row=row(), content=body, modified="2024-01-02")
    assert first == render_document(row=row(), content=body, modified="2024-01-02")
    assert 'source: "ima"' in first and 'ima_container: "Lib"' in first and 'fidelity: "partial"' in first
    assert 'fidelity_notes: "plain_text"' in first and 'source_url: "https://x/y"' in first
    assert 'modified: "2024-01-02"' in first
    assert "# Doc\n\ntext" in first


def test_render_document_does_not_repeat_an_existing_heading() -> None:
    rendered = render_document(row=row(), content=ImaContent(body="# Own heading\n\nbody"))
    assert rendered.count("# ") == 1
    assert 'fidelity: "full"' in rendered


async def test_unknown_media_type_is_unsupported(tmp_path: Path) -> None:
    fake = FakeIma(media={"m1": ImaMediaInfo(media_type=None, url="", headers={}, note_id="")})
    assert await _resolve(fake, tmp_path, item=row(media_type=None)) == ImaUnsupported("unsupported_type")


async def test_audio_and_video_are_unsupported(tmp_path: Path) -> None:
    fake = FakeIma(media={"m1": ImaMediaInfo(media_type=15, url=COS_URL, headers={}, note_id="")})
    assert await _resolve(fake, tmp_path) == ImaUnsupported("unsupported_type")


async def test_document_without_download_url_is_unsupported(tmp_path: Path) -> None:
    fake = FakeIma(media={"m1": ImaMediaInfo(media_type=7, url="", headers={}, note_id="")})
    assert await _resolve(fake, tmp_path) == ImaUnsupported("no_download_url")


async def test_note_already_covered_is_a_duplicate_and_otherwise_plain_text(tmp_path: Path) -> None:
    fake = FakeIma(media={"m1": ImaMediaInfo(media_type=11, url="", headers={}, note_id="n1")}, note_text={"n1": "note words"})

    async def is_covered(_note_id: str) -> bool:
        return True

    assert isinstance(await _resolve(fake, tmp_path, note_covered=is_covered), ImaDuplicate)
    resolved = await _resolve(fake, tmp_path)
    assert resolved == ImaContent(body="note words", lossy=("plain_text",), type_label="note")


async def test_empty_note_is_unsupported() -> None:
    assert await resolve_note(as_client(FakeIma(note_text={"n1": ""})), "n1") == ImaUnsupported("no_text")


async def test_saved_web_page_goes_through_web_fetch_and_flags_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched: list[tuple[str, bool]] = []

    async def crawl(url: str, *, allow_escalation: bool) -> SimpleNamespace:
        fetched.append((url, allow_escalation))
        return SimpleNamespace(page_content=f"article body\n\n{WEIXIN_BODY_TRUNCATED_MARKER}")

    monkeypatch.setattr(content_module.web_fetch_tools, "crawl", crawl)
    fake = FakeIma(media={"m1": ImaMediaInfo(media_type=6, url=WEB_URL, headers={}, note_id="")})

    resolved = await _resolve(fake, tmp_path, item=row(media_type=6))

    assert isinstance(resolved, ImaContent)
    assert fetched == [(WEB_URL, False)]
    assert resolved.source_url == WEB_URL and "body_truncated" in resolved.lossy and resolved.type_label == "wechat"


async def test_unreachable_web_page_is_retryable_not_unsupported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def crawl(url: str, *, allow_escalation: bool) -> None:
        return None

    monkeypatch.setattr(content_module.web_fetch_tools, "crawl", crawl)
    fake = FakeIma(media={"m1": ImaMediaInfo(media_type=2, url=WEB_URL, headers={}, note_id="")})

    with pytest.raises(ImaPageUnavailableError):
        await _resolve(fake, tmp_path, item=row(media_type=2))


async def test_web_snapshot_with_signed_headers_is_downloaded_as_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def download(url: str, headers: dict[str, str]) -> bytes:
        assert headers == {"Authorization": "sig"}
        return b"<html><body><h1>Snapshot</h1></body></html>"

    async def to_markdown(html: str, *, base_url: str) -> str:
        return "# Snapshot\n\n![chart](https://cdn.example.com/c.png)"

    async def keep_images(structure: object, body: str, *, base_url: str, raw_relative: str) -> tuple[str, int]:
        return body, 0

    monkeypatch.setattr(content_module, "download_media", download)
    monkeypatch.setattr(content_module, "_html_to_markdown", to_markdown)
    monkeypatch.setattr(content_module, "localize_public_markdown_images", keep_images)
    fake = FakeIma(media={"m1": ImaMediaInfo(media_type=6, url=COS_URL, headers={"Authorization": "sig"}, note_id="")})

    resolved = await _resolve(fake, tmp_path, item=row(media_type=6))

    assert isinstance(resolved, ImaContent)
    assert "Snapshot" in resolved.body and resolved.lossy == ("images_remote",)


async def test_pdf_text_is_marked_layout_flattened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def download(url: str, headers: dict[str, str]) -> bytes:
        return b"%PDF"

    async def convert(data: bytes, **kwargs: object) -> str:
        assert kwargs["filename"] == "Doc.pdf"
        return "pdf text"

    monkeypatch.setattr(content_module, "download_media", download)
    monkeypatch.setattr(content_module, "bytes_to_wiki_markdown", convert)
    fake = FakeIma(media={"m1": ImaMediaInfo(media_type=1, url=COS_URL, headers={}, note_id="")})

    resolved = await _resolve(fake, tmp_path, item=row(media_type=1))

    assert resolved == ImaContent(body="pdf text", lossy=("layout_flattened",), type_label="pdf")


async def test_document_that_converts_to_nothing_is_unsupported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def download(url: str, headers: dict[str, str]) -> bytes:
        return b"scan"

    async def convert(data: bytes, **kwargs: object) -> str:
        return ""

    monkeypatch.setattr(content_module, "download_media", download)
    monkeypatch.setattr(content_module, "bytes_to_wiki_markdown", convert)
    fake = FakeIma(media={"m1": ImaMediaInfo(media_type=1, url=COS_URL, headers={}, note_id="")})

    assert await _resolve(fake, tmp_path, item=row(media_type=1)) == ImaUnsupported("no_text")
