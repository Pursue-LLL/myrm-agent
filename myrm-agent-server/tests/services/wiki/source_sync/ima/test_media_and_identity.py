"""Untrusted download URL handling and stable item identity / path layout."""

from __future__ import annotations

import httpx
import pytest

from app.services.wiki.source_sync.ima.errors import ImaPermanentError, ImaTooLargeError, ImaTransientError
from app.services.wiki.source_sync.ima.identity import build_raw_path, kb_item_key, note_item_key
from app.services.wiki.source_sync.ima.media import download_media, validate_media_url

COS_URL = "https://bucket-1.cos.ap-guangzhou.myqcloud.com/file.pdf"


@pytest.mark.parametrize(
    "url",
    [
        "http://bucket.cos.ap-guangzhou.myqcloud.com/f",
        "https://evil.example.com/f",
        "https://myqcloud.com.evil.example.com/f",
        "https://notmyqcloud.com/f",
        "file:///etc/passwd",
        "https:///nohost",
    ],
)
def test_untrusted_media_urls_are_rejected(url: str) -> None:
    with pytest.raises(ImaPermanentError):
        validate_media_url(url)


@pytest.mark.parametrize("url", [COS_URL, "https://res-pkb.ima.qq.com/x", "https://myqcloud.com/x"])
def test_trusted_media_urls_pass(url: str) -> None:
    validate_media_url(url)


async def test_download_returns_bytes_and_forwards_only_safe_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"data")

    body = await download_media(
        COS_URL, {"Authorization": "sig", "Cookie": "x=1", "Host": "evil"}, transport=httpx.MockTransport(handler)
    )

    assert body == b"data"
    assert seen[0].headers["authorization"] == "sig"
    assert "cookie" not in seen[0].headers
    assert seen[0].headers["host"] != "evil"
    assert "ima-openapi-apikey" not in seen[0].headers


async def test_download_never_follows_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example.com/steal"})

    with pytest.raises(ImaTransientError):
        await download_media(COS_URL, {}, transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(("status", "expected"), [(404, ImaPermanentError), (410, ImaPermanentError), (503, ImaTransientError)])
async def test_download_status_classification(status: int, expected: type[Exception]) -> None:
    with pytest.raises(expected):
        await download_media(COS_URL, {}, transport=httpx.MockTransport(lambda request: httpx.Response(status)))


async def test_download_enforces_the_cap_by_advertised_length_and_while_streaming() -> None:
    advertised = httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-length": "100"}, content=b"x" * 100))
    with pytest.raises(ImaTooLargeError):
        await download_media(COS_URL, {}, max_bytes=10, transport=advertised)

    streamed = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 100))
    with pytest.raises(ImaTooLargeError):
        await download_media(COS_URL, {}, max_bytes=10, transport=streamed)


def test_item_keys_are_deterministic_and_scoped() -> None:
    assert kb_item_key("kb", "f", "t") == kb_item_key("kb", "f", "t")
    assert kb_item_key("kb", "f", "t") != kb_item_key("kb", "g", "t")
    assert kb_item_key("kb", "f", "t") != kb_item_key("kb2", "f", "t")
    assert note_item_key("n1") != note_item_key("n2")


def test_renaming_or_moving_a_file_gives_it_a_new_key() -> None:
    key = kb_item_key("kb", "folder-a", "contract.pdf")
    assert kb_item_key("kb", "folder-a", "contract-v2.pdf") != key
    assert kb_item_key("kb", "folder-b", "contract.pdf") != key


def test_same_title_in_different_folders_never_collides() -> None:
    first = build_raw_path(container="Lib", folders=["A"], title="notes.md", item_key=kb_item_key("kb", "A", "notes.md"))
    second = build_raw_path(container="Lib", folders=["B"], title="notes.md", item_key=kb_item_key("kb", "B", "notes.md"))
    assert first != second
    assert first.startswith("ima/Lib/A/notes-") and first.endswith(".md")


def test_path_stays_within_the_gate_budget_for_long_cjk_titles_and_deep_folders() -> None:
    path = build_raw_path(
        container="知识库" * 30,
        folders=["很深的目录" * 10] * 8,
        title="非常长的文档标题" * 40 + ".pdf",
        item_key=kb_item_key("kb", "f", "t"),
    )
    segments = path.split("/")
    assert segments[0] == "ima"
    assert len(segments) <= 2 + 3 + 1  # root + container + at most three folder levels + file
    assert all(len(segment.encode()) <= 200 for segment in segments)
    assert path.endswith(".md")


@pytest.mark.parametrize("name", ["CON", "nul", "Aux.txt", "com1", "LPT9"])
def test_windows_device_names_never_become_a_directory_name(name: str) -> None:
    parts = build_raw_path(container=name, folders=[name], title="doc", item_key="kb_abcdef0123456789").split("/")

    assert parts[1].startswith("_") and parts[2].startswith("_")
    assert build_raw_path(container="Contacts", folders=["Console"], title="x", item_key="k_1") == "ima/Contacts/Console/x-1.md"


def test_known_document_suffix_is_dropped_from_the_stem() -> None:
    path = build_raw_path(container="L", folders=[], title="Report.PDF", item_key="kb_abcdef0123456789")
    assert path == "ima/L/Report-abcdef01.md"
