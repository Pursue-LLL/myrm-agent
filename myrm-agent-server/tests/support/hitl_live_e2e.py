"""Shared HITL pin + probe helpers for LIVE chrome / HTTP E2E."""

from __future__ import annotations

from cdp_chat.support import (
    ensure_e2e_hitl_mode,
    ensure_e2e_onboarding_complete,
    fetch_config_value,
    shared_hot_e2e_api_base,
)


def hitl_probe(api_url: str) -> dict[str, object]:
    from cdp_chat.support import _e2e_api_get_json

    probe = _e2e_api_get_json(
        f"{api_url.rstrip('/')}/api/v1/security/allowlist/test/hitl-probe",
        timeout_sec=15.0,
    )
    return probe if isinstance(probe, dict) else {}


def pin_and_verify_hitl_mode(api_url: str) -> None:
    """Pin global securityConfig to ASK mode and verify via test-only hitl-probe."""
    ensure_e2e_hitl_mode(api_url=api_url)
    targets: list[str] = [api_url.rstrip("/")]
    shared = shared_hot_e2e_api_base()
    if shared not in targets:
        targets.append(shared)
    for target in targets:
        ensure_e2e_onboarding_complete(api_url=target)
        cfg = fetch_config_value("securityConfig", api_url=target)
        if cfg.get("yoloModeEnabled") or cfg.get("yolo_mode_enabled"):
            raise AssertionError(f"LIVE E2E requires YOLO off on {target}; got {cfg!r}")
        if int(cfg.get("approvalTimeoutSeconds") or cfg.get("approval_timeout_seconds") or 0) < 300:
            raise AssertionError(
                f"LIVE E2E requires approval timeout >= 300s on {target}; got {cfg!r}"
            )
        probe = hitl_probe(target)
        if probe.get("yolo") or probe.get("expects_ask") is not True:
            raise AssertionError(
                f"LIVE E2E HITL probe failed on {target}: {probe!r}; cfg={cfg!r}"
            )
