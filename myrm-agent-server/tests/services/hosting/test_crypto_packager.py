import base64
import json
import secrets

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.services.hosting.crypto_packager import (
    _decrypt_payload,
    _encrypt_payload,
    package_encrypted_publish_files,
)
from app.services.hosting.packager import PublishFile


def test_crypto_packager_roundtrip() -> None:
    files = {
        "index.html": PublishFile(
            path="index.html",
            content="<h1>Secret Title</h1><script src='app.js'></script>",
            encoding="utf-8",
        ),
        "app.js": PublishFile(
            path="app.js",
            content="console.log('sensitive data');",
            encoding="utf-8",
        ),
        "data.json": PublishFile(
            path="data.json",
            content='{"revenue": 1000000}',
            encoding="utf-8",
        ),
    }
    password = "TestPassword2026!"

    encrypted_files = package_encrypted_publish_files(files, password, title="Secret Report")

    assert list(encrypted_files.keys()) == ["index.html"]
    entry = encrypted_files["index.html"]
    assert entry.encoding == "utf-8"
    assert "<!DOCTYPE html>" in entry.content
    assert "Secret Report" in entry.content
    assert "Web Crypto" not in entry.content or "crypto.subtle" in entry.content

    # Extract JSON encrypted data embedded in HTML
    start_marker = "const encryptedData = "
    assert start_marker in entry.content
    start_idx = entry.content.index(start_marker) + len(start_marker)
    end_idx = entry.content.index(";\n", start_idx)
    raw_json_str = entry.content[start_idx:end_idx]

    encrypted_dict = json.loads(raw_json_str)
    assert "salt" in encrypted_dict
    assert "nonce" in encrypted_dict
    assert "ciphertext" in encrypted_dict

    # Decrypt and verify payload
    decrypted_bytes = _decrypt_payload(encrypted_dict, password)
    vfs = json.loads(decrypted_bytes.decode("utf-8"))

    assert "index.html" in vfs
    assert "app.js" in vfs
    assert "data.json" in vfs
    assert vfs["index.html"]["content"] == files["index.html"].content
    assert vfs["app.js"]["content"] == files["app.js"].content
    assert vfs["data.json"]["content"] == files["data.json"].content


def test_crypto_packager_wrong_password() -> None:
    files = {
        "index.html": PublishFile(
            path="index.html",
            content="<h1>Secret</h1>",
            encoding="utf-8",
        )
    }
    encrypted_files = package_encrypted_publish_files(files, "CorrectPassword")
    start_marker = "const encryptedData = "
    start_idx = encrypted_files["index.html"].content.index(start_marker) + len(start_marker)
    end_idx = encrypted_files["index.html"].content.index(";\n", start_idx)
    encrypted_dict = json.loads(encrypted_files["index.html"].content[start_idx:end_idx])

    with pytest.raises((InvalidTag, ValueError)):
        _decrypt_payload(encrypted_dict, "WrongPassword")


def test_crypto_packager_empty_password() -> None:
    files = {
        "index.html": PublishFile(
            path="index.html",
            content="<h1>Public</h1>",
            encoding="utf-8",
        )
    }
    result = package_encrypted_publish_files(files, "")
    assert result == files


def test_crypto_packager_binary_asset_roundtrip() -> None:
    # Base64 encoded 1x1 transparent PNG
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    files = {
        "index.html": PublishFile(
            path="index.html",
            content="<h1>Graph</h1><img src='logo.png' />",
            encoding="utf-8",
        ),
        "logo.png": PublishFile(
            path="logo.png",
            content=png_b64,
            encoding="base64",
        ),
    }
    encrypted_files = package_encrypted_publish_files(files, "Pass1234", title="Asset Bundle")
    entry = encrypted_files["index.html"]

    start_marker = "const encryptedData = "
    start_idx = entry.content.index(start_marker) + len(start_marker)
    end_idx = entry.content.index(";\n", start_idx)
    encrypted_dict = json.loads(entry.content[start_idx:end_idx])

    decrypted_bytes = _decrypt_payload(encrypted_dict, "Pass1234")
    vfs = json.loads(decrypted_bytes.decode("utf-8"))

    assert "logo.png" in vfs
    assert vfs["logo.png"]["encoding"] == "base64"
    assert vfs["logo.png"]["content"] == png_b64


def test_crypto_packager_xss_prevention_in_title() -> None:
    files = {
        "index.html": PublishFile(
            path="index.html",
            content="<h1>Safe</h1>",
            encoding="utf-8",
        )
    }
    malicious_title = "<script>alert('xss')</script>\"&'<h1>"
    encrypted_files = package_encrypted_publish_files(files, "Pass1234", title=malicious_title)
    entry_content = encrypted_files["index.html"].content

    # Raw script tags in title must be escaped
    assert "<script>alert('xss')</script>" not in entry_content
    assert "<title>&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;&quot;&amp;&#x27;&lt;h1&gt;</title>" in entry_content
    assert "checkSecureContext" in entry_content
    assert "can only be unlocked over a secure connection" in entry_content


def test_crypto_packager_css_cascade_topological_resolution() -> None:
    """Verify that CSS cascade replacement logic and TextDecoder are properly embedded."""
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    files = {
        "index.html": PublishFile(
            path="index.html",
            content="<html><head><link rel='stylesheet' href='style.css'></head><body><div class='hero'>Test</div></body></html>",
            encoding="utf-8",
        ),
        "style.css": PublishFile(
            path="style.css",
            content=".hero { background: url('./bg.png'); } .icon { background: url('icons/arrow.svg'); }",
            encoding="utf-8",
        ),
        "bg.png": PublishFile(
            path="bg.png",
            content=png_b64,
            encoding="base64",
        ),
        "icons/arrow.svg": PublishFile(
            path="icons/arrow.svg",
            content="<svg></svg>",
            encoding="utf-8",
        ),
    }

    encrypted_files = package_encrypted_publish_files(files, "SecretCascadePass", title="Cascade Test")
    entry_html = encrypted_files["index.html"].content

    # Verify decryptor runtime script contains two-phase topological logic
    assert "leafBlobMap" in entry_html
    assert "cssBlobMap" in entry_html
    assert "TextDecoder" in entry_html
    assert "getMimeType" in entry_html

    # Decrypt and verify round-trip fidelity
    start_marker = "const encryptedData = "
    start_idx = entry_html.index(start_marker) + len(start_marker)
    end_idx = entry_html.index(";\n", start_idx)
    encrypted_dict = json.loads(entry_html[start_idx:end_idx])

    decrypted_bytes = _decrypt_payload(encrypted_dict, "SecretCascadePass")
    vfs = json.loads(decrypted_bytes.decode("utf-8"))

    assert "index.html" in vfs
    assert "style.css" in vfs
    assert "bg.png" in vfs
    assert "icons/arrow.svg" in vfs
    assert vfs["style.css"]["content"] == files["style.css"].content


def test_the_key_stretching_meets_the_owasp_floor_for_pbkdf2_sha256() -> None:
    """The ciphertext sits on public hosting, so the iteration count is all that slows an offline password guess."""
    assert int(_encrypt_payload(b"x", "Pass1234")["iterations"]) >= 600_000


def test_a_payload_is_opened_with_the_iteration_count_it_carries() -> None:
    """Pages published before the count was raised carry their own, and still open."""
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    key = PBKDF2HMAC(algorithm=SHA256(), length=32, salt=salt, iterations=100_000).derive(b"Pass1234")
    legacy = {
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(AESGCM(key).encrypt(nonce, b"legacy", None)).decode(),
        "iterations": "100000",
    }
    assert _decrypt_payload(legacy, "Pass1234") == b"legacy"
