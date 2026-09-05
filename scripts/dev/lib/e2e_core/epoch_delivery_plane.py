"""Epoch Delivery Plane — pin epoch-matched API for SHARED LIVE tests without private ADMIT.

[INPUT]
- api_verify.resolve_e2e_api_context (POS: epoch / verify candidate SSOT)
- verify_backend_seed.ensure_verify_backend_seed (POS: backend-only isolated runtime)

[OUTPUT]
- evaluate_epoch_pin_eligibility / needs_epoch_pin_backend
- apply_epoch_pin_for_shared_live → env dict for pytest monkeypatch

[POS]
Dev Gate epoch routing layer. Decouples «run new workspace code» from «consume private ADMIT credit».
"""

from __future__ import annotations

import json
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
    if scope != "NAMESPACE_WRITE":
        return EpochPinEligibility(False, "access_scope_not_namespace_write")
    if load not in ("LIVE", "STANDARD"):
        return EpochPinEligibility(False, "workload_not_pin_eligible")
    return EpochPinEligibility(True, "eligible")


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
        with urllib.request.urlopen(url, timeout=3.0) as response:  # noqa: S310
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
    node_id: str,  # noqa: ARG001 — reserved for structured logs
    workload: str = "",
) -> EpochPinOutcome:
    """Resolve or seed an epoch-matched backend; never consumes private ADMIT credit."""
    _ = workload  # eligibility is decided by the caller before this resolver
    from e2e_core.api_verify import resolve_e2e_api_context  # noqa: PLC0415

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

    shared = str(getattr(ctx, "shared_api_base", "") or "http://127.0.0.1:8080").strip()
    verify_base = str(getattr(ctx, "verify_api_base", "") or "").strip()
    # A stale shared backend is never a valid namespace-write target, even when
    # its health endpoint is reachable. Reuse only a distinct, healthy verify
    # candidate; otherwise seed an epoch-matched backend before the test starts.
    if verify_base and verify_base.rstrip("/") != shared.rstrip("/"):
        port = urlsplit(verify_base).port
        reused = _outcome_from_api_base(
            api_base=verify_base,
            detail=f"reused_verify_candidate port={port or '?'}",
            seeded=False,
        )
        if reused.applied:
            return reused

    from e2e_core.verify_backend_seed import ensure_verify_backend_seed  # noqa: PLC0415

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
