"""Security headers of served shares: which responses carry the CSP, and what the policy allows."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.api.files.artifact_share_public import (
    _HTML_MEDIA_TYPES,
    _SHARE_SECURITY_HEADERS,
    _file_response,
)
from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.hosting.packager import PublishFile
from tests.support.detached_artifact import make_detached_artifact

pytestmark = pytest.mark.usefixtures("chats_share_workspace")


@pytest.mark.asyncio
async def test_html_share_includes_csp_headers(share_client, html_artifact) -> None:
    files = {
        "index.html": PublishFile(path="index.html", content="<html></html>", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    token = response.json()["token"]
    index = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert index.status_code == 200
    csp = index.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp
    assert "'self'" in csp
    assert "connect-src 'none'" in csp
    assert index.headers.get("x-content-type-options") == "nosniff"
    assert index.headers.get("x-frame-options") == "DENY"
    assert index.headers.get("x-robots-tag") == "noindex, nofollow"
    assert index.headers.get("cache-control") == "no-store"
    assert index.headers.get("referrer-policy") == "no-referrer"


@pytest.mark.asyncio
async def test_pdf_share_omits_csp_headers(share_client, html_artifact) -> None:
    files = {
        "report.pdf": PublishFile(path="report.pdf", content="JVBERi0=", encoding="base64"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "pdf"},
        )
    token = response.json()["token"]
    entry = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert entry.status_code == 200
    assert "content-security-policy" not in entry.headers
    assert entry.headers.get("x-robots-tag") == "noindex, nofollow"
    assert entry.headers.get("cache-control") == "no-store"
    assert entry.headers.get("referrer-policy") == "no-referrer"


@pytest.mark.asyncio
async def test_multi_file_bundle_csp_allows_self(share_client, html_artifact) -> None:
    """CSP 'self' allows same-origin CSS/JS in multi-file bundles."""
    files = {
        "index.html": PublishFile(
            path="index.html",
            content='<html><link href="styles.css"/></html>',
            encoding="utf-8",
        ),
        "styles.css": PublishFile(path="styles.css", content="body{}", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    token = response.json()["token"]
    index = share_client.get(f"/public/artifact-share/{token}/", follow_redirects=False)
    csp = index.headers.get("content-security-policy", "")
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data: blob:" in csp

    css = share_client.get(f"/public/artifact-share/{token}/styles.css")
    assert css.status_code == 200
    assert "content-security-policy" not in css.headers
    assert css.headers.get("x-robots-tag") == "noindex, nofollow"
    assert css.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_csp_integration_html_real_vault(share_client, db_session, workspace) -> None:
    """Integration: real Vault → create share → public GET → CSP headers present."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(workspace))
    uri = vault.put("<html><body>hello</body></html>", "index.html")

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="index.html",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    ver = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=uri,
        sha256_hash="h_csp",
    )
    db_session.add(ver)
    await db_session.commit()
    await db_session.refresh(artifact)

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        resp = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert resp.status_code == 200
    token = resp.json()["token"]

    serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert serve.status_code == 200
    csp = serve.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "connect-src 'none'" in csp
    assert serve.headers.get("x-content-type-options") == "nosniff"
    assert serve.headers.get("x-frame-options") == "DENY"


@pytest.mark.asyncio
async def test_csp_integration_multi_file_bundle(share_client, db_session, workspace) -> None:
    """Integration: multi-file bundle with real Vault → CSP on HTML, no CSP on CSS asset."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(workspace))
    uri = vault.put(
        '<html><link rel="stylesheet" href="style.css"/><body>test</body></html>',
        "index.html",
    )

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="index.html",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    ver = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=uri,
        sha256_hash="h_multi",
    )
    db_session.add(ver)
    await db_session.commit()
    await db_session.refresh(artifact)

    detached = make_detached_artifact(
        artifact_id=artifact.id,
        name="index.html",
        chat_id=artifact.chat_id,
        versions=[ver],
    )
    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        resp = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert resp.status_code == 200
    token = resp.json()["token"]

    index_resp = share_client.get(
        f"/public/artifact-share/{token}",
        follow_redirects=False,
    )
    assert index_resp.status_code == 200
    csp = index_resp.headers.get("content-security-policy", "")
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data: blob:" in csp


@pytest.mark.asyncio
async def test_csp_integration_pdf_real_vault(share_client, db_session, workspace) -> None:
    """Integration: real Vault PDF → public GET → correct media type + no HTML headers.

    Vault objects are extension-less UUID files; the entry name now derives
    from artifact.name (report.pdf), so a PDF is served as ``application/pdf``
    and deliberately omits the HTML-only security headers (CSP/nosniff).
    """
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(workspace))
    uri = vault.put("%PDF-1.4 dummy", "report.pdf")

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="report.pdf",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    ver = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=uri,
        sha256_hash="h_pdf",
    )
    db_session.add(ver)
    await db_session.commit()
    await db_session.refresh(artifact)

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        resp = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "pdf"},
        )
    assert resp.status_code == 200
    token = resp.json()["token"]

    serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert serve.status_code == 200
    assert serve.headers["content-type"].startswith("application/pdf")
    assert serve.headers.get("x-content-type-options") is None


# ---------------------------------------------------------------------------
# _file_response unit tests (direct function, no HTTP)
# ---------------------------------------------------------------------------


class TestFileResponseCSP:
    """Exhaustive _file_response media_type → header boundary tests."""

    def _make_tmp_file(self, tmp_path: Path) -> str:
        p = tmp_path / "test_file"
        p.write_text("content")
        return str(p)

    def test_html_media_type_has_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "text/html", "index.html")
        assert resp.headers.get("content-security-policy") is not None

    def test_html_charset_has_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "text/html; charset=utf-8", "index.html")
        assert resp.headers.get("content-security-policy") is not None

    def test_xhtml_has_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "application/xhtml+xml", "page.xhtml")
        assert resp.headers.get("content-security-policy") is not None

    def test_css_no_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "text/css", "style.css")
        assert resp.headers.get("content-security-policy") is None

    def test_javascript_no_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "application/javascript", "app.js")
        assert resp.headers.get("content-security-policy") is None

    def test_pdf_no_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "application/pdf", "report.pdf")
        assert resp.headers.get("content-security-policy") is None

    def test_octet_stream_no_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "application/octet-stream", "data.bin")
        assert resp.headers.get("content-security-policy") is None

    def test_plain_text_no_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "text/plain", "readme.txt")
        assert resp.headers.get("content-security-policy") is None


class TestFileResponsePrivacyHeaders:
    """Privacy headers (noindex + no-store) apply to every served file type."""

    def _make_tmp_file(self, tmp_path: Path) -> str:
        p = tmp_path / "test_file"
        p.write_text("content")
        return str(p)

    @pytest.mark.parametrize(
        "media_type",
        [
            "text/html",
            "text/html; charset=utf-8",
            "application/xhtml+xml",
            "text/css",
            "application/javascript",
            "application/pdf",
            "text/plain",
            "application/octet-stream",
        ],
    )
    def test_privacy_headers_present_for_all_media_types(self, tmp_path: Path, media_type: str) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, media_type, "file")
        assert resp.headers.get("x-robots-tag") == "noindex, nofollow"
        assert resp.headers.get("cache-control") == "no-store"
        assert resp.headers.get("referrer-policy") == "no-referrer"


class TestShareSecurityHeadersCompleteness:
    """Verify _SHARE_SECURITY_HEADERS constant has exact expected directives."""

    def test_csp_has_all_nine_directives(self) -> None:
        csp = _SHARE_SECURITY_HEADERS["Content-Security-Policy"]
        expected = [
            "default-src 'none'",
            "script-src 'self' 'unsafe-inline'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self' data:",
            "media-src 'self' data: blob:",
            "connect-src 'none'",
            "frame-src 'none'",
            "object-src 'none'",
        ]
        for directive in expected:
            assert directive in csp, f"Missing CSP directive: {directive}"

    def test_x_content_type_options(self) -> None:
        assert _SHARE_SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self) -> None:
        assert _SHARE_SECURITY_HEADERS["X-Frame-Options"] == "DENY"

    def test_html_media_types_coverage(self) -> None:
        assert "text/html" in _HTML_MEDIA_TYPES
        assert "text/html; charset=utf-8" in _HTML_MEDIA_TYPES
        assert "application/xhtml+xml" in _HTML_MEDIA_TYPES
        assert len(_HTML_MEDIA_TYPES) == 3


@pytest.mark.asyncio
async def test_multi_file_redirect_has_no_csp(share_client, html_artifact) -> None:
    """307 redirect for multi-file bundles must not carry CSP headers."""
    files = {
        "index.html": PublishFile(path="index.html", content="<html/>", encoding="utf-8"),
        "app.js": PublishFile(path="app.js", content="console.log(1)", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    token = response.json()["token"]
    redirect = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert redirect.status_code == 307
    assert "content-security-policy" not in redirect.headers
    # Redirect is transient; the followed target carries privacy headers itself.
    assert "x-robots-tag" not in redirect.headers
    assert "cache-control" not in redirect.headers


@pytest.mark.asyncio
async def test_nested_css_asset_no_csp(share_client, html_artifact) -> None:
    """CSS sub-asset in nested path must not carry CSP headers."""
    files = {
        "index.html": PublishFile(
            path="index.html",
            content='<html><link href="assets/main.css"/></html>',
            encoding="utf-8",
        ),
        "assets/main.css": PublishFile(path="assets/main.css", content=".a{}", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    token = response.json()["token"]
    css = share_client.get(f"/public/artifact-share/{token}/assets/main.css")
    assert css.status_code == 200
    assert "content-security-policy" not in css.headers
    assert css.headers.get("x-content-type-options") is None
    assert css.headers.get("x-robots-tag") == "noindex, nofollow"
    assert css.headers.get("cache-control") == "no-store"
