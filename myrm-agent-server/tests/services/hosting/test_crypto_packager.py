import json

import pytest
from cryptography.exceptions import InvalidTag

from app.services.hosting.crypto_packager import (
    _decrypt_payload,
    package_encrypted_publish_files,
)
from app.services.hosting.packager import PublishFile


def test_crypto_packager_roundtrip():
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


def test_crypto_packager_wrong_password():
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

    with pytest.raises(Exception):
        _decrypt_payload(encrypted_dict, "WrongPassword")


def test_crypto_packager_empty_password():
    files = {
        "index.html": PublishFile(
            path="index.html",
            content="<h1>Public</h1>",
            encoding="utf-8",
        )
    }
    result = package_encrypted_publish_files(files, "")
    assert result == files
