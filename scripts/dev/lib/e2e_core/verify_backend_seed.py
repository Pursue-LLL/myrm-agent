"""On-demand backend-only isolated runtime for verify-api when epoch match is missing.

[INPUT]
- isolated_runtime.allocator.runtime_environment (POS: per-runtime env SSOT)
- dev_gate.contract.LIVE_SHPOIB_MAX_CONCURRENT (POS: private backend cap)
- runtime_identity._backend_source_fingerprint (POS: workspace epoch SSOT)

[OUTPUT]
- ensure_verify_backend_seed(): spawn ephemeral backend-only runtime at workspace epoch (cap/bootstrap retry)
- _spawn_verify_backend_seed(): single seed attempt with claim_bootstrap_slot → running phase transition

[POS]
Verification Plane helper — unblocks verify-api during parallel E2E without stopping pytest.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dev_gate.contract import LIVE_SHPOIB_MAX_CONCURRENT
from e2e_core.runtime_identity import _backend_source_fingerprint

SEED_START_TIMEOUT_SEC: Final[int] = 180
SEED_HEALTH_WAIT_SEC: Final[float] = 120.0
SEED_PARALLEL_HEALTH_WAIT_SEC: Final[float] = 45.0
SEED_PARALLEL_SPAWN_WALL_SEC: Final[float] = 60.0
SEED_CAP_RETRY_BACKOFF_SEC: Final[float] = 5.0
SEED_PARALLEL_CAP_RETRY_BACKOFF_SEC: Final[float] = 2.0
SEED_CAP_MAX_ATTEMPTS: Final[int] = 2
SEED_PROGRESS_EMIT_INTERVAL_SEC: Final[float] = 10.0


@dataclass(frozen=True, slots=True)
class VerifyBackendSeedResult:
    ok: bool
    runtime_id: str
    api_base: str
    detail: str
    owner_token: str = ""


def _ensure_scripts_dev_importable(monorepo: Path) -> Path:
    dev_dir = monorepo / "scripts" / "dev"
    dev_str = str(dev_dir.resolve())
    if dev_str not in sys.path:
        sys.path.insert(0, dev_str)
    return dev_dir


def _isolated_registry_root() -> Path:
    override = os.environ.get("MYRM_ISOLATED_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return _real_user_home() / ".local/state/myrm-isolated"


def _real_user_home() -> Path:
    """Real login home — Cursor sandboxes HOME (~/.cursor2), splitting state."""
    try:
        import pwd

        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError, OSError):
        return Path.home()


def _read_stored_fingerprint(state_dir: Path) -> str:
    epoch_file = state_dir / "stack-epoch.json"
    if not epoch_file.is_file():
        return ""
    try:
        raw = json.loads(epoch_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(raw, dict):
        return ""
    stored_fp = raw.get("source_fingerprint")
    return stored_fp.strip() if isinstance(stored_fp, str) else ""


def _health_ok(api_base: str) -> bool:
    url = f"{api_base.rstrip('/')}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _count_active_backend_only() -> int:
    from isolated_runtime.registry import (  # noqa: PLC0415
        ACTIVE_PHASES,
        owner_is_active,
        process_is_alive,
        read_registry,
    )

    registry_path = _isolated_registry_root() / "registry.json"
    if not registry_path.is_file():
        return 0
    try:
        records = read_registry(registry_path)
    except RuntimeError:
        return 0
    count = 0
    for record in records.values():
        if not record.get("backendOnly"):
            continue
        if record["phase"] not in ACTIVE_PHASES:
            continue
        owner_pid = int(record.get("ownerPid") or 0)
        if not process_is_alive(owner_pid):
            continue
        if owner_is_active(record):
            count += 1
    return count


def _parallel_pressure_active() -> bool:
    try:
        from e2e_core.peer_count_ssot import parallel_active_test_count_ssot  # noqa: PLC0415

        return parallel_active_test_count_ssot() > 0
    except ImportError:
        return False


def _seed_health_wait_sec() -> float:
    raw = os.environ.get("MYRM_VERIFY_SEED_HEALTH_WAIT_SEC", "").strip()
    if raw:
        try:
            return max(5.0, min(SEED_HEALTH_WAIT_SEC, float(raw)))
        except ValueError:
            pass
    if _parallel_pressure_active():
        return SEED_PARALLEL_HEALTH_WAIT_SEC
    return SEED_HEALTH_WAIT_SEC


def _seed_spawn_timeout_sec() -> int:
    if not _parallel_pressure_active():
        return SEED_START_TIMEOUT_SEC
    raw = os.environ.get("MYRM_VERIFY_SEED_PARALLEL_WALL_SEC", "").strip()
    if raw:
        try:
            return max(15, int(float(raw)))
        except ValueError:
            pass
    return int(SEED_PARALLEL_SPAWN_WALL_SEC)


def _seed_cap_retry_backoff_sec() -> float:
    if _parallel_pressure_active():
        return SEED_PARALLEL_CAP_RETRY_BACKOFF_SEC
    return SEED_CAP_RETRY_BACKOFF_SEC


def _emit_seed_progress(*, started_mono: float, budget_sec: float, phase: str) -> None:
    elapsed = max(0.0, time.monotonic() - started_mono)
    sys.stderr.write(
        "E2E_VERIFY_SEED_WAIT: "
        f"phase={phase} elapsed={int(elapsed)}s budget={int(budget_sec)}s "
        "(parallel-safe; do not stop other pytest)\n"
    )
    sys.stderr.flush()


def _health_source_fingerprint(api_base: str) -> str:
    url = f"{api_base.rstrip('/')}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=3.0) as resp:  # noqa: S310
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return ""
    if not isinstance(raw, dict):
        return ""
    stack_epoch = raw.get("stack_epoch")
    if not isinstance(stack_epoch, dict):
        return ""
    source_fp = stack_epoch.get("source_fingerprint")
    return source_fp.strip() if isinstance(source_fp, str) else ""


def _wait_backend_healthy(api_base: str, state_dir: Path, *, deadline: float) -> bool:
    workspace_fp = _backend_source_fingerprint()
    started = time.monotonic()
    budget = max(0.0, deadline - started)
    last_emit = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now - last_emit >= SEED_PROGRESS_EMIT_INTERVAL_SEC:
            _emit_seed_progress(
                started_mono=started,
                budget_sec=budget,
                phase="health_epoch",
            )
            last_emit = now
        if not _health_ok(api_base):
            time.sleep(0.5)
            continue
        health_fp = _health_source_fingerprint(api_base)
        if workspace_fp and health_fp and health_fp == workspace_fp:
            return True
        stored_fp = _read_stored_fingerprint(state_dir)
        if stored_fp and workspace_fp and stored_fp == workspace_fp:
            return True
        time.sleep(0.5)
    return False


def _wait_backend_health_ok(api_base: str, *, deadline: float) -> bool:
    """Health-only wait — signoff direct start already wrote stack-epoch at boot."""
    while time.monotonic() < deadline:
        if _health_ok(api_base):
            return True
        time.sleep(0.5)
    return False


def _cap_reached_result(active: int) -> VerifyBackendSeedResult:
    return VerifyBackendSeedResult(
        ok=False,
        runtime_id="",
        api_base="",
        detail=(
            f"private backend cap reached ({active}/{LIVE_SHPOIB_MAX_CONCURRENT}); "
            "wait for pytest release or auto queue"
        ),
    )


def _is_retriable_seed_detail(detail: str) -> bool:
    lowered = detail.lower()
    return "cap reached" in lowered or "bootstrap slot unavailable" in lowered


def ensure_verify_backend_seed(*, monorepo: Path) -> VerifyBackendSeedResult:
    """Spawn backend-only runtime; retry once when SHPOIB cap is temporarily full."""
    last_result: VerifyBackendSeedResult | None = None
    for attempt in range(SEED_CAP_MAX_ATTEMPTS):
        active = _count_active_backend_only()
        if active >= LIVE_SHPOIB_MAX_CONCURRENT:
            last_result = _cap_reached_result(active)
            if attempt + 1 < SEED_CAP_MAX_ATTEMPTS:
                time.sleep(_seed_cap_retry_backoff_sec())
                continue
            return last_result
        result = _spawn_verify_backend_seed(monorepo=monorepo)
        if result.ok:
            return result
        last_result = result
        if attempt + 1 < SEED_CAP_MAX_ATTEMPTS and _is_retriable_seed_detail(
            result.detail
        ):
            time.sleep(_seed_cap_retry_backoff_sec())
            continue
        return result
    if last_result is not None:
        return last_result
    active = _count_active_backend_only()
    return _cap_reached_result(active)


def _mark_runtime_cleaning(runtime_id: str) -> None:
    from isolated_runtime.allocator import isolated_root  # noqa: PLC0415
    from isolated_runtime.registry import (  # noqa: PLC0415
        locked_registry,
        read_registry,
        write_registry,
    )

    with locked_registry(isolated_root()) as registry_path:
        records = read_registry(registry_path)
        if runtime_id in records:
            records[runtime_id]["phase"] = "cleaning"
            write_registry(registry_path, records)


def _spawn_verify_backend_seed(*, monorepo: Path) -> VerifyBackendSeedResult:
    root = monorepo.resolve()
    agent_root = root / "myrm-agent"
    if not (agent_root / "myrm-agent-server" / "run.py").is_file():
        return VerifyBackendSeedResult(
            ok=False,
            runtime_id="",
            api_base="",
            detail=f"missing agent root: {agent_root}",
        )

    _ensure_scripts_dev_importable(root)
    from isolated_runtime.allocator import (  # noqa: PLC0415
        allocate_runtime,
        claim_bootstrap_slot,
        heartbeat_runtime,
        runtime_environment,
    )
    from isolated_runtime.process import record_backend_process  # noqa: PLC0415
    from isolated_runtime.reaper import start_reaper_daemon  # noqa: PLC0415

    runtime_id = f"verify-api-{uuid.uuid4().hex[:12]}"
    owner_token = f"verify-{uuid.uuid4().hex}"
    owner_pid = os.getpid()

    try:
        record = allocate_runtime(
            runtime_id,
            agent_root,
            owner_pid=owner_pid,
            owner_token=owner_token,
            backend_only=True,
            reapable=True,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return VerifyBackendSeedResult(
            ok=False,
            runtime_id=runtime_id,
            api_base="",
            detail=str(exc),
        )

    start_reaper_daemon()
    environment = runtime_environment(record)
    api_base = environment["E2E_API_BASE"]
    dev_stack = root / "myrm-agent" / "scripts" / "dev" / "dev-stack.sh"
    ready_sh = root / "scripts" / "dev" / "ready.sh"

    if not claim_bootstrap_slot(runtime_id, owner_token, LIVE_SHPOIB_MAX_CONCURRENT):
        _mark_runtime_cleaning(runtime_id)
        return VerifyBackendSeedResult(
            ok=False,
            runtime_id=runtime_id,
            api_base=api_base.rstrip("/"),
            detail=(
                f"private backend bootstrap slot unavailable "
                f"(cap {LIVE_SHPOIB_MAX_CONCURRENT})"
            ),
        )

    process_env = os.environ.copy()
    process_env.update(environment)
    process_env.update(
        {
            "MYRM_SUPERVISOR_BYPASS": "1",
            "MYRM_WAVE_GATE_BYPASS": "1",
            "MYRM_BACKEND_HEALTH_WAIT_SEC": str(
                min(120, _seed_spawn_timeout_sec())
            ),
        }
    )

    spawn_wall = _seed_spawn_timeout_sec()
    harness_wall = min(60, spawn_wall)
    try:
        _emit_seed_progress(
            started_mono=time.monotonic(),
            budget_sec=float(spawn_wall),
            phase="harness",
        )
        harness = subprocess.run(
            ["bash", str(ready_sh), "--harness-only"],
            cwd=str(root),
            env=process_env,
            capture_output=True,
            text=True,
            timeout=harness_wall,
            check=False,
        )
        if harness.returncode != 0:
            detail = (harness.stderr or harness.stdout).strip()[-500:]
            raise RuntimeError(f"harness ensure failed: {detail}")

        _emit_seed_progress(
            started_mono=time.monotonic(),
            budget_sec=float(spawn_wall),
            phase="backend_only",
        )
        stack = subprocess.run(
            ["bash", str(dev_stack), "backend-only", "ensure"],
            cwd=str(root),
            env=process_env,
            capture_output=True,
            text=True,
            timeout=spawn_wall,
            check=False,
        )
        if stack.returncode != 0:
            detail = (stack.stderr or stack.stdout).strip()[-500:]
            raise RuntimeError(f"backend-only ensure failed: {detail}")

        record_backend_process(runtime_id, owner_token)

        state_dir = Path(record["stateDir"])
        deadline = time.monotonic() + _seed_health_wait_sec()
        if not _wait_backend_healthy(api_base, state_dir, deadline=deadline):
            raise RuntimeError("seed backend health or epoch match timeout")

        heartbeat_runtime(runtime_id, owner_token, phase="running")

    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        _mark_runtime_cleaning(runtime_id)
        return VerifyBackendSeedResult(
            ok=False,
            runtime_id=runtime_id,
            api_base=api_base,
            detail=str(exc),
            owner_token=owner_token,
        )

    return VerifyBackendSeedResult(
        ok=True,
        runtime_id=runtime_id,
        api_base=api_base.rstrip("/"),
        detail="seeded backend-only runtime for verify-api",
        owner_token=owner_token,
    )
