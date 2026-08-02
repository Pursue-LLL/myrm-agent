"""Unit tests for server-side marketplace signature verification."""

from __future__ import annotations

import time

from app.services.theme.package.marketplace_signing import verify_marketplace_download_signature


def test_verify_marketplace_download_signature_dev_fallback(monkeypatch) -> None:
    monkeypatch.delenv("MARKETPLACE_CP_SIGNING_SECRET", raising=False)
    listing_id = "abc"
    digest = "d" * 64
    expires_at = time.time() + 120
    import hashlib

    signature = hashlib.sha256(f"{listing_id}:{digest}:{expires_at}".encode()).hexdigest()
    assert verify_marketplace_download_signature(
        listing_id=listing_id,
        package_sha256=digest,
        signature=signature,
        expires_at=expires_at,
    )
