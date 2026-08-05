"""Auth State Provisioner for Chrome E2E isolated contexts (P0-C).

Canonical browser identity uses a fixed data dir, but mux creates isolated contexts
that do not inherit default-profile login. This module tracks runtime-scoped auth
template seal/hydrate/verify/expiry and exposes machine-readable status for
e2e-context and Effect Guard consumers.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import TypedDict

from e2e_browser_pool import resolve_chrome_data_dir, resolve_chrome_port

SCHEMA_VERSION = 1
DEFAULT_TEMPLATE_TTL_SEC = 7 * 86400


class AuthTemplateState(StrEnum):
    MISSING = "MISSING"
    SEALED = "SEALED"
    EXPIRED = "EXPIRED"
    RUNTIME_MISMATCH = "RUNTIME_MISMATCH"
    VERIFY_FAILED = "VERIFY_FAILED"
    SETUP_IN_PROGRESS = "SETUP_IN_PROGRESS"
    UNKNOWN = "UNKNOWN"


class AuthTemplateStatus(TypedDict):
    status: str
    next_action: str
    templateFingerprint: str
    runtimeFingerprint: str
    setupLeaderPid: int | None
    sealedAt: float
    expiresAt: float
    origin: str


class AuthTemplateGateError(RuntimeError):
    """Raised when isolated context new_page requires auth template but it is not ready."""


def _resolve_workspace_fingerprint() -> str:
    env_fp = os.environ.get("MYRM_WORKSPACE_FINGERPRINT", "").strip()
    if env_fp:
        return env_fp
    try:
        from e2e_api_verify import workspace_backend_fingerprint

        return workspace_backend_fingerprint()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return ""


def assert_auth_template_ready_for_isolated_context(
    *,
    workspace_fingerprint: str = "",
) -> AuthTemplateStatus:
    """Fail-closed gate before isolated-context new_page (P0-C)."""
    if os.environ.get("MYRM_E2E_RELAX_AUTH_TEMPLATE", "").strip() == "1":
        return auth_template_status(workspace_fingerprint=workspace_fingerprint)
    workspace = workspace_fingerprint.strip() or _resolve_workspace_fingerprint()
    status = auth_template_status(workspace_fingerprint=workspace)
    if status["next_action"] == "READY":
        return status
    raise AuthTemplateGateError(
        "AUTH_TEMPLATE_GATE: isolated context requires sealed auth template; "
        f"status={status['status']} next_action={status['next_action']} "
        f"runtime_fp={status['runtimeFingerprint']}"
    )


def _resolve_template_cookies(template: dict[str, object]) -> list[dict[str, object]]:
    cookies_ref = template.get("cookiesRef")
    if isinstance(cookies_ref, str) and cookies_ref.strip():
        try:
            from e2e_auth_keychain import load_auth_cookie_blob  # noqa: PLC0415

            loaded = load_auth_cookie_blob(cookies_ref)
            if loaded is not None:
                return loaded
        except ImportError:
            pass
    cookies_raw = template.get("cookies", [])
    if isinstance(cookies_raw, list):
        return [item for item in cookies_raw if isinstance(item, dict)]
    return []


def hydrate_auth_template_for_context(
    *,
    context_id: str,
    workspace_fingerprint: str = "",
) -> bool:
    """Hydrate sealed template cookies into an isolated context and probe auth."""
    normalized = context_id.strip()
    if not normalized:
        return False
    workspace = workspace_fingerprint.strip() or _resolve_workspace_fingerprint()
    status = auth_template_status(workspace_fingerprint=workspace)
    if status["next_action"] != "READY":
        return False
    template = _load_template()
    if template is None:
        return False
    cookies_raw = _resolve_template_cookies(template)
    if not cookies_raw:
        return True
    origin = str(template.get("origin", "")).strip()
    if not origin:
        return False
    probe_path = str(template.get("probePath", "/")).strip() or "/"
    try:
        from e2e_auth_cdp import (  # noqa: PLC0415
            cdp_auth_hydrate_enabled,
            hydrate_and_probe_context,
        )
    except ImportError:
        return False
    if not cdp_auth_hydrate_enabled():
        return True
    observed = hydrate_and_probe_context(
        browser_context_id=normalized,
        origin=origin,
        cookies=[item for item in cookies_raw if isinstance(item, dict)],
        probe_path=probe_path,
    )
    if observed is None:
        return False
    return observed


def _state_dir() -> Path:
    override = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    return Path(override) if override else Path.home() / ".local/state/myrm-dev"


def _template_path() -> Path:
    return _state_dir() / "e2e-auth-template.json"


def _setup_lock_path() -> Path:
    return _state_dir() / "e2e-auth-setup.lock"


def runtime_fingerprint(*, workspace_fingerprint: str = "") -> str:
    workspace = (
        workspace_fingerprint.strip()
        or os.environ.get("MYRM_WORKSPACE_FINGERPRINT", "").strip()
    )
    payload = (
        f"port={resolve_chrome_port()}|data={resolve_chrome_data_dir()}|ws={workspace}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _load_template() -> dict[str, object] | None:
    path = _template_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_setup_leader_pid() -> int | None:
    path = _setup_lock_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    leader_pid = payload.get("leaderPid")
    if not isinstance(leader_pid, int) or leader_pid <= 0:
        return None
    try:
        os.kill(leader_pid, 0)
    except OSError:
        return None
    return leader_pid


def auth_template_status(*, workspace_fingerprint: str = "") -> AuthTemplateStatus:
    runtime_fp = runtime_fingerprint(workspace_fingerprint=workspace_fingerprint)
    leader_pid = _read_setup_leader_pid()
    status: AuthTemplateStatus = {
        "status": AuthTemplateState.UNKNOWN.value,
        "next_action": "OBSERVABILITY_UNKNOWN",
        "templateFingerprint": "",
        "runtimeFingerprint": runtime_fp,
        "setupLeaderPid": leader_pid,
        "sealedAt": 0.0,
        "expiresAt": 0.0,
        "origin": "",
    }

    if leader_pid is not None:
        status["status"] = AuthTemplateState.SETUP_IN_PROGRESS.value
        status["next_action"] = "AUTH_SETUP_WAIT"
        return status

    template = _load_template()
    if template is None:
        status["status"] = AuthTemplateState.MISSING.value
        status["next_action"] = "AUTH_SETUP_REQUIRED"
        return status

    template_fp = str(template.get("templateFingerprint", ""))
    stored_runtime = str(template.get("runtimeFingerprint", ""))
    sealed_at = float(template.get("sealedAt", 0) or 0)
    expires_at = float(template.get("expiresAt", 0) or 0)
    origin = str(template.get("origin", ""))
    status["templateFingerprint"] = template_fp
    status["sealedAt"] = sealed_at
    status["expiresAt"] = expires_at
    status["origin"] = origin

    if not template_fp or not stored_runtime:
        status["status"] = AuthTemplateState.VERIFY_FAILED.value
        status["next_action"] = "AUTH_SETUP_REQUIRED"
        return status

    if stored_runtime != runtime_fp:
        status["status"] = AuthTemplateState.RUNTIME_MISMATCH.value
        status["next_action"] = "AUTH_HYDRATE_REQUIRED"
        return status

    if expires_at > 0 and time.time() > expires_at:
        status["status"] = AuthTemplateState.EXPIRED.value
        status["next_action"] = "AUTH_SETUP_REQUIRED"
        return status

    status["status"] = AuthTemplateState.SEALED.value
    status["next_action"] = "READY"
    return status


@contextmanager
def auth_setup_leader_lock(*, wait_sec: float = 30.0) -> Iterator[None]:
    """Acquire single-flight auth setup leader lock (fail-closed on contention)."""
    path = _setup_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        deadline = time.monotonic() + max(0.1, wait_sec)
        acquired = False
        while time.monotonic() < deadline:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                handle.seek(0)
                handle.truncate()
                handle.write(
                    json.dumps({"leaderPid": os.getpid(), "startedAt": time.time()})
                )
                handle.flush()
                break
            except BlockingIOError:
                time.sleep(0.2)
        if not acquired:
            raise TimeoutError(f"auth setup leader lock busy after {wait_sec}s")
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def seal_auth_template(
    *,
    origin: str,
    test_account: str = "",
    ttl_sec: float = DEFAULT_TEMPLATE_TTL_SEC,
    workspace_fingerprint: str = "",
    cookies: list[dict[str, object]] | None = None,
    probe_path: str = "/",
) -> AuthTemplateStatus:
    """Persist sealed auth template metadata after successful manual setup."""
    runtime_fp = runtime_fingerprint(workspace_fingerprint=workspace_fingerprint)
    now = time.time()
    template_fp = hashlib.sha256(
        f"{origin.strip()}|{test_account.strip()}|{runtime_fp}|{now}".encode()
    ).hexdigest()[:16]
    record: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "templateFingerprint": template_fp,
        "runtimeFingerprint": runtime_fp,
        "sealedAt": now,
        "expiresAt": now + max(3600.0, ttl_sec),
        "origin": origin.strip(),
        "testAccount": test_account.strip(),
        "probePath": probe_path.strip() or "/",
    }
    if cookies:
        try:
            from e2e_auth_keychain import (  # noqa: PLC0415
                keychain_storage_enabled,
                store_auth_cookie_blob,
            )
        except ImportError:
            record["cookies"] = cookies
        else:
            blob_ref = store_auth_cookie_blob(template_fp, cookies)
            record["cookiesRef"] = blob_ref
            record["cookiesEncrypted"] = keychain_storage_enabled()
            if not keychain_storage_enabled():
                record["cookies"] = cookies
    path = _template_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)
    return auth_template_status(workspace_fingerprint=workspace_fingerprint)


def reseal_auth_template_for_current_runtime(
    *,
    origin: str,
    workspace_fingerprint: str = "",
) -> AuthTemplateStatus:
    """Re-stamp sealed auth metadata when runtime fingerprint drifted (P0-C).

    Preserves cookies/probe metadata from the prior template when present so
    SHARED READ tests can hydrate without manual auth setup after ready --chrome.
    """
    workspace = workspace_fingerprint.strip() or _resolve_workspace_fingerprint()
    status = auth_template_status(workspace_fingerprint=workspace)
    if status["next_action"] == "READY":
        return status
    template = _load_template()
    cookies = _resolve_template_cookies(template) if template is not None else None
    test_account = (
        str(template.get("testAccount", "")).strip() if template is not None else ""
    )
    probe_path = (
        str(template.get("probePath", "/")).strip() or "/"
        if template is not None
        else "/"
    )
    return seal_auth_template(
        origin=origin.strip(),
        test_account=test_account,
        workspace_fingerprint=workspace,
        cookies=cookies or None,
        probe_path=probe_path,
    )
