"""A shared Markdown artifact opens as a styled page under a script-free policy; every other file keeps its own response."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.share.share_csp import MARKDOWN_SHARE_CSP
from app.database.models.artifact import Artifact
from app.services.artifacts.share import markdown_page
from app.services.hosting.packager import PublishFile

pytestmark = pytest.mark.usefixtures("chats_share_workspace")

_REPORT = "# Quarterly report\n\nAll **deliverables** shipped.\n"
_HOSTILE = "# Notes\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[click](javascript:alert(1))\n"


def _share(client: TestClient, artifact: Artifact, files: dict[str, str], artifact_type: str) -> str:
    """Create a share of *files* and return its token."""
    bundle = {path: PublishFile(path=path, content=content, encoding="utf-8") for path, content in files.items()}
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(artifact, bundle),
    ):
        response = client.post(f"/{artifact.id}/share-preview", json={"ttl_days": 7, "artifact_type": artifact_type})
    assert response.status_code == 200
    token: str = response.json()["token"]
    return token


def test_a_markdown_artifact_opens_as_a_styled_page(share_client: TestClient, html_artifact: Artifact) -> None:
    token = _share(share_client, html_artifact, {"report.md": _REPORT}, "document")

    page = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "<h1>Quarterly report</h1>" in page.text
    assert "<strong>deliverables</strong>" in page.text
    assert "<title>report</title>" in page.text


def test_the_page_carries_the_script_free_policy_and_the_privacy_headers(
    share_client: TestClient, html_artifact: Artifact
) -> None:
    token = _share(share_client, html_artifact, {"report.md": _REPORT}, "document")

    page = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)

    assert page.headers["content-security-policy"] == MARKDOWN_SHARE_CSP
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["referrer-policy"] == "no-referrer"


def test_markup_written_in_the_markdown_never_reaches_the_page(share_client: TestClient, html_artifact: Artifact) -> None:
    token = _share(share_client, html_artifact, {"report.md": _HOSTILE}, "document")

    page = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)

    assert page.status_code == 200
    for markup in ("<script", "<img", "<a "):
        assert markup not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text


def test_an_entry_without_a_suffix_is_rendered_by_the_document_type(share_client: TestClient, html_artifact: Artifact) -> None:
    token = _share(share_client, html_artifact, {"report": _REPORT}, "document")

    page = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)

    assert page.headers["content-type"].startswith("text/html")
    assert "<h1>Quarterly report</h1>" in page.text


def test_the_page_follows_the_visitor_language(share_client: TestClient, html_artifact: Artifact) -> None:
    token = _share(share_client, html_artifact, {"report.md": _REPORT}, "document")

    page = share_client.get(f"/public/artifact-share/{token}", headers={"Accept-Language": "zh-CN,zh;q=0.9"})

    assert '<html lang="zh-CN">' in page.text
    assert "由 Myrm Agent 分享" in page.text


def test_a_markdown_file_too_large_to_render_is_served_as_its_source(
    share_client: TestClient, html_artifact: Artifact, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(markdown_page, "_MAX_RENDERED_BYTES", 10)
    token = _share(share_client, html_artifact, {"report.md": _REPORT}, "document")

    page = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/markdown")
    assert page.text == _REPORT
    assert "content-security-policy" not in page.headers


def test_a_markdown_file_inside_a_site_is_served_as_its_source(share_client: TestClient, html_artifact: Artifact) -> None:
    """Only the entry of a share is rendered; a page's own ``notes.md`` link downloads the file as written."""
    token = _share(share_client, html_artifact, {"index.html": "<html></html>", "notes.md": _REPORT}, "html")

    notes = share_client.get(f"/public/artifact-share/{token}/notes.md")

    assert notes.status_code == 200
    assert notes.headers["content-type"].startswith("text/markdown")
    assert notes.text == _REPORT
