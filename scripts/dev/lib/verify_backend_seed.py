"""On-demand backend-only isolated runtime for verify-api when epoch match is missing.

[INPUT]
- isolated_runtime_allocator.runtime_environment (POS: per-runtime env SSOT)
- dev_gate_contract.LIVE_SHPOIB_MAX_CONCURRENT (POS: private backend cap)
- runtime_identity._backend_source_fingerprint (POS: workspace epoch SSOT)

[OUTPUT]
- ensure_verify_backend_seed(): spawn ephemeral backend-only runtime at workspace epoch

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

from dev_gate_contract import LIVE_SHPOIB_MAX_CONCURRENT
from runtime_identity import _backend_source_fingerprint

SEED_START_TIMEOUT_SEC: Final[int] = 180
SEED_HEALTH_WAIT_SEC: Final[float] = 120.0


@dataclass(frozen=True, slots=True)
class VerifyBackendSeedResult:
    ok: bool
    runtime_id: str
    api_base: str
    detail: str


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
    return Path.home() / ".local/state/myrm-isolated"


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
    from isolated_runtime_registry import (  # noqa: PLC0415
        ACTIVE_PHASES,
        owner_is_active,
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
        if owner_is_active(record):
            count += 1
    return count


def _wait_backend_healthy(api_base: str, state_dir: Path, *, deadline: float) -> bool:
    workspace_fp = _backend_source_fingerprint()
    while time.monotonic() < deadline:
        if not _health_ok(api_base):
            time.sleep(0.5)
            continue
        stored_fp = _read_stored_fingerprint(state_dir)
        if stored_fp and workspace_fp and stored_fp == workspace_fp:
            return True
        time.sleep(0.5)
    return False


def ensure_verify_backend_seed(*, monorepo: Path) -> VerifyBackendSeedResult:
    root = monorepo.resolve()
    _ensure_scripts_dev_importable(root)
    from isolated_runtime_allocator import (  # noqa: PLC0415
        allocate_runtime,
        runtime_environment,
    )
    from isolated_runtime_process import record_backend_process  # noqa: PLC0415
    from isolated_runtime_reaper import start_reaper_daemon  # noqa: PLC0415
    from isolated_runtime_registry import locked_registry, read_registry, write_registry  # noqa: PLC0415
    from isolated_runtime_allocator import isolated_root, heartbeat_runtime  # noqa: PLC0415

    active = _count_active_backend_only()
    if active >= LIVE_SHPOIB_MAX_CONCURRENT:
        return VerifyBackendSeedResult(
            ok=False,
            runtime_id="",
            api_base="",
            detail=(
                f"private backend cap reached ({active}/{LIVE_SHPOIB_MAX_CONCURRENT}); "
                "wait for pytest release or auto queue"
            ),
        )

    agent_root = root / "myrm-agent"
    if not (agent_root / "myrm-agent-server" / "run.py").is_file():
        return VerifyBackendSeedResult(
            ok=False,
            runtime_id="",
            api_base="",
            detail=f"missing agent root: {agent_root}",
        )

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

    process_env = os.environ.copy()
    process_env.update(environment)
    process_env.update(
        {
            "MYRM_SUPERVISOR_BYPASS": "1",
            "MYRM_WAVE_GATE_BYPASS": "1",
            "MYRM_BACKEND_HEALTH_WAIT_SEC": "120",
        }
    )

    try:
        harness = subprocess.run(
            ["bash", str(ready_sh), "--harness-only"],
            cwd=str(root),
            env=process_env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if harness.returncode != 0:
            detail = (harness.stderr or harness.stdout).strip()[-500:]
            raise RuntimeError(f"harness ensure failed: {detail}")

        stack = subprocess.run(
            ["bash", str(dev_stack), "backend-only", "ensure"],
            cwd=str(root),
            env=process_env,
            capture_output=True,
            text=True,
            timeout=SEED_START_TIMEOUT_SEC,
            check=False,
        )
        if stack.returncode != 0:
            detail = (stack.stderr or stack.stdout).strip()[-500:]
            raise RuntimeError(f"backend-only ensure failed: {detail}")

        record_backend_process(runtime_id, owner_token)
        heartbeat_runtime(runtime_id, owner_token, phase="running")

        state_dir = Path(record["stateDir"])
        deadline = time.monotonic() + SEED_HEALTH_WAIT_SEC
        if not _wait_backend_healthy(api_base, state_dir, deadline=deadline):
            raise RuntimeError("seed backend health or epoch match timeout")

    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        with locked_registry(isolated_root()) as registry_path:
            records = read_registry(registry_path)
            if runtime_id in records:
                records[runtime_id]["phase"] = "cleaning"
                write_registry(registry_path, records)
        return VerifyBackendSeedResult(
            ok=False,
            runtime_id=runtime_id,
            api_base=api_base,
            detail=str(exc),
        )

    return VerifyBackendSeedResult(
        ok=True,
        runtime_id=runtime_id,
        api_base=api_base.rstrip("/"),
        detail="seeded backend-only runtime for verify-api",
    )
