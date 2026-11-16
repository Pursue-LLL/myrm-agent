"""E2E API and UI origins, and loopback-only HTTP calls to the API.

[INPUT]
- cdp_chat.support.paths::MONOREPO_ROOT (POS: Single source of the checkout root the E2E helpers resolve dev scripts and stack state against)
- e2e_core.dev_ports::current_backend_port, shared_api_base, shared_ui_base (POS: default ports of the user, shared dev and isolated stacks)
- e2e_core.epoch_delivery_plane::epoch_pin_active (POS: Dev Gate epoch routing of LIVE and STANDARD namespace-write tests)
- e2e_core.stack_mutation_policy::attach_backend_crash_heal_inner (POS: shared-stack mutation decisions; defers drift heal while wave leases are active)

[OUTPUT]
- get_e2e_api_url, get_e2e_ui_url, resolve_e2e_api_base: the loopback origins a run talks to
- get_open_page_api_url: the API base the orchestrator opens pages with
- shared_hot_e2e_api_base: the shared dev-stack API, never the per-run override
- _e2e_api_urlopen, _e2e_api_get_json, _e2e_api_post_json: loopback-only HTTP with retry; package-internal, shared by the other modules
- _set_http_response_read_timeout: per-read socket timeout for SSE loops

[POS]
Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load. A refused connection to the shared dev backend triggers one crash heal before the retry.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http.client import HTTPResponse
from urllib.parse import urlsplit

from e2e_core.dev_ports import current_backend_port, shared_api_base, shared_ui_base

from cdp_chat.support.paths import MONOREPO_ROOT

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})

_E2E_API_REQUEST_ATTEMPTS = 3
_E2E_API_REQUEST_BACKOFF_SEC = 2.0


def _is_shared_dev_api_url(url: str) -> bool:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").strip().lower()
    if hostname not in _LOOPBACK_HOSTS:
        return False
    return (parsed.port or 80) == current_backend_port()


def _normalize_loopback_http_origin(origin: str, *, env_name: str) -> str:
    trimmed = origin.strip().rstrip("/")
    if not trimmed:
        raise RuntimeError(f"{env_name} is empty")
    parsed = urlsplit(trimmed)
    hostname = (parsed.hostname or "").strip().lower()
    if (
        parsed.scheme not in {"http", "https"}
        or hostname not in _LOOPBACK_HOSTS
        or bool(parsed.username)
        or bool(parsed.password)
        or bool(parsed.query)
        or bool(parsed.fragment)
        or parsed.path not in {"", "/"}
    ):
        raise RuntimeError(
            f"{env_name} must be an explicit loopback HTTP origin (127.0.0.1 / localhost / ::1 / 0.0.0.0): {trimmed}"
        )
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _validate_loopback_http_url(url: str) -> None:
    parsed = urlsplit(url.strip())
    hostname = (parsed.hostname or "").strip().lower()
    if parsed.scheme not in {"http", "https"} or hostname not in _LOOPBACK_HOSTS:
        raise RuntimeError(f"E2E HTTP helper only permits loopback URLs: {url}")


def get_e2e_api_url() -> str:
    return _normalize_loopback_http_origin(
        os.getenv("E2E_API_BASE", shared_api_base()),
        env_name="E2E_API_BASE",
    )


def get_e2e_ui_url() -> str:
    return _normalize_loopback_http_origin(
        os.getenv("E2E_UI_BASE", shared_ui_base()),
        env_name="E2E_UI_BASE",
    )


def resolve_e2e_api_base(api_base: str | None = None) -> str:
    raw = (api_base or os.getenv("E2E_API_BASE", "")).strip()
    if not raw:
        return ""
    return _normalize_loopback_http_origin(raw, env_name="E2E_API_BASE")


def get_open_page_api_url() -> str:
    """Orchestrator page-open API base — epoch pin uses E2E_API_BASE; else SHARED hot API.

    The shared API is a sentinel for SHARED+RESOURCE_WRITE: skip CDP API inject and rely on
    Next.js rewrites (including isolated stacks on custom UI/API ports).
    """
    try:
        from e2e_core.epoch_delivery_plane import epoch_pin_active

        if epoch_pin_active():
            return get_e2e_api_url()
    except ImportError:
        pass
    mode = os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip().upper()
    lane = os.environ.get("MYRM_E2E_LANE", "").strip().upper()
    if mode == "SHARED" and lane == "RESOURCE_WRITE":
        return shared_api_base()
    return get_e2e_api_url()


def shared_hot_e2e_api_base() -> str:
    """Shared dev-stack API. Never the SHPOIB-monkeypatched ``E2E_API_BASE``."""
    explicit = os.getenv("MYRM_SHARED_E2E_API_BASE", "").strip()
    if explicit:
        return explicit.rstrip("/")
    return shared_api_base()


def _connection_refused(exc: BaseException) -> bool:
    if isinstance(exc, ConnectionRefusedError):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, ConnectionRefusedError):
            return True
        if isinstance(reason, OSError) and reason.errno == 61:
            return True
    return bool(isinstance(exc, OSError) and exc.errno == 61)


def _maybe_heal_shared_api_on_refused() -> None:
    """One-shot shared backend crash heal when parallel E2E reloads the dev backend."""
    try:
        from e2e_core.stack_mutation_policy import attach_backend_crash_heal_inner

        dev_stack = MONOREPO_ROOT / "myrm-agent" / "scripts" / "dev" / "dev-stack.sh"
        attach_backend_crash_heal_inner(
            monorepo_root=MONOREPO_ROOT, dev_stack=dev_stack
        )
    except (ImportError, OSError, RuntimeError):
        return


def _e2e_api_urlopen(
    req: urllib.request.Request,
    *,
    timeout_sec: float,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
    no_retry_statuses: frozenset[int] = frozenset(),
) -> HTTPResponse:
    """Retry loopback E2E API reads on transient socket/timeouts under parallel load.

    `no_retry_statuses` disables the blanket HTTP retry for specific status codes
    (e.g. 409 optimistic-lock conflicts): the caller owns the retry policy and
    must re-read the server version before each re-put.
    """
    _validate_loopback_http_url(req.full_url)
    last_error: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return urllib.request.urlopen(req, timeout=timeout_sec)
        except urllib.error.HTTPError as exc:
            last_error = exc
            retriable = (
                exc.code in {409, 423, 500, 503} and exc.code not in no_retry_statuses
            )
            if retriable and attempt + 1 < max_attempts:
                time.sleep(_E2E_API_REQUEST_BACKOFF_SEC * (attempt + 1))
                continue
            raise
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            last_error = exc
            if _connection_refused(exc) and _is_shared_dev_api_url(req.full_url):
                _maybe_heal_shared_api_on_refused()
                if attempt + 1 < max_attempts:
                    time.sleep(_E2E_API_REQUEST_BACKOFF_SEC * (attempt + 1))
                    continue
            if attempt + 1 >= max_attempts:
                raise
            time.sleep(_E2E_API_REQUEST_BACKOFF_SEC * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("E2E API request failed without response")


def _set_http_response_read_timeout(resp: object, timeout_sec: float) -> None:
    """Apply a per-read socket timeout so SSE loops can honor wall deadlines."""
    fp = getattr(resp, "fp", None)
    if fp is None:
        return
    raw = getattr(fp, "raw", None)
    sock = getattr(raw, "_sock", None) if raw is not None else None
    if sock is not None:
        sock.settimeout(max(0.1, timeout_sec))


def _e2e_api_get_json(
    url: str,
    *,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> object:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with _e2e_api_urlopen(
        req, timeout_sec=timeout_sec, max_attempts=max_attempts
    ) as resp:
        return json.loads(resp.read())


def _e2e_api_post_json(
    url: str,
    body: dict[str, object],
    *,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> object:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _e2e_api_urlopen(
        req, timeout_sec=timeout_sec, max_attempts=max_attempts
    ) as resp:
        raw = resp.read()
        if not raw:
            return {}
        return json.loads(raw)
