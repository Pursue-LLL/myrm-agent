"""Unit tests for vault_proxy endpoint — extension validation and security.

Tests the allowed extension dictionary, path security, and media type mapping
without requiring a running server or real filesystem (uses tmp_path).
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.files.vault_proxy import _ALLOWED_EXTENSIONS


class TestAllowedExtensions:
    """Verify the extension → media type mapping."""

    def test_webm_supported(self):
        assert _ALLOWED_EXTENSIONS[".webm"] == "video/webm"

    def test_mp4_supported(self):
        assert _ALLOWED_EXTENSIONS[".mp4"] == "video/mp4"

    def test_png_supported(self):
        assert _ALLOWED_EXTENSIONS[".png"] == "image/png"

    def test_webp_supported(self):
        assert _ALLOWED_EXTENSIONS[".webp"] == "image/webp"

    def test_jpg_jpeg_supported(self):
        assert _ALLOWED_EXTENSIONS[".jpg"] == "image/jpeg"
        assert _ALLOWED_EXTENSIONS[".jpeg"] == "image/jpeg"

    def test_unsupported_extension_not_present(self):
        assert ".exe" not in _ALLOWED_EXTENSIONS
        assert ".sh" not in _ALLOWED_EXTENSIONS
        assert ".py" not in _ALLOWED_EXTENSIONS


class TestVaultProxyEndpoint:
    """Test the /vault/render endpoint behavior using test client."""

    @pytest.fixture
    def client(self):
        from tests.support.minimal_app import build_minimal_app

        app = build_minimal_app("vault_proxy")
        return TestClient(app)

    def test_valid_webm_file(self, client: TestClient, tmp_path):
        video = tmp_path / "session.webm"
        video.write_bytes(b"\x1a\x45\xdf\xa3")  # WebM magic bytes

        with patch("app.api.files.vault_proxy.is_local_mode", return_value=True):
            resp = client.get(
                "/api/v1/files/vault/render",
                params={"filepath": str(video), "workspace": str(tmp_path)},
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("video/webm")

    def test_valid_png_file(self, client: TestClient, tmp_path):
        img = tmp_path / "screenshot.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")

        with patch("app.api.files.vault_proxy.is_local_mode", return_value=True):
            resp = client.get(
                "/api/v1/files/vault/render",
                params={"filepath": str(img), "workspace": str(tmp_path)},
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/png")

    def test_rejected_extension(self, client: TestClient, tmp_path):
        script = tmp_path / "hack.sh"
        script.write_text("#!/bin/bash\nrm -rf /")

        with patch("app.api.files.vault_proxy.is_local_mode", return_value=True):
            resp = client.get(
                "/api/v1/files/vault/render",
                params={"filepath": str(script), "workspace": str(tmp_path)},
            )
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"]

    def test_file_not_found(self, client: TestClient, tmp_path):
        with patch("app.api.files.vault_proxy.is_local_mode", return_value=True):
            resp = client.get(
                "/api/v1/files/vault/render",
                params={"filepath": "nonexistent.webm", "workspace": str(tmp_path)},
            )
        assert resp.status_code == 404

    def test_path_traversal_rejected(self, client: TestClient, tmp_path):
        with patch("app.api.files.vault_proxy.is_local_mode", return_value=True):
            resp = client.get(
                "/api/v1/files/vault/render",
                params={"filepath": "../../../etc/passwd", "workspace": str(tmp_path)},
            )
        assert resp.status_code == 403

    def test_invalid_token_non_local(self, client: TestClient, tmp_path):
        video = tmp_path / "test.webm"
        video.write_bytes(b"\x1a\x45\xdf\xa3")

        with patch("app.api.files.vault_proxy.is_local_mode", return_value=False):
            resp = client.get(
                "/api/v1/files/vault/render",
                params={"filepath": str(video), "workspace": str(tmp_path), "token": "short"},
            )
        assert resp.status_code == 401
