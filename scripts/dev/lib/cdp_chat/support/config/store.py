"""Config records over the API.

[INPUT]
- cdp_chat.support.api_client::_E2E_API_REQUEST_ATTEMPTS, _E2E_API_REQUEST_BACKOFF_SEC, _e2e_api_urlopen, get_e2e_api_url (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)
- cdp_chat.support.timeouts::e2e_parallel_config_api_timeout_sec (POS: Turns a base timeout into the budget a parallel run needs, from the active wave leases, parallel tests and mux peers)

[OUTPUT]
- config_write_mutex: serialize read-modify-write of one config key across parallel tests
- fetch_config_record, fetch_config_value, put_config_value: read and optimistically write a config key

[POS]
Global config records over the API with optimistic locking: a per-key cross-process mutex, reads and writes with bounded retry.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

from cdp_chat.support.api_client import (
    _E2E_API_REQUEST_ATTEMPTS,
    _E2E_API_REQUEST_BACKOFF_SEC,
    _e2e_api_urlopen,
    get_e2e_api_url,
)
from cdp_chat.support.timeouts import e2e_parallel_config_api_timeout_sec

_CONFIG_MUTEX_DIR = Path("/tmp/myrm-e2e-config-mutex")
_CONFIG_MUTEX_WAIT_SEC = float(
    os.environ.get("MYRM_E2E_CONFIG_MUTEX_WAIT_SEC", "120").strip() or "120"
)


@contextlib.contextmanager
def config_write_mutex(
    config_key: str, *, wait_sec: float | None = None
) -> Iterator[None]:
    """Serialize read-modify-write of a global config key across parallel tests.

    The providers config is a single global key shared by every chrome_e2e
    session. Even with optimistic-lock PUTs (R2), concurrent tests can still
    overwrite each other's seed between their read and their put. A per-key
    advisory flock scopes the whole "read → merge → put → verify → restore"
    window to one writer. `wait_sec` bounds how long a peer test may hold it;
    exceeding the bound is an honest serialization failure, not a silent retry.
    """
    _CONFIG_MUTEX_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = _CONFIG_MUTEX_DIR / f"{config_key}.lock"
    resolved_wait = wait_sec if wait_sec is not None else _CONFIG_MUTEX_WAIT_SEC
    with lock_path.open("a+", encoding="utf-8") as handle:
        deadline = time.monotonic() + resolved_wait
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"E2E_CONFIG_MUTEX_TIMEOUT: '{config_key}' held by a peer "
                        f"beyond {resolved_wait:.0f}s — serialize or reconcile writers"
                    ) from None
                time.sleep(0.25)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _config_http_json(
    method: str,
    path: str,
    body: dict[str, object] | None = None,
    *,
    api_url: str | None = None,
    timeout_sec: float = 10.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
    no_retry_statuses: frozenset[int] = frozenset(),
) -> dict[str, object]:
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{resolved_api}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method=method,
    )
    with _e2e_api_urlopen(
        req,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
        no_retry_statuses=no_retry_statuses,
    ) as resp:
        raw = resp.read()
        if not raw:
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {"value": payload}


def fetch_config_record(
    config_key: str, *, api_url: str | None = None
) -> dict[str, object]:
    """Fetch the full config record (value + version + updatedAt + deviceId).

    The `version` is the optimistic-lock token used by `put_config_value` to
    detect concurrent writers; last-write-wins PUTs are the R2 root cause.
    """
    base_timeout = 15.0 if os.environ.get("E2E_SIGNOFF", "").strip() == "1" else 10.0
    timeout_sec = e2e_parallel_config_api_timeout_sec(base_timeout)
    attempts = _E2E_API_REQUEST_ATTEMPTS
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        # mux gen bump / parallel SHPOIB may transiently stall config GET.
        attempts = max(attempts, 6)
    elif timeout_sec > base_timeout:
        attempts = max(attempts, 5)
    payload = _config_http_json(
        "GET",
        f"/api/v1/config/{config_key}",
        api_url=api_url,
        timeout_sec=timeout_sec,
        max_attempts=attempts,
    )
    return payload if isinstance(payload, dict) else {}


def fetch_config_value(
    config_key: str, *, api_url: str | None = None
) -> dict[str, object]:
    value = fetch_config_record(config_key, api_url=api_url).get("value")
    return value if isinstance(value, dict) else {}


def put_config_value(
    config_key: str,
    value: dict[str, object],
    *,
    api_url: str | None = None,
    max_conflict_retries: int = 5,
) -> None:
    """Write a config with an optimistic-lock (expectedVersion) and bounded retry.

    Reads the current server version, PUTs with `expectedVersion`, and on a 409
    conflict re-reads and retries (≤ max_conflict_retries). Still conflicting =>
    fail-fast with the surviving peer's version, so a caller never silently
    overwrites a concurrent writer's seed (R2).
    """
    peer_version: str | None = None
    for attempt in range(max_conflict_retries):
        record = fetch_config_record(config_key, api_url=api_url)
        version = str(record.get("version") or "0")
        try:
            _config_http_json(
                "PUT",
                f"/api/v1/config/{config_key}",
                {"deviceId": "web", "value": value, "expectedVersion": version},
                api_url=api_url,
                timeout_sec=30.0,
                max_attempts=5,
                no_retry_statuses=frozenset({409}),
            )
            return
        except urllib.error.HTTPError as exc:
            if exc.code != 409:
                raise
            peer_version = version
            if attempt + 1 < max_conflict_retries:
                time.sleep(_E2E_API_REQUEST_BACKOFF_SEC * (attempt + 1))
                continue
            raise RuntimeError(
                f"E2E config optimistic-lock exhausted for '{config_key}': "
                f"{max_conflict_retries} conflicts with peer version={peer_version!r}; "
                "a parallel test is mutating the same global config — serialize "
                "writers (E2E_CONFIG_MUTEX) or reconcile the shared seed"
            ) from exc
