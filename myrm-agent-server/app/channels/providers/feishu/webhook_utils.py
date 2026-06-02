"""Feishu Webhook utilities — signature verification and parsing helpers.

Provides lightweight utilities for Feishu Webhook processing without requiring
a full FeishuChannel instance. Used by both the channel system and external
integrations (e.g. control planes).

[INPUT]

[OUTPUT]
- verify_webhook_signature() → bool: Verify Webhook signature
- extract_channel_user_id() → str | None: Extract sender's open_id from payload
- extract_chat_id() → str | None: Extract chat_id from payload

[POS]
Feishu Webhook utility functions for signature verification and metadata extraction.
No full FeishuChannel instantiation needed. Suitable for control planes and lightweight scenarios.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


def verify_webhook_signature(
    raw_body: bytes | str,
    *,
    timestamp: str,
    nonce: str,
    signature: str,
    encrypt_key: str,
) -> bool:
    """Verify Feishu Webhook signature.

    Feishu signature: sha256(timestamp + nonce + encrypt_key + body)

    Args:
        raw_body: Raw Webhook request body (bytes or str)
        timestamp: X-Lark-Request-Timestamp header value
        nonce: X-Lark-Request-Nonce header value
        signature: X-Lark-Signature header value
        encrypt_key: Feishu app encrypt key

    Returns:
        True if signature is valid or encrypt_key is empty (no verification)

    Raises:
        ValueError: If signature is invalid
    """
    if not encrypt_key:
        return True

    # Ensure raw_body is bytes
    body_bytes = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body

    prefix = (timestamp + nonce + encrypt_key).encode("utf-8")
    expected = hashlib.sha256(prefix + body_bytes).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid Feishu Webhook signature")

    return True


def extract_channel_user_id(payload: dict[str, object]) -> str | None:
    """Extract sender's open_id from Feishu Webhook payload.

    Args:
        payload: Parsed Feishu Webhook JSON payload

    Returns:
        Sender's open_id, or None if not found
    """
    event = payload.get("event")
    if not isinstance(event, dict):
        return None

    sender = event.get("sender")
    if not isinstance(sender, dict):
        return None

    sender_id = sender.get("sender_id")
    if not isinstance(sender_id, dict):
        return None

    open_id = sender_id.get("open_id")
    return str(open_id) if open_id else None


def extract_chat_id(payload: dict[str, object]) -> str | None:
    """Extract chat_id from Feishu Webhook payload.

    Args:
        payload: Parsed Feishu Webhook JSON payload

    Returns:
        Chat ID, or None if not found
    """
    event = payload.get("event")
    if not isinstance(event, dict):
        return None

    message = event.get("message")
    if not isinstance(message, dict):
        return None

    chat_id = message.get("chat_id")
    return str(chat_id) if chat_id else None


def is_url_verification_challenge(payload: dict[str, object]) -> bool:
    """Check if the payload is a URL verification challenge.

    Args:
        payload: Parsed Feishu Webhook JSON payload

    Returns:
        True if this is a URL verification challenge
    """
    return "challenge" in payload


def parse_webhook_headers(headers: dict[str, str]) -> tuple[str, str, str]:
    """Parse Feishu Webhook headers for signature verification.

    Args:
        headers: HTTP headers (lowercase keys recommended)

    Returns:
        Tuple of (timestamp, nonce, signature)

    Raises:
        ValueError: If required headers are missing
    """
    # Normalize header keys to lowercase
    headers_lower = {k.lower(): v for k, v in headers.items()}

    timestamp = headers_lower.get("x-lark-request-timestamp", "")
    nonce = headers_lower.get("x-lark-request-nonce", "")
    signature = headers_lower.get("x-lark-signature", "")

    if not signature:
        raise ValueError("Missing X-Lark-Signature header")

    return timestamp, nonce, signature
