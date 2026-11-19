"""Readiness waits of the stack under test.

[INPUT]
- cdp_chat.support.api_client::_e2e_api_get_json, _validate_loopback_http_url, get_e2e_api_url (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)
- cdp_chat.support.timeouts::e2e_parallel_config_api_timeout_sec (POS: Turns a base timeout into the budget a parallel run needs, from the active wave leases, parallel tests and mux peers)

[OUTPUT]
- wait_e2e_provider_ready, fetch_provider_readiness_snapshot, _api_provider_ready: provider readiness of the private pool
- wait_e2e_backend_ready: backend health
- wait_e2e_cdp_ready: Chrome CDP endpoint
- warmup_frontend: first Next.js dev compile before navigation

[POS]
Polls until the pieces under test accept work: provider, backend, Chrome CDP and the frontend dev server.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request

from cdp_chat.support.api_client import (
    _e2e_api_get_json,
    _validate_loopback_http_url,
    get_e2e_api_url,
)
from cdp_chat.support.timeouts import e2e_parallel_config_api_timeout_sec


def _api_provider_ready(
    *,
    api_url: str | None = None,
    timeout_sec: float = 5.0,
) -> bool:
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    try:
        payload = _e2e_api_get_json(
            f"{resolved_api}/api/v1/config/readiness",
            timeout_sec=timeout_sec,
        )
    except (OSError, TimeoutError, urllib.error.URLError, ValueError):
        return False
    provider = payload.get("provider") if isinstance(payload, dict) else None
    return isinstance(provider, dict) and bool(provider.get("is_ready"))


def fetch_provider_readiness_snapshot() -> dict[str, object]:
    """Return private-pool provider readiness for E2E failure diagnostics."""
    api_base = get_e2e_api_url()
    try:
        payload = _e2e_api_get_json(
            f"{api_base}/api/v1/config/readiness",
            timeout_sec=5.0,
        )
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as exc:
        return {"apiBase": api_base, "error": str(exc)}
    if not isinstance(payload, dict):
        return {"apiBase": api_base, "error": "invalid_readiness_payload"}
    provider = payload.get("provider")
    return {
        "apiBase": api_base,
        "provider": provider if isinstance(provider, dict) else None,
        "degraded": payload.get("degraded"),
    }


def wait_e2e_provider_ready(
    *,
    api_url: str | None = None,
    timeout_sec: float = 60.0,
    poll_interval_sec: float = 1.0,
) -> bool:
    """Poll private-pool provider readiness (SHPOIB bootstrap race).

    ``timeout_sec`` is the full poll budget. ``e2e_parallel_config_api_timeout_sec``
    scales per-request HTTP only — applying it to the poll deadline silently capped
    desktop soak gate waits (260s budget → 120s under parallel load).
    Provider ``is_ready`` is sufficient; health is an optional fast-path hint.
    """
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    request_timeout_sec = e2e_parallel_config_api_timeout_sec(5.0)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if _api_provider_ready(
            api_url=resolved_api,
            timeout_sec=request_timeout_sec,
        ):
            return True
        try:
            health_payload = _e2e_api_get_json(
                f"{resolved_api}/api/v1/health",
                timeout_sec=request_timeout_sec,
            )
            if (
                isinstance(health_payload, dict)
                and health_payload.get("status") == "healthy"
                and _api_provider_ready(
                    api_url=resolved_api,
                    timeout_sec=request_timeout_sec,
                )
            ):
                return True
        except (OSError, TimeoutError, urllib.error.URLError, ValueError):
            pass
        time.sleep(poll_interval_sec)
    return _api_provider_ready(
        api_url=resolved_api,
        timeout_sec=request_timeout_sec,
    )


def wait_e2e_backend_ready(
    *,
    timeout_sec: float = 60.0,
    poll_interval_sec: float = 1.0,
    api_url: str | None = None,
) -> bool:
    """Poll private-backend /health until stack is accepting requests."""
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            payload = _e2e_api_get_json(
                f"{resolved_api}/api/v1/health",
                timeout_sec=5.0,
            )
            if isinstance(payload, dict) and payload.get("status") == "healthy":
                return True
        except (OSError, TimeoutError, urllib.error.URLError, ValueError):
            pass
        time.sleep(poll_interval_sec)
    return False


def wait_e2e_cdp_ready(
    *,
    timeout_sec: float = 30.0,
    poll_interval_sec: float = 1.0,
    port: int | None = None,
) -> bool:
    """Poll Myrm E2E Chrome CDP (:9333) until attach endpoint responds."""
    resolved_port = port
    if resolved_port is None:
        raw = os.getenv("MYRM_CHROME_E2E_PORT", "9333").strip()
        try:
            resolved_port = int(raw)
        except ValueError:
            resolved_port = 9333
    endpoint = f"http://127.0.0.1:{resolved_port}/json/version"
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(endpoint, timeout=3)
            if resp.status == 200:
                return True
        except (OSError, TimeoutError, urllib.error.URLError):
            pass
        time.sleep(poll_interval_sec)
    return False


def warmup_frontend(base_url: str, *, timeout_sec: float = 120.0) -> None:
    """Warm Next.js dev compile before CDP navigation (avoids hung first paint)."""
    deadline = time.monotonic() + timeout_sec
    last_error = "unknown"
    while time.monotonic() < deadline:
        try:
            warm_url = base_url.rstrip("/") + "/"
            _validate_loopback_http_url(warm_url)
            with urllib.request.urlopen(warm_url, timeout=45) as resp:
                if resp.status == 200:
                    return
                last_error = f"HTTP {resp.status}"
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(3)
    raise TimeoutError(
        f"Frontend warmup failed within {timeout_sec:.0f}s: {last_error}"
    )
