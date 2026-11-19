"""Backend config pins of an E2E run over the API.

[INPUT]
- cdp_chat.support.api_client::_e2e_api_post_json, _e2e_api_urlopen, _validate_loopback_http_url, get_e2e_api_url, shared_hot_e2e_api_base (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)
- cdp_chat.support.config.store::_config_http_json, fetch_config_value, put_config_value (POS: Global config records over the API with optimistic locking: a per-key cross-process mutex, reads and writes with bounded retry)
- dev_gate.contract::signoff_hitl_pin_max_attempts, signoff_hitl_pin_request_timeout_sec (POS: Dev Gate contract SSOT: error tokens, parallel caps and timeout budgets)

[OUTPUT]
- ensure_e2e_yolo_mode, ensure_e2e_hitl_mode, ensure_e2e_onboarding_complete, ensure_e2e_memory_disabled, clear_search_services_ssot: the pins
- _pin_hitl_on_api_with_retry, _hitl_pin_retry_policy: HITL pin with retry; the policy is shared with page_pins

[POS]
Pins the backend config an E2E run needs over the API: YOLO and HITL mode, onboarding complete, memory disabled, search services cleared.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request

from cdp_chat.support.api_client import (
    _e2e_api_post_json,
    _e2e_api_urlopen,
    _validate_loopback_http_url,
    get_e2e_api_url,
    shared_hot_e2e_api_base,
)
from cdp_chat.support.config.store import (
    _config_http_json,
    fetch_config_value,
    put_config_value,
)


def _yolo_security_payload(current: dict[str, object]) -> dict[str, object]:
    now = int(time.time())
    return {
        **current,
        "yoloModeEnabled": True,
        "yoloModeEnabledAt": now,
        "yoloModeTimeout": None,
        "yolo_mode_enabled": True,
        "yolo_mode_enabled_at": float(now),
        "yolo_mode_timeout": None,
        "permissions": {"*": "allow", "computer_use": "allow"},
        "domainHitlEnabled": False,
        # SecurityConfig prefers autoModeEnabled over autoReviewEnabled — must be False
        # for YOLO E2E or AI Security Reviewer LLM init errors stall on approval cards.
        "autoModeEnabled": False,
        "autoReviewEnabled": False,
        "planConfirmEnabled": False,
        "approvalTimeoutSeconds": 900,
        "approval_timeout_seconds": 900,
    }


def _pin_yolo_on_api(api_url: str) -> None:
    last_exc: BaseException | None = None
    current: dict[str, object] = {}
    for attempt in range(5):
        try:
            current = fetch_config_value("securityConfig", api_url=api_url)
            last_exc = None
            break
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last_exc = exc
            if attempt >= 4:
                raise RuntimeError(
                    f"SHPOIB config fetch failed after 5 attempts: {exc}"
                ) from exc
            time.sleep(2.0 * (attempt + 1))
    if last_exc is not None:
        raise RuntimeError(f"SHPOIB config fetch failed: {last_exc}") from last_exc
    put_config_value(
        "securityConfig",
        _yolo_security_payload(current),
        api_url=api_url,
    )
    persisted = fetch_config_value("securityConfig", api_url=api_url)
    if not persisted.get("yoloModeEnabled") and not persisted.get("yolo_mode_enabled"):
        raise RuntimeError(f"Failed to persist YOLO securityConfig: {persisted}")


def ensure_e2e_yolo_mode(*, api_url: str | None = None) -> None:
    """Enable YOLO mode for live Chrome agent E2E (skips tool approval gate).

    Pins private SHPOIB API **and** the shared backend (HITL dual-target SSOT).
    Parallel LIVE HITL tests may leave ``computer_use: ask`` on shared; Next
    may briefly proxy via shared before ``__MYRM_E2E_API_BASE__`` inject.
    """
    targets: list[str] = []
    if api_url:
        targets.append(api_url.rstrip("/"))
    else:
        targets.append(get_e2e_api_url().rstrip("/"))
    shared = shared_hot_e2e_api_base()
    if shared not in targets:
        targets.append(shared)
    for target in targets:
        _pin_yolo_on_api(target)


def _hitl_security_payload(current: dict[str, object]) -> dict[str, object]:
    return {
        **current,
        "yoloModeEnabled": False,
        "yoloModeEnabledAt": None,
        "yoloModeTimeout": None,
        "yolo_mode_enabled": False,
        "yolo_mode_enabled_at": None,
        "yolo_mode_timeout": None,
        "autoModeEnabled": False,
        "autoReviewEnabled": False,
        "planConfirmEnabled": False,
        "domainHitlEnabled": False,
        "approvalTimeoutBehavior": "deny",
        "approvalTimeoutSeconds": 900,
        "approval_timeout_seconds": 900,
        "permissions": {
            "shell_exec": "ask",
            "code_interpreter": "ask",
            "computer_use": "ask",
        },
    }


def _pin_hitl_on_api(api_url: str, *, request_timeout_sec: float = 15.0) -> None:
    current_payload = _config_http_json(
        "GET",
        "/api/v1/config/securityConfig",
        api_url=api_url,
        timeout_sec=request_timeout_sec,
        max_attempts=5,
    )
    current_value = current_payload.get("value")
    current = current_value if isinstance(current_value, dict) else {}
    put_config_value(
        "securityConfig",
        _hitl_security_payload(current),
        api_url=api_url,
    )
    reset_url = (
        f"{api_url.rstrip('/')}/api/v1/security/allowlist/test/reset-hitl-runtime"
    )
    reset_req = urllib.request.Request(
        reset_url,
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    _validate_loopback_http_url(reset_url)
    try:
        with _e2e_api_urlopen(
            reset_req, timeout_sec=request_timeout_sec, max_attempts=5
        ) as reset_resp:
            if reset_resp.status != 200:
                body = reset_resp.read(500)
                raise RuntimeError(
                    f"reset-hitl-runtime failed on {api_url}: {reset_resp.status} {body!r}"
                )
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    persisted_payload = _config_http_json(
        "GET",
        "/api/v1/config/securityConfig",
        api_url=api_url,
        timeout_sec=request_timeout_sec,
        max_attempts=5,
    )
    persisted_value = persisted_payload.get("value")
    persisted = persisted_value if isinstance(persisted_value, dict) else {}
    if persisted.get("yoloModeEnabled") or persisted.get("yolo_mode_enabled"):
        raise RuntimeError(
            f"Failed to disable YOLO securityConfig on {api_url}: {persisted}"
        )
    perms = persisted.get("permissions")
    if isinstance(perms, dict) and str(perms.get("*", "")).lower() == "allow":
        raise RuntimeError(
            f"Wildcard permissions still allow-all on {api_url}: {persisted}"
        )
    if isinstance(perms, dict) and str(perms.get("computer_use", "")).lower() != "ask":
        raise RuntimeError(
            f"computer_use permission must be ask on {api_url}: {persisted}"
        )


_HITL_PIN_BACKOFF_SEC = 1.5


def _hitl_pin_retry_policy() -> tuple[int, float]:
    try:
        from dev_gate.contract import (
            signoff_hitl_pin_max_attempts,
            signoff_hitl_pin_request_timeout_sec,
        )

        return (
            signoff_hitl_pin_max_attempts(),
            signoff_hitl_pin_request_timeout_sec(),
        )
    except ImportError:
        return 3, 15.0


def _pin_hitl_on_api_with_retry(api_url: str) -> None:
    """Retry transient loopback timeouts while pinning HITL mode."""
    max_attempts, request_timeout_sec = _hitl_pin_retry_policy()
    last_error: OSError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            _pin_hitl_on_api(api_url, request_timeout_sec=request_timeout_sec)
            return
        except OSError as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            time.sleep(_HITL_PIN_BACKOFF_SEC * attempt)
    if last_error is not None:
        raise RuntimeError(
            f"Failed to pin HITL securityConfig on {api_url} after "
            f"{max_attempts} attempts: {last_error}"
        ) from last_error


def ensure_e2e_hitl_mode(*, api_url: str | None = None) -> None:
    """Disable YOLO + auto-review so shell HITL approval dialogs appear.

    Agent-level ``yoloModeEnabled: false`` does not override user securityConfig
    (merge uses OR). LIVE approval E2E must pin global securityConfig on the
    target API (including SHPOIB private ``:180xx`` backends).

    Also pins the shared backend when it differs from the private API — SHPOIB UI
    may briefly stream via Next ``/api/v1`` proxy before ``__MYRM_E2E_API_BASE__``
    inject completes, and parallel LIVE tests leave YOLO on the shared backend.

    Also clears wildcard ``permissions.*=allow`` left by ``ensure_e2e_yolo_mode``.
    """
    targets: list[str] = []
    if api_url:
        targets.append(api_url.rstrip("/"))
    shared = shared_hot_e2e_api_base()
    if shared not in targets:
        targets.append(shared)
    for target in targets:
        _pin_hitl_on_api_with_retry(target)


def ensure_e2e_onboarding_complete(*, api_url: str) -> None:
    """Mark onboarding complete on any SHPOIB private or shared API (bypasses http_json allowlist)."""
    _e2e_api_post_json(
        f"{api_url.rstrip('/')}/api/v1/config/onboarding/complete",
        {},
        timeout_sec=15.0,
    )


def clear_search_services_ssot(*, api_url: str | None = None) -> None:
    """Python SSOT: empty searchServices on the bound E2E API, with verify."""
    resolved = (api_url or get_e2e_api_url()).rstrip("/")
    put_config_value(
        "searchServices",
        {"searchServiceConfigs": []},
        api_url=resolved,
    )
    value = fetch_config_value("searchServices", api_url=resolved)
    configs = value.get("searchServiceConfigs")
    if configs != []:
        raise RuntimeError(
            f"searchServices must be empty after Python PUT, got {value!r} api={resolved}"
        )


def ensure_e2e_memory_disabled(*, api_url: str | None = None) -> None:
    """Disable memory for live agent E2E to avoid poisoned procedural briefs."""
    personal = fetch_config_value("personalSettings", api_url=api_url)
    merged: dict[str, object] = {
        **personal,
        "enableMemory": False,
        "enableMemoryAutoExtraction": False,
    }
    put_config_value("personalSettings", merged, api_url=api_url)
