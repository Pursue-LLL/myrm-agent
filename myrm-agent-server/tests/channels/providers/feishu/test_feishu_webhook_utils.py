"""Tests for Feishu webhook utilities."""

from __future__ import annotations

import hashlib

import pytest

from app.channels.providers.feishu.webhook_utils import (
    extract_channel_user_id,
    extract_chat_id,
    is_url_verification_challenge,
    parse_webhook_headers,
    verify_webhook_signature,
)


class TestVerifyWebhookSignature:
    """Tests for verify_webhook_signature function."""

    def test_verify_signature_success(self) -> None:
        """Test successful signature verification."""
        raw_body = b'{"event_type":"test"}'
        timestamp = "1234567890"
        nonce = "test_nonce"
        encrypt_key = "test_encrypt_key"

        # Generate expected signature
        prefix = (timestamp + nonce + encrypt_key).encode("utf-8")
        expected_signature = hashlib.sha256(prefix + raw_body).hexdigest()

        # Should not raise
        result = verify_webhook_signature(
            raw_body,
            timestamp=timestamp,
            nonce=nonce,
            signature=expected_signature,
            encrypt_key=encrypt_key,
        )
        assert result is True

    def test_verify_signature_invalid(self) -> None:
        """Test invalid signature raises ValueError."""
        raw_body = b'{"event_type":"test"}'
        timestamp = "1234567890"
        nonce = "test_nonce"
        encrypt_key = "test_encrypt_key"
        invalid_signature = "invalid_signature"

        with pytest.raises(ValueError, match="Invalid Feishu Webhook signature"):
            verify_webhook_signature(
                raw_body,
                timestamp=timestamp,
                nonce=nonce,
                signature=invalid_signature,
                encrypt_key=encrypt_key,
            )

    def test_verify_signature_no_encrypt_key(self) -> None:
        """Test verification skipped when encrypt_key is empty."""
        raw_body = b'{"event_type":"test"}'
        result = verify_webhook_signature(
            raw_body,
            timestamp="123",
            nonce="nonce",
            signature="any_signature",
            encrypt_key="",
        )
        assert result is True


class TestExtractChannelUserId:
    """Tests for extract_channel_user_id function."""

    def test_extract_user_id_success(self) -> None:
        """Test successful extraction of user ID."""
        payload = {
            "event": {
                "sender": {
                    "sender_id": {
                        "open_id": "ou_test123",
                    }
                }
            }
        }
        result = extract_channel_user_id(payload)
        assert result == "ou_test123"

    def test_extract_user_id_missing_event(self) -> None:
        """Test extraction when event is missing."""
        payload = {}
        result = extract_channel_user_id(payload)
        assert result is None

    def test_extract_user_id_missing_sender(self) -> None:
        """Test extraction when sender is missing."""
        payload = {"event": {}}
        result = extract_channel_user_id(payload)
        assert result is None

    def test_extract_user_id_missing_sender_id(self) -> None:
        """Test extraction when sender_id is missing."""
        payload = {"event": {"sender": {}}}
        result = extract_channel_user_id(payload)
        assert result is None

    def test_extract_user_id_missing_open_id(self) -> None:
        """Test extraction when open_id is missing."""
        payload = {"event": {"sender": {"sender_id": {}}}}
        result = extract_channel_user_id(payload)
        assert result is None


class TestExtractChatId:
    """Tests for extract_chat_id function."""

    def test_extract_chat_id_success(self) -> None:
        """Test successful extraction of chat ID."""
        payload = {
            "event": {
                "message": {
                    "chat_id": "oc_test123",
                }
            }
        }
        result = extract_chat_id(payload)
        assert result == "oc_test123"

    def test_extract_chat_id_missing_event(self) -> None:
        """Test extraction when event is missing."""
        payload = {}
        result = extract_chat_id(payload)
        assert result is None

    def test_extract_chat_id_missing_message(self) -> None:
        """Test extraction when message is missing."""
        payload = {"event": {}}
        result = extract_chat_id(payload)
        assert result is None

    def test_extract_chat_id_missing_chat_id(self) -> None:
        """Test extraction when chat_id is missing."""
        payload = {"event": {"message": {}}}
        result = extract_chat_id(payload)
        assert result is None


class TestIsUrlVerificationChallenge:
    """Tests for is_url_verification_challenge function."""

    def test_is_challenge_true(self) -> None:
        """Test detection of URL verification challenge."""
        payload = {"challenge": "test_challenge_token"}
        assert is_url_verification_challenge(payload) is True

    def test_is_challenge_false(self) -> None:
        """Test detection when not a challenge."""
        payload = {"event_type": "im.message.receive_v1"}
        assert is_url_verification_challenge(payload) is False

    def test_is_challenge_empty_payload(self) -> None:
        """Test detection with empty payload."""
        payload = {}
        assert is_url_verification_challenge(payload) is False


class TestParseWebhookHeaders:
    """Tests for parse_webhook_headers function."""

    def test_parse_headers_success(self) -> None:
        """Test successful header parsing."""
        headers = {
            "x-lark-request-timestamp": "1234567890",
            "x-lark-request-nonce": "test_nonce",
            "x-lark-signature": "test_signature",
        }
        timestamp, nonce, signature = parse_webhook_headers(headers)
        assert timestamp == "1234567890"
        assert nonce == "test_nonce"
        assert signature == "test_signature"

    def test_parse_headers_case_insensitive(self) -> None:
        """Test header parsing is case-insensitive."""
        headers = {
            "X-Lark-Request-Timestamp": "1234567890",
            "X-Lark-Request-Nonce": "test_nonce",
            "X-Lark-Signature": "test_signature",
        }
        timestamp, nonce, signature = parse_webhook_headers(headers)
        assert timestamp == "1234567890"
        assert nonce == "test_nonce"
        assert signature == "test_signature"

    def test_parse_headers_missing_signature(self) -> None:
        """Test parsing raises error when signature is missing."""
        headers = {
            "x-lark-request-timestamp": "1234567890",
            "x-lark-request-nonce": "test_nonce",
        }
        with pytest.raises(ValueError, match="Missing X-Lark-Signature header"):
            parse_webhook_headers(headers)

    def test_parse_headers_missing_timestamp_nonce(self) -> None:
        """Test parsing returns empty strings for missing timestamp/nonce."""
        headers = {"x-lark-signature": "test_signature"}
        timestamp, nonce, signature = parse_webhook_headers(headers)
        assert timestamp == ""
        assert nonce == ""
        assert signature == "test_signature"
