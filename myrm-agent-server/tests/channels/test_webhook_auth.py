"""Unit tests for webhook authentication logic."""

from __future__ import annotations

import hashlib
import hmac as hmac_mod

from app.channels.providers.telegram import TelegramChannel


class TestTelegramWebhookSecret:
    """Tests for TelegramChannel.webhook_secret property."""

    def test_deterministic(self) -> None:
        """Same bot_token always produces the same secret."""
        ch = TelegramChannel("123456:ABC-DEF")
        assert ch.webhook_secret == ch.webhook_secret

    def test_different_tokens_different_secrets(self) -> None:
        ch1 = TelegramChannel("token_a")
        ch2 = TelegramChannel("token_b")
        assert ch1.webhook_secret != ch2.webhook_secret

    def test_length(self) -> None:
        ch = TelegramChannel("123456:ABC-DEF")
        assert len(ch.webhook_secret) == 32

    def test_matches_sha256_derivation(self) -> None:
        token = "123456:ABC-DEF"
        ch = TelegramChannel(token)
        expected = hashlib.sha256(token.encode()).hexdigest()[:32]
        assert ch.webhook_secret == expected


class TestVerifyHmacSignature:
    """Tests for HMAC-SHA256 signature verification logic.

    Verifies the algorithm used in webhook.py without importing the app layer.
    """

    @staticmethod
    def _verify(body: bytes, secret: str, signature: str) -> bool:
        if not secret or not signature:
            return False
        expected = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac_mod.compare_digest(f"sha256={expected}", signature)

    def test_valid_signature(self) -> None:
        body = b'{"event": "test"}'
        secret = "my-secret"
        digest = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()
        signature = f"sha256={digest}"
        assert self._verify(body, secret, signature) is True

    def test_invalid_signature(self) -> None:
        body = b'{"event": "test"}'
        assert self._verify(body, "my-secret", "sha256=invalid") is False

    def test_empty_secret(self) -> None:
        assert self._verify(b"body", "", "sha256=abc") is False

    def test_empty_signature(self) -> None:
        assert self._verify(b"body", "secret", "") is False

    def test_tampered_body(self) -> None:
        secret = "my-secret"
        original_body = b'{"event": "test"}'
        digest = hmac_mod.new(secret.encode(), original_body, hashlib.sha256).hexdigest()
        signature = f"sha256={digest}"
        tampered_body = b'{"event": "hacked"}'
        assert self._verify(tampered_body, secret, signature) is False
