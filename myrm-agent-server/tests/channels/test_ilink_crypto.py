"""Tests for ilink_crypto module (AES-128-ECB encryption/decryption)."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.providers._ilink.crypto import (
    _pkcs7_pad,
    _pkcs7_unpad,
    decrypt_media,
    download_and_decrypt,
    encrypt_and_upload,
    encrypt_media,
    generate_aes_key,
)


class TestGenerateAesKey:
    def test_generates_valid_base64(self) -> None:
        key = generate_aes_key()
        raw = base64.b64decode(key)
        assert len(raw) == 16

    def test_generates_unique_keys(self) -> None:
        keys = {generate_aes_key() for _ in range(100)}
        assert len(keys) == 100


class TestPkcs7:
    def test_pad_full_block(self) -> None:
        data = b"0123456789abcdef"
        padded = _pkcs7_pad(data, 16)
        assert len(padded) == 32
        assert padded[-16:] == bytes([16] * 16)

    def test_pad_partial_block(self) -> None:
        data = b"hello"
        padded = _pkcs7_pad(data, 16)
        assert len(padded) == 16
        assert padded[-11:] == bytes([11] * 11)

    def test_unpad_valid(self) -> None:
        data = b"hello" + bytes([11] * 11)
        assert _pkcs7_unpad(data) == b"hello"

    def test_unpad_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            _pkcs7_unpad(b"")

    def test_unpad_invalid_padding_raises(self) -> None:
        with pytest.raises(ValueError, match="padding"):
            _pkcs7_unpad(b"\x00")

    def test_roundtrip(self) -> None:
        data = b"test data for roundtrip"
        assert _pkcs7_unpad(_pkcs7_pad(data, 16)) == data


class TestEncryptDecrypt:
    def test_roundtrip(self) -> None:
        key = generate_aes_key()
        plaintext = b"Hello, WeChat media encryption!"
        ciphertext = encrypt_media(plaintext, key)
        assert ciphertext != plaintext
        decrypted = decrypt_media(ciphertext, key)
        assert decrypted == plaintext

    def test_invalid_key_length(self) -> None:
        bad_key = base64.b64encode(b"short").decode()
        with pytest.raises(ValueError, match="16 bytes"):
            encrypt_media(b"data", bad_key)

    def test_decrypt_invalid_key_length(self) -> None:
        bad_key = base64.b64encode(b"short").decode()
        with pytest.raises(ValueError, match="16 bytes"):
            decrypt_media(b"data" * 4, bad_key)

    def test_large_data(self) -> None:
        key = generate_aes_key()
        plaintext = b"x" * 10000
        ciphertext = encrypt_media(plaintext, key)
        assert decrypt_media(ciphertext, key) == plaintext


class TestDownloadAndDecrypt:
    @pytest.mark.asyncio
    async def test_with_provided_client(self, tmp_path: Path) -> None:
        key = generate_aes_key()
        plaintext = b"test media content"
        ciphertext = encrypt_media(plaintext, key)

        mock_resp = AsyncMock()
        mock_resp.content = ciphertext
        mock_resp.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        output = tmp_path / "decrypted.jpg"
        await download_and_decrypt("https://cdn.example.com/media", key, output, http_client=mock_client)

        assert output.exists()
        assert output.read_bytes() == plaintext

    @pytest.mark.asyncio
    async def test_without_client(self, tmp_path: Path) -> None:
        key = generate_aes_key()
        plaintext = b"test content"
        ciphertext = encrypt_media(plaintext, key)

        mock_resp = AsyncMock()
        mock_resp.content = ciphertext
        mock_resp.raise_for_status = lambda: None

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)

        output = tmp_path / "decrypted.jpg"
        with patch(
            "app.channels.providers._ilink.crypto.httpx.AsyncClient",
            return_value=mock_client_instance,
        ):
            await download_and_decrypt("https://cdn.example.com/media", key, output)

        assert output.exists()
        assert output.read_bytes() == plaintext


class TestEncryptAndUpload:
    @pytest.mark.asyncio
    async def test_with_provided_client(self, tmp_path: Path) -> None:
        key = generate_aes_key()
        file_path = tmp_path / "test.jpg"
        file_path.write_bytes(b"image content")

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        size = await encrypt_and_upload(file_path, "https://upload.example.com", key, http_client=mock_client)
        assert size > 0
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_file_too_large(self, tmp_path: Path) -> None:
        key = generate_aes_key()
        file_path = tmp_path / "huge.bin"
        file_path.write_bytes(b"x" * (101 * 1024 * 1024))

        with pytest.raises(ValueError, match="exceeds maximum"):
            await encrypt_and_upload(file_path, "https://upload.example.com", key)

    @pytest.mark.asyncio
    async def test_without_client(self, tmp_path: Path) -> None:
        key = generate_aes_key()
        file_path = tmp_path / "test.jpg"
        file_path.write_bytes(b"image content")

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.channels.providers._ilink.crypto.httpx.AsyncClient",
            return_value=mock_client_instance,
        ):
            size = await encrypt_and_upload(file_path, "https://upload.example.com", key)

        assert size > 0
