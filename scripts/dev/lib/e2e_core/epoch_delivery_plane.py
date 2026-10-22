"""Epoch Delivery Plane — pin an epoch-matched API for shared namespace writes.

[INPUT]
- api_verify.resolve_e2e_api_context (POS: epoch / verify candidate SSOT)
- verify_backend_seed.ensure_verify_backend_seed (POS: backend-only isolated runtime)

[OUTPUT]
- evaluate_epoch_pin_eligibility / needs_epoch_pin_backend
- apply_epoch_pin_for_shared_live → env dict for pytest monkeypatch

[POS]
Dev Gate epoch routing layer. Applies to LIVE and STANDARD namespace-write tests and
decouples «run new workspace code» from «consume private ADMIT credit».
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

_EPOCH_PIN_ENV: Final[str] = "MYRM_E2E_EPOCH_PIN"


@dataclass(frozen=True, slots=True)
class EpochPinEligibility:
    eligible: bool
    reason: str


@dataclass(frozen=True, slots=True)
class EpochPinOutcome:
    applied: bool
    api_base: str
    runtime_id: str
    environment: dict[str, str]
    detail: str
    seeded: bool


def evaluate_epoch_pin_eligibility(
    *,
    execution_mode: str,
    access_scope: str,
    workload: str,
) -> EpochPinEligibility:
    mode = execution_mode.strip().upper()
    scope = access_scope.strip().upper()
    load = workload.strip().upper()
    if mode != "SHARED":
        return EpochPinEligibility(False, "execution_mode_not_shared")
    if scope not in ("NAMESPACE_WRITE", "READ"):
        return EpochPinEligibility(False, "access_scope_not_epoch_pin_eligible")
    if load not in ("LIVE", "STANDARD"):
        return EpochPinEligibility(False, "workload_not_pin_eligible")
    return EpochPinEligibility(True, "eligible")


def _isolated_runtime_api_base() -> str:
    """API base of a ready isolated runtime, when the caller pinned one.

    ``MYRM_E2E_ISOLATED_RUNTIME_ID`` is the documented way to run workspace-backend
    tests beside real user data. The runtime already runs the workspace code, so it
    is a valid epoch target and must not fall back to the shared pool.
    """
    runtime_id = os.environ.get("MYRM_E2E_ISOLATED_RUNTIME_ID", "").strip()
    if not runtime_id:
        return ""
    registry_path = Path.home() / ".local" / "state" / "myrm-isolated" / "registry.json"
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        record = (payload.get("runtimes") or {}).get(runtime_id) or {}
    except (OSError, json.JSONDecodeError):
        return ""
    port = int(record.get("backendPort") or 0)
    return f"http://127.0.0.1:{port}" if port > 0 else ""


def _isolated_outcome(*, api_base: str, runtime_id: str) -> EpochPinOutcome:
    """Pin the isolated runtime itself; its health payload has no runtime_id field."""
    healthy = False
    try:
        with urllib.request.urlopen(f"{api_base.rstrip('/')}/api/v1/health", timeout=3.0) as response:
            payload = json.loads(response.read())
        healthy = isinstance(payload, dict) and payload.get("status") == "healthy"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        healthy = False
    if not healthy:
        return EpochPinOutcome(
            applied=False,
            api_base="",
            runtime_id="",
            environment={},
            detail="isolated_runtime_health_failed",
            seeded=False,
        )
    return EpochPinOutcome(
        applied=True,
        api_base=api_base.rstrip("/"),
        runtime_id=runtime_id,
        environment=_runtime_identity_env(runtime_id=runtime_id, api_base=api_base),
        detail=f"isolated_runtime:{runtime_id}",
        seeded=False,
    )


def _shared_epoch_aligned(ctx: object) -> bool:
    candidates = getattr(ctx, "candidates", ())
    for item in candidates:
        source = getattr(item, "source", "")
        epoch_match = getattr(item, "epoch_match", False)
        health_ok = getattr(item, "health_ok", False)
        if source == "shared" and epoch_match and health_ok:
            return True
    return False


def needs_epoch_pin_backend(ctx: object) -> bool:
    """True when shared :8080 is not at workspace epoch (UI must pin verify API)."""
    return not _shared_epoch_aligned(ctx)


def _health_runtime_id(api_base: str) -> str:
    url = f"{api_base.rstrip('/')}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=3.0) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    runtime_id = payload.get("runtime_id")
    return runtime_id.strip() if isinstance(runtime_id, str) else ""


def _runtime_identity_env(*, runtime_id: str, api_base: str) -> dict[str, str]:
    """API-only epoch pin env — no isolated runtime bind (P0-DGR-6)."""
    _ = runtime_id  # health identity only; not an allocator-owned runtime
    return {
        "E2E_API_BASE": api_base.rstrip("/"),
        _EPOCH_PIN_ENV: "1",
        "MYRM_E2E_FORCE_MODEL_SEED": "1",
    }


def _outcome_from_api_base(
    *,
    api_base: str,
    detail: str,
    seeded: bool,
) -> EpochPinOutcome:
    runtime_id = _health_runtime_id(api_base)
    if not runtime_id:
        return EpochPinOutcome(
            applied=False,
            api_base="",
            runtime_id="",
            environment={},
            detail=f"epoch pin health probe failed for {api_base}",
            seeded=seeded,
        )
    env = _runtime_identity_env(runtime_id=runtime_id, api_base=api_base)
    return EpochPinOutcome(
        applied=True,
        api_base=api_base.rstrip("/"),
        runtime_id=runtime_id,
        environment=env,
        detail=detail,
        seeded=seeded,
    )


def apply_epoch_pin_for_shared_live(
    *,
    monorepo: Path,
    node_id: str,
    workload: str = "",
) -> EpochPinOutcome:
    """Resolve or seed an epoch-matched backend; never consumes private ADMIT credit."""
    _ = (node_id, workload)
    from e2e_core.api_verify import resolve_e2e_api_context
    from e2e_core.epoch_backend_pool import (
        invalidate_epoch_backend,
        register_epoch_backend_holder,
    )
    from e2e_core.verify_backend_seed import _isolated_registry_root

    isolated_api = _isolated_runtime_api_base()
    if isolated_api:
        isolated_id = os.environ.get("MYRM_E2E_ISOLATED_RUNTIME_ID", "").strip()
        isolated = _isolated_outcome(api_base=isolated_api, runtime_id=isolated_id)
        if isolated.applied:
            return isolated

    ctx = resolve_e2e_api_context(retry_after_apply=False)
    if not needs_epoch_pin_backend(ctx):
        shared = str(getattr(ctx, "shared_api_base", "") or "").strip()
        return EpochPinOutcome(
            applied=False,
            api_base=shared,
            runtime_id="",
            environment={},
            detail="shared_epoch_aligned",
            seeded=False,
        )

    isolated_root = _isolated_registry_root()
    raw_fp = getattr(ctx, "workspace_fingerprint", "")
    workspace_fp = raw_fp.strip() if isinstance(raw_fp, str) else ""
    shared = str(getattr(ctx, "shared_api_base", "") or "http://127.0.0.1:8080").strip()
    verify_base = str(getattr(ctx, "verify_api_base", "") or "").strip()
    # A stale shared backend is never a valid namespace-write target, even when
    # its health endpoint is reachable. Reuse only a distinct, healthy verify
    # candidate; otherwise seed an epoch-matched backend before the test starts.
    if verify_base and verify_base.rstrip("/") != shared.rstrip("/"):
        from e2e_core.verify_backend_seed import ensure_verify_backend_providers

        ensure_verify_backend_providers(api_base=verify_base, monorepo=monorepo.resolve())
        port = urlsplit(verify_base).port
        reused = _outcome_from_api_base(
            api_base=verify_base,
            detail=f"reused_verify_candidate port={port or '?'}",
            seeded=False,
        )
        if reused.applied:
            register_epoch_backend_holder(
                isolated_root=isolated_root,
                runtime_id=reused.runtime_id,
                api_base=reused.api_base,
                fingerprint=workspace_fp,
            )
            return reused
        invalidate_epoch_backend(
            isolated_root=isolated_root,
            api_base=verify_base,
        )

    from e2e_core.verify_backend_seed import ensure_verify_backend_seed

    seed = ensure_verify_backend_seed(monorepo=monorepo.resolve())
    if not seed.ok:
        return EpochPinOutcome(
            applied=False,
            api_base="",
            runtime_id="",
            environment={},
            detail=f"verify_seed_failed_no_aligned_backend:{seed.detail}",
            seeded=False,
        )
    outcome = _outcome_from_api_base(
        api_base=seed.api_base,
        detail=seed.detail,
        seeded=True,
    )
    if outcome.applied:
        register_epoch_backend_holder(
            isolated_root=isolated_root,
            runtime_id=outcome.runtime_id,
            api_base=outcome.api_base,
            fingerprint=workspace_fp,
            owner_token=getattr(seed, "owner_token", ""),
        )
    if outcome.seeded:
        try:
            from cdp_chat.support import get_e2e_ui_url

            from e2e_core.warm_shell_registry import seal_platform_shell

            seal_platform_shell(ui_url=get_e2e_ui_url(), route_path="/")
        except ImportError:
            pass
    return outcome


def epoch_pin_active() -> bool:
    import os

    return os.environ.get(_EPOCH_PIN_ENV, "").strip() == "1"
