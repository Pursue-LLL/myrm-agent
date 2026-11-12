"""Effect-guarded HTTP access to the E2E backend and the identity of the backend process."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request

from cdp_chat.support import _e2e_api_urlopen, get_e2e_api_url, get_e2e_ui_url
from e2e_core.dev_ports import current_api_base, shared_api_base


def prepare_e2e_ui_session(api_url: str) -> None:
    """Mark onboarding complete so PageLayout does not overlay the chat during E2E.

    READ-scoped tests must not mutate global config; they rely on dismiss_blocking_modals
    localStorage boot flags instead (P0-C effect guard).
    """
    from e2e_core.effect_guard import current_access_scope

    if current_access_scope() == "READ":
        return
    last_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            http_json(
                "POST",
                f"{api_url}/api/v1/config/onboarding/complete",
                expected_statuses=frozenset({200, 201}),
            )
            return
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            if attempt >= 3:
                break
            time.sleep(min(2.0 * attempt, 6.0))
    if last_error is not None:
        raise last_error


def guarded_httpx_request(client: object, method: str, url: str, **kwargs: object) -> object:
    """Effect-guarded httpx request for formal chrome_e2e live agent paths."""
    from e2e_core.effect_guard import guarded_httpx_request as _guard

    return _guard(client, method, url, **kwargs)


def guarded_urlopen(
    request: urllib.request.Request,
    *,
    timeout_sec: float,
    max_attempts: int = 3,
    opener: urllib.request.OpenerDirector | None = None,
) -> object:
    """Effect-guarded loopback request for direct Chrome E2E HTTP helpers.

    ``http_json`` covers JSON calls, while binary and form responses need the
    raw response object. Keeping the guard at this boundary prevents those
    callers from silently bypassing the same access-scope contract.
    """
    from e2e_core.effect_guard import assert_http_effect_allowed

    assert_http_effect_allowed(method=request.get_method(), url=request.full_url)
    if opener is not None:
        return opener.open(request, timeout=timeout_sec)
    return _e2e_api_urlopen(
        request,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    )


def get_first_enabled_model(api_url: str | None = None) -> str:
    """Return the first model from the backend's enabled providers.

    Mirrors the Kanban UI model select (single data source: /config/providers),
    so tests never hard-code a model that the target backend may not have.
    """
    base = (api_url or get_e2e_api_url()).rstrip("/")
    payload = http_json("GET", f"{base}/api/v1/config/providers")
    value = payload.get("value") if isinstance(payload, dict) else payload
    if not isinstance(value, dict):
        raise RuntimeError(f"E2E: providers config malformed on {base}")
    providers = value.get("providers")
    if not isinstance(providers, list):
        raise RuntimeError(f"E2E: providers list missing on {base}")
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        if not (provider.get("isEnabled") or provider.get("enabled")):
            continue
        keys = provider.get("apiKeys")
        has_key = isinstance(keys, list) and any(isinstance(k, dict) and k.get("isActive") for k in keys)
        if not has_key:
            continue
        provider_id = str(provider.get("id", ""))
        models = provider.get("enabledModels")
        if isinstance(models, list):
            for model in models:
                if isinstance(model, str) and model:
                    return f"{provider_id}/{model}"
    raise RuntimeError(f"E2E: no enabled provider model found on {base}")


def backend_boot_identity(api_url: str) -> str:
    """Best-effort ``pid:started_at`` for whichever process serves the API port.

    A LIVE turn can be interrupted by a dev-stack hot reload (another agent edits backend
    code): the stream dies before any assistant message, and the test then reads like a
    product defect. Comparing this value before and after the wait separates the two.
    Returns "" when the platform cannot answer, so an unknown identity never invents a
    restart.
    """
    from urllib.parse import urlsplit

    port = urlsplit(api_url).port
    if port is None:
        return ""
    try:
        listing = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        pid = next(
            (line.strip() for line in (listing.stdout or "").splitlines() if line.strip().isdigit()),
            "",
        )
        if not pid:
            return ""
        started = subprocess.run(
            ["ps", "-p", pid, "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        started_at = (started.stdout or "").strip()
        return f"{pid}:{started_at}" if started_at else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def http_json(
    method: str,
    url: str,
    body: dict[str, object] | None = None,
    *,
    expected_statuses: frozenset[int] = frozenset({200, 201, 204}),
    timeout_sec: float = 30.0,
) -> object:
    from e2e_core.effect_guard import assert_http_effect_allowed

    assert_http_effect_allowed(method=method, url=url)
    allowed_bases = [get_e2e_ui_url(), get_e2e_api_url()]
    shared_hot = current_api_base()
    # The canonical shared backend stays reachable on its port across backend
    # rotations (seeded/isolated runtimes come and go); keep it allowlisted
    # alongside the volatile env-derived base. Loopback-only, no trust change.
    for base in (shared_hot, shared_api_base()):
        if base.rstrip("/") not in {known.rstrip("/") for known in allowed_bases}:
            allowed_bases.append(base)
    allowed = tuple(allowed_bases)
    if not url.startswith(allowed):
        raise ValueError(f"Chrome E2E HTTP helper only permits loopback app URLs: {url}")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(  # noqa: S310 - validated loopback
        url, data=data, method=method
    )
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        response = _e2e_api_urlopen(
            request,
            timeout_sec=timeout_sec,
            max_attempts=3,
        )  # noqa: S310 - loopback only
        with response as http_response:
            raw = http_response.read()
            status = http_response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    if status not in expected_statuses:
        raise RuntimeError(f"HTTP {method} {url} returned {status}: {raw[:500]!r}")
    return json.loads(raw) if raw else {}
