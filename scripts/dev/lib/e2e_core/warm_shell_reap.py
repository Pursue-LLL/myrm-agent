"""Reclaim policy for warm-shell registry entries (WarmShellRegistry companion).

[INPUT]
- warm_shell_registry registry files (sealedTargets + sealedAt per fingerprint)
- CDP HTTP close on the dedicated E2E port

[OUTPUT]
- live_sealed_target_ids() — still-unexpired seals treated as claimed pages
- reap_expired_sealed_targets() — exact-targetId close + expired file/lock cleanup

[POS]
Warm-shell reclaim policy, split out of ``warm_shell_registry`` so the seal/fresh
hot-path module stays within its size budget. Closing is by exact targetId only:
URL inference is never used, and a page is only reclaimable once its seal TTL
elapsed because an unexpired shell is still reachable by the hot path.
"""

from __future__ import annotations

import time
from pathlib import Path

from e2e_core.warm_shell_registry import (
    _DEFAULT_TTL_SEC,
    _read_registry_payload,
    _registry_file_lock,
    _registry_files,
    _registry_path,
    _write_registry_payload,
    read_platform_shell,
)


def live_sealed_target_ids(*, ttl_sec: float = _DEFAULT_TTL_SEC) -> set[str]:
    """Sealed target ids still inside their TTL, across every workspace fingerprint.

    A fresh shell is reachable by the hot path, so its page must be treated as
    claimed by hygiene and by the orphan budget even though no wave lease names
    it. Reading only the current fingerprint would leave other fingerprints'
    shells invisible while they are still hot.
    """
    live: set[str] = set()
    now = time.time()
    for path in _registry_files():
        targets = _read_registry_payload(path).get("sealedTargets")
        if not isinstance(targets, dict):
            continue
        for target_id, sealed_at in targets.items():
            if (
                isinstance(target_id, str)
                and target_id.strip()
                and isinstance(sealed_at, (int, float))
                and (now - float(sealed_at)) <= float(ttl_sec)
            ):
                live.add(target_id.strip())
    return live


def reap_expired_sealed_targets(
    *,
    cdp_port: int | None = None,
    workspace_fp: str | None = None,
    ttl_sec: float = _DEFAULT_TTL_SEC,
) -> tuple[int, int]:
    """Close warm-shell targets whose seal TTL elapsed — exact targetId only.

    Expired hot shells are unreachable by the hot path (``platform_shell_fresh``
    already reports False), so their physical pages would otherwise linger
    forever while every later seal creates a new page. Ownership is never
    inferred from URL: only ids recorded by ``seal_platform_shell`` are eligible.

    ``workspace_fp=None`` sweeps every fingerprint. Scoping the sweep to the
    current fingerprint left every other fingerprint's sealed pages — and its
    registry files — to accumulate forever, because a fingerprint is not
    revisited once the workspace changes.
    """
    if workspace_fp is not None:
        return _reap_fingerprint(
            workspace_fp=workspace_fp, cdp_port=cdp_port, ttl_sec=ttl_sec
        )
    closed_total = 0
    failed_total = 0
    for path in _registry_files():
        fp = str(_read_registry_payload(path).get("workspaceFingerprint") or "").strip()
        if not fp:
            continue
        closed, failed = _reap_fingerprint(
            workspace_fp=fp, cdp_port=cdp_port, ttl_sec=ttl_sec
        )
        closed_total += closed
        failed_total += failed
    _prune_registry_files(_registry_files())
    return closed_total, failed_total


def _prune_registry_files(paths: list[Path]) -> None:
    """Remove registry files whose last seal expired, with their lock files.

    A workspace fingerprint that never seals again would otherwise leave a JSON
    plus a lock file behind forever (measured live: 1789 fingerprints, 1756
    locks), so the registry directory grows without bound.
    """
    for path in paths:
        try:
            sealed_at = _read_registry_payload(path).get("sealedAt")
            if not isinstance(sealed_at, (int, float)):
                continue
            if (time.time() - float(sealed_at)) <= _DEFAULT_TTL_SEC:
                continue
            path.unlink(missing_ok=True)
            path.with_suffix(".lock").unlink(missing_ok=True)
        except OSError:
            continue


def _reap_fingerprint(
    *, workspace_fp: str, cdp_port: int | None, ttl_sec: float
) -> tuple[int, int]:
    fp = workspace_fp.strip()
    if not fp:
        return 0, 0
    record = read_platform_shell(workspace_fp=fp)
    if record is None or not record.sealed_targets:
        return 0, 0
    now = time.time()
    expired = [
        target
        for target, sealed_at in record.sealed_targets
        if (now - sealed_at) > float(ttl_sec)
    ]
    if not expired:
        return 0, 0

    from e2e_core.infra_browser_registry import close_exact_target  # noqa: PLC0415

    port = cdp_port if cdp_port is not None else 9333
    closed: list[str] = []
    failed: list[str] = []
    for target in expired:
        if close_exact_target(port, target):
            closed.append(target)
        else:
            failed.append(target)

    path = _registry_path(fp)
    with _registry_file_lock(workspace_fp=fp):
        payload = _read_registry_payload(path)
        if payload:
            raw_targets = payload.get("sealedTargets")
            if isinstance(raw_targets, dict):
                # Drop reaped ids; keep failures so a later sweep retries them.
                remaining = {
                    key: value
                    for key, value in raw_targets.items()
                    if key not in closed
                }
                if remaining:
                    payload["sealedTargets"] = remaining
                else:
                    payload.pop("sealedTargets", None)
                _write_registry_payload(path, payload)
    return len(closed), len(failed)
