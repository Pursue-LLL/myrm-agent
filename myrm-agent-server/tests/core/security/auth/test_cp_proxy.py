"""Unit tests for CP proxy signature verification on agent-server."""

from __future__ import annotations

import time

import pytest

from app.core.security.auth.cp_proxy import (
    build_signed_proxy_headers,
    verify_cp_proxy_request,
)

_FIXED_TS = 1_700_000_000


def test_verify_cp_proxy_request_accepts_valid_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import SecretStr

    from app.config.settings import settings

    monkeypatch.setattr(settings, "internal_service_key", SecretStr("svc-key"))
    monkeypatch.setattr(time, "time", lambda: float(_FIXED_TS))

    headers = build_signed_proxy_headers(
        user_id="alice",
        method="GET",
        path="/api/v1/health",
        internal_service_key="svc-key",
        timestamp=_FIXED_TS,
    )
    assert verify_cp_proxy_request(headers, method="GET", path="/api/v1/health") == "alice"


def test_verify_cp_proxy_request_rejects_tampered_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import SecretStr

    from app.config.settings import settings

    monkeypatch.setattr(settings, "internal_service_key", SecretStr("svc-key"))
    monkeypatch.setattr(time, "time", lambda: float(_FIXED_TS))

    headers = build_signed_proxy_headers(
        user_id="alice",
        method="GET",
        path="/api/v1/health",
        internal_service_key="svc-key",
        timestamp=_FIXED_TS,
    )
    headers["X-User-Id"] = "eve"
    assert verify_cp_proxy_request(headers, method="GET", path="/api/v1/health") is None


def test_cp_proxy_signature_contract_vectors() -> None:
    """Verify server signatures match CP contract fixture (cross-repo)."""
    import json
    from pathlib import Path

    from app.core.security.auth.cp_proxy import compute_proxy_signature

    contract_path = (
        Path(__file__).resolve().parents[5]
        / "myrm-control-plane/tests/fixtures/cp_proxy_signature_contract.json"
    )
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    for vector in payload["vectors"]:
        signature = compute_proxy_signature(
            vector["internal_service_key"],
            timestamp=vector["timestamp"],
            user_id=vector["user_id"],
            method=vector["method"],
            path=vector["path"],
        )
        assert signature == vector["expected_signature"]
