"""Wiki URL and video import: a link that cannot be read is an error with a code and never touches raw/."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.guards.ssrf import SSRFResult
from myrm_agent_harness.toolkits.wiki import SourceLoadError
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.ingress import ClipIngressResult

from app.api.wiki.routes.schemas_import import ImportUrlsResultResponse, ImportVideoResponse
from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from tests.support.minimal_app import build_minimal_app

_FETCH = "myrm_agent_harness.toolkits.wiki.fetch_url_markdown"
_PUBLISH = "myrm_agent_harness.toolkits.wiki.pipeline.ingress.publish_url_markdown_ingress"
_PUBLISH_VIDEO = "myrm_agent_harness.toolkits.wiki.pipeline.ingress.publish_video_url_ingress"
_YOUTUBE_EXTRACTOR = "myrm_agent_harness.toolkits.wiki.pipeline.ingress.video_ingress.extract_youtube_transcript"
_SSRF_GUARD = "myrm_agent_harness.core.security.guards.ssrf.async_validate_url_for_ssrf"
_VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
_GONE_URL = "https://example.com/gone"
_GONE_REASON = f"No readable content could be fetched from {_GONE_URL}"


@dataclass(frozen=True, slots=True)
class _Loopback:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _loopback_caller_and_public_targets() -> Iterator[None]:
    with (
        patch("app.middleware.auth.resolve_identity", return_value=_Loopback()),
        patch(_SSRF_GUARD, new=AsyncMock(return_value=SSRFResult(safe=True))),
    ):
        yield


@pytest.fixture
def import_client(tmp_path: Path) -> Iterator[tuple[TestClient, WikiStructure]]:
    from app.api.wiki.router import _get_wiki_archiver

    archiver = MemoryToWikiArchiver(MagicMock(), wiki_dir=str(tmp_path / "wiki"))
    archiver._structure.ensure_structure()
    app = build_minimal_app(preset="wiki")

    async def _archiver() -> MemoryToWikiArchiver:
        return archiver

    app.dependency_overrides[_get_wiki_archiver] = _archiver
    yield TestClient(app), archiver._structure
    app.dependency_overrides.clear()


def _import_urls(client: TestClient, urls: list[str], **options: str) -> ImportUrlsResultResponse:
    body = {"urls": urls, "auto_compile": False, "on_conflict": "skip", **options}
    response = client.post("/api/v1/wiki/import/urls", json=body)
    assert response.status_code == 200
    return ImportUrlsResultResponse.model_validate(response.json())


def _import_video(client: TestClient) -> ImportVideoResponse:
    body = {"url": _VIDEO_URL, "auto_compile": False, "on_conflict": "skip"}
    response = client.post("/api/v1/wiki/import/video", json=body)
    assert response.status_code == 200
    return ImportVideoResponse.model_validate(response.json())


def _raw_files(structure: WikiStructure) -> list[Path]:
    return [path for path in structure.raw_dir.rglob("*") if path.is_file()]


def test_unreadable_page_is_an_error_item_and_nothing_is_written(import_client: tuple[TestClient, WikiStructure]) -> None:
    client, structure = import_client

    with patch(_FETCH, new=AsyncMock(side_effect=SourceLoadError(_GONE_REASON))):
        data = _import_urls(client, [_GONE_URL])

    assert data.error_count == 1
    assert data.enqueued_count == 0
    assert [(item.url, item.status, item.error, item.error_code) for item in data.results] == [
        (_GONE_URL, "error", _GONE_REASON, "nothing_readable")
    ]
    assert _raw_files(structure) == []


def test_failed_supersede_keeps_the_source_already_stored(import_client: tuple[TestClient, WikiStructure]) -> None:
    client, structure = import_client
    url = "https://example.com/shared-doc"

    with patch(_FETCH, new=AsyncMock(return_value="# Version 1\n\nFirst edition.")):
        first = _import_urls(client, [url])
    stored = structure.get_raw_file_path(first.results[0].relative_path)
    before = stored.read_text(encoding="utf-8")

    with patch(_FETCH, new=AsyncMock(side_effect=SourceLoadError(f"No readable content could be fetched from {url}"))):
        second = _import_urls(client, [url], on_conflict="supersede", supersede_reason="Updated from upstream website")

    assert second.results[0].status == "error"
    assert second.superseded_count == 0
    assert second.enqueued_count == 0
    assert stored.read_text(encoding="utf-8") == before
    assert "First edition." in before


def test_one_unreadable_url_does_not_stop_the_batch(import_client: tuple[TestClient, WikiStructure]) -> None:
    client, structure = import_client

    async def fetch(url: str) -> str:
        if url == _GONE_URL:
            raise SourceLoadError(_GONE_REASON)
        return "# Readable\n\nBody of the readable page."

    with patch(_FETCH, new=AsyncMock(side_effect=fetch)):
        data = _import_urls(client, ["https://example.com/readable", _GONE_URL])

    assert [(item.status, item.error_code) for item in data.results] == [("success", None), ("error", "nothing_readable")]
    assert data.enqueued_count == 1
    assert data.error_count == 1
    assert len(_raw_files(structure)) == 1


def test_unexpected_fetch_failure_is_an_error_item_without_internal_detail(
    import_client: tuple[TestClient, WikiStructure],
) -> None:
    """The error text goes back to API clients, so the cause of an unforeseen failure stays in the log."""
    client, structure = import_client

    with patch(_FETCH, new=AsyncMock(side_effect=RuntimeError("browser pool exhausted"))):
        data = _import_urls(client, ["https://example.com/page"])

    assert [(item.status, item.error, item.error_code) for item in data.results] == [
        ("error", "Failed to import this URL", "import_failed")
    ]
    assert data.enqueued_count == 0
    assert _raw_files(structure) == []


def test_ingress_that_wrote_nothing_is_an_error_item(import_client: tuple[TestClient, WikiStructure]) -> None:
    client, structure = import_client
    unwritten = ClipIngressResult(relative_path="", written=False, skipped=True, conflict=False, security_blocked=False)

    with (
        patch(_FETCH, new=AsyncMock(return_value="# Readable\n\nBody of the readable page.")),
        patch(_PUBLISH, new=AsyncMock(return_value=unwritten)),
    ):
        data = _import_urls(client, ["https://example.com/page"])

    assert [(item.status, item.error, item.error_code) for item in data.results] == [
        ("error", "Ingress was not written", "import_failed")
    ]
    assert data.error_count == 1
    assert data.enqueued_count == 0
    assert _raw_files(structure) == []


def test_video_without_subtitles_is_an_error_and_nothing_is_written(import_client: tuple[TestClient, WikiStructure]) -> None:
    client, structure = import_client

    with patch(_YOUTUBE_EXTRACTOR, new=AsyncMock(return_value=None)):
        data = _import_video(client)

    assert (data.success, data.status, data.error_code) == (False, "error", "nothing_readable")
    assert data.error == f"Could not fetch subtitles for the YouTube video, or it has no subtitles: {_VIDEO_URL}"
    assert _raw_files(structure) == []


def test_video_address_rejected_by_the_guard_does_not_leak_the_verdict(
    import_client: tuple[TestClient, WikiStructure],
) -> None:
    client, structure = import_client
    verdict = SSRFResult(safe=False, error="Blocked IP: 10.1.2.3 is a non-public IP address")

    with patch(_SSRF_GUARD, new=AsyncMock(return_value=verdict)):
        data = _import_video(client)

    assert (data.status, data.error, data.error_code) == ("error", "This address cannot be imported", "address_rejected")
    assert "10.1.2.3" not in data.model_dump_json()
    assert _raw_files(structure) == []


def test_unexpected_video_failure_is_an_error_without_internal_detail(
    import_client: tuple[TestClient, WikiStructure],
) -> None:
    client, structure = import_client

    with patch(_YOUTUBE_EXTRACTOR, new=AsyncMock(side_effect=RuntimeError("browser pool exhausted"))):
        data = _import_video(client)

    assert (data.status, data.error, data.error_code) == ("error", "Failed to import this video", "import_failed")
    assert "browser pool exhausted" not in data.model_dump_json()
    assert _raw_files(structure) == []


def test_video_ingress_that_wrote_nothing_is_an_error(import_client: tuple[TestClient, WikiStructure]) -> None:
    client, structure = import_client
    unwritten = ClipIngressResult(relative_path="", written=False, skipped=True, conflict=False, security_blocked=False)

    with patch(_PUBLISH_VIDEO, new=AsyncMock(return_value=unwritten)):
        data = _import_video(client)

    assert (data.success, data.status, data.error, data.error_code) == (
        False,
        "error",
        "Ingress was not written",
        "import_failed",
    )
    assert _raw_files(structure) == []


def test_video_security_block_is_told_apart_by_status_and_has_no_error_code(
    import_client: tuple[TestClient, WikiStructure],
) -> None:
    client, _structure = import_client
    blocked = ClipIngressResult(
        relative_path="videos/talk.md", written=False, skipped=False, conflict=False, security_blocked=True
    )

    with patch(_PUBLISH_VIDEO, new=AsyncMock(return_value=blocked)):
        data = _import_video(client)

    assert (data.success, data.status, data.error_code) == (False, "security_blocked", None)
