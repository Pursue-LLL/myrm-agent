"""Tests for VAPID key generation and persistence."""

from __future__ import annotations

import base64
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.core.web_push.vapid_keys import load_vapid_keys


class TestVapidKeys:
    """Verify VAPID key generation, persistence, and reload."""

    def test_generates_new_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.core.web_push.vapid_keys._get_vapid_dir", return_value=Path(tmpdir)):
                private_pem, public_key = load_vapid_keys()

        assert private_pem.startswith("-----BEGIN PRIVATE KEY-----")
        assert len(public_key) > 0
        assert "+" not in public_key
        assert "=" not in public_key

    def test_reloads_existing_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.core.web_push.vapid_keys._get_vapid_dir", return_value=Path(tmpdir)):
                pem1, pub1 = load_vapid_keys()
                pem2, pub2 = load_vapid_keys()

        assert pem1 == pem2
        assert pub1 == pub2

    def test_public_key_is_valid_uncompressed_point(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.core.web_push.vapid_keys._get_vapid_dir", return_value=Path(tmpdir)):
                _, public_key = load_vapid_keys()

        padding = "=" * ((4 - len(public_key) % 4) % 4)
        raw = base64.urlsafe_b64decode(public_key + padding)
        assert len(raw) == 65
        assert raw[0] == 0x04

    def test_private_key_file_permissions(self) -> None:
        if sys.platform == "win32":
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.core.web_push.vapid_keys._get_vapid_dir", return_value=Path(tmpdir)):
                load_vapid_keys()
            priv_path = Path(tmpdir) / "vapid_private_key.pem"
            pub_path = Path(tmpdir) / "vapid_public_key.txt"
            priv_mode = stat.S_IMODE(os.stat(priv_path).st_mode)
            pub_mode = stat.S_IMODE(os.stat(pub_path).st_mode)
            assert priv_mode == 0o600, f"Expected 0600, got {oct(priv_mode)}"
            assert pub_mode == 0o644, f"Expected 0644, got {oct(pub_mode)}"

    def test_private_key_has_no_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.core.web_push.vapid_keys._get_vapid_dir", return_value=Path(tmpdir)):
                pem, _ = load_vapid_keys()
        assert not pem.endswith("\n")
        assert pem == pem.strip()
