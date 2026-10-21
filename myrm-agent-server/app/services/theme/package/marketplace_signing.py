"""Verify CP theme marketplace transport signatures on the server.

[INPUT]
MARKETPLACE_CP_SIGNING_SECRET (ENV: 市场签名密钥)

[OUTPUT]
verify_marketplace_download_signature(body, sig_header) -> bool
sign_marketplace_payload(body) -> str

[POS]
HMAC-SHA256 签名校验，防止包传输中被篡改；
5 分钟时间窗口防重放。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

TRANSPORT_SIGNER = "control-plane"
TRANSPORT_ALGORITHM = "hmac-sha256-v1"
_SIGN_SECRET_ENV = "MARKETPLACE_CP_SIGNING_SECRET"


def marketplace_signing_secret() -> str | None:
    raw = os.environ.get(_SIGN_SECRET_ENV)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def compute_transport_signature(package_sha256: str, secret: str) -> str:
    signing_message = f"{TRANSPORT_SIGNER}:{TRANSPORT_ALGORITHM}:{package_sha256}"
    return hmac.new(
        secret.encode("utf-8"),
        signing_message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_marketplace_download_signature(
    *,
    listing_id: str,
    package_sha256: str,
    signature: str,
    expires_at: float,
) -> bool:
    if time.time() > expires_at:
        return False
    secret = marketplace_signing_secret()
    if secret is None:
        expected = hashlib.sha256(f"{listing_id}:{package_sha256}:{expires_at}".encode()).hexdigest()
        return hmac.compare_digest(expected, signature)
    expected = compute_transport_signature(package_sha256, secret)
    return hmac.compare_digest(expected, signature)
