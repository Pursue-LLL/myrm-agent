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
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
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

logger = logging.getLogger(__name__)


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


def _agent_root_present(monorepo: Path) -> bool:
    """Whether ``monorepo`` actually hosts the server this seed would run.

    Gating *adoption* on the workspace, not just on ``_spawn_verify_backend_seed``,
    keeps the caller's contract honest: reusing a record the runtime registry
    happens to hold in a process whose workspace has no ``run.py`` would report a
    reachable backend for a tree that cannot serve it at all.
    """
    return (
        monorepo.resolve() / "myrm-agent" / "myrm-agent-server" / "run.py"
    ).is_file()


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
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _count_active_backend_only() -> int:
    """Active backend-only weight, using the same rules as slot admission.

    Mirrors ``claim_bootstrap_slot``'s weight accounting (ACTIVE_PHASES +
    ``owner_is_active``). Counting a different set — for instance excluding
    runtimes whose owner already exited — lets this pre-check report free
    capacity while admission is actually full, which surfaces to the caller as
    an unexplained cap failure instead of an honest queue signal.
    """
    from isolated_runtime.registry import (
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
    weight = 0
    for record in records.values():
        if not record.get("backendOnly"):
            continue
        if record["phase"] not in ACTIVE_PHASES:
            continue
        if owner_is_active(record):
            weight += int(record.get("resourceWeight", 1))
    return weight


def _parallel_pressure_active() -> bool:
    try:
        from e2e_core.peer_count_ssot import (
            parallel_active_test_count_ssot,
        )

        return parallel_active_test_count_ssot() > 1
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
    """Read the workspace fingerprint a live backend was built at.

    Returns ``""`` when the probe fails or the payload lacks one. Callers must
    treat that as *unknown*, never as a mismatch: an empty string never equals a
    real fingerprint, so a naive comparison would condemn a healthy backend
    merely because one request timed out.
    """
    url = f"{api_base.rstrip('/')}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=3.0) as resp:
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


def _resolve_js_runtime() -> str | None:
    for candidate_name in ("bun", "node"):
        override = os.getenv(f"MYRM_{candidate_name.upper()}_BIN", "").strip()
        if override and Path(override).is_file():
            return override
        found = shutil.which(candidate_name)
        if found:
            return found
        home = Path.home()
        candidates = [
            home / ".bun" / "bin" / candidate_name,
            Path(f"/opt/homebrew/bin/{candidate_name}"),
            Path(f"/usr/local/bin/{candidate_name}"),
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
    return None


def _load_env_test_vars(env_path: Path) -> dict[str, str]:
    if not env_path.is_file():
        return {}
    res: dict[str, str] = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" in line:
            k, v = line.split("=", 1)
            res[k.strip()] = v.strip().strip("'\"")
    return res


def _provider_ready(api_base: str) -> bool:
    url = f"{api_base.rstrip('/')}/api/v1/config/readiness"
    try:
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read())
            provider = data.get("provider") if isinstance(data, dict) else None
            return isinstance(provider, dict) and bool(provider.get("is_ready"))
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        ValueError,
        json.JSONDecodeError,
    ):
        return False


def _retrieval_ready(api_base: str) -> bool:
    url = f"{api_base.rstrip('/')}/api/v1/config/retrieval"
    try:
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read())
            val = data.get("value") if isinstance(data, dict) else data
            if isinstance(val, dict) and val.get("embeddingConfig"):
                cfg = val.get("embeddingConfig")
                return isinstance(cfg, dict) and bool(
                    cfg.get("apiKey") and cfg.get("model")
                )
            return False
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        ValueError,
        json.JSONDecodeError,
    ):
        return False


def ensure_verify_backend_providers(*, api_base: str, monorepo: Path) -> bool:
    """Ensure that the verify-api instance has seeded provider configs."""
    clean_base = api_base.rstrip("/")
    if _provider_ready(clean_base) and _retrieval_ready(clean_base):
        return True

    env_test = monorepo / "myrm-agent" / "myrm-agent-server" / ".env.test"
    if not env_test.is_file():
        env_test = monorepo / ".env.test"
    seed_script = (
        monorepo / "myrm-agent" / "scripts" / "dev" / "chrome-e2e-model-seed.mjs"
    )
    if not seed_script.is_file():
        return False

    js_bin = _resolve_js_runtime()
    if not js_bin:
        return False

    seed_env = os.environ.copy()
    seed_env.update(_load_env_test_vars(env_test))
    seed_env["E2E_API_BASE"] = clean_base

    try:
        proc = subprocess.run(
            [js_bin, str(seed_script)],
            cwd=str(seed_script.parent),
            env=seed_env,
            capture_output=True,
            text=True,
            timeout=25.0,
            check=False,
        )
        if proc.returncode != 0:
            return False
    except (OSError, subprocess.TimeoutExpired):
        return False

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if _provider_ready(clean_base) and _retrieval_ready(clean_base):
            return True
        time.sleep(0.5)
    return False


_VERIFY_RUNTIME_PREFIX = "verify-api-"


def _reapable_reuse_candidate(
    record: dict[str, object],
    *,
    owner_ttl_sec: float,
    active_phases: frozenset[str],
    warm_pool_ids: set[str] | None = None,
    owner_alive: bool | None = None,
) -> bool:
    """A backend-only runtime this session may adopt.

    Three independent guards apply:

    * Provenance — only ``verify-api-*`` ids, which this module and the SHPOIB
      warm pool create. The CLI's ``--persistent`` runtimes are also
      ``reapable=False``, but they belong to whatever session started them;
      adopting one would hijack a foreign backend and keep it alive via the
      heartbeat refresh below.
    * Pool ownership — ids still tracked by the SHPOIB warm pool are excluded, so
      its borrow/release lifecycle stays single-borrower.
    * Abandonment — the creating session must have stopped keeping the record
      alive. A dead ``ownerPid`` proves that. A heartbeat that lapsed past the
      owner TTL proves it too, and is what covers pid reuse, where the pid now
      belongs to an unrelated process. Either signal alone is sufficient.
    """
    if not record.get("backendOnly") or record.get("reapable") is not False:
        return False
    runtime_id = str(record.get("runtimeId", ""))
    if not runtime_id.startswith(_VERIFY_RUNTIME_PREFIX):
        return False
    if warm_pool_ids and runtime_id in warm_pool_ids:
        return False
    if record.get("phase") not in active_phases:
        return False
    heartbeat = record.get("heartbeatAt")
    if not isinstance(heartbeat, (int, float)):
        # A malformed heartbeat is *unknown*, never "infinitely lapsed". Folding
        # it into a lapsed value would satisfy `heartbeat_lapsed` and let a
        # record whose liveness we cannot read be adopted and kept alive by the
        # refresh — the same unknown-vs-negative mistake as the pid check below.
        return False
    heartbeat_lapsed = time.time() - heartbeat > owner_ttl_sec
    if owner_alive is not False and not heartbeat_lapsed:
        return False
    try:
        backend_port = int(record.get("backendPort") or 0)
    except (TypeError, ValueError):
        return False
    return backend_port > 0


def _warm_pool_owned_runtime_ids() -> set[str]:
    """Runtime ids the SHPOIB warm pool manages — reuse must leave those alone.

    The warm pool (``shpoib_warm_pool``) owns its own borrow/release lifecycle for
    LIVE chrome_e2e, and it spawns through the same ``verify-api-*`` allocator.
    Adopting a runtime it still tracks would put two borrowers on one backend and
    desynchronise its staleness clock, so those ids are excluded here.
    """
    try:
        from e2e_core.shpoib_warm_pool import _load_registry
    except ImportError:
        return set()
    try:
        registry = _load_registry()
    except (OSError, ValueError, RuntimeError):
        # Fail closed: an unreadable pool registry must not license adoption.
        return set()
    backends = registry.get("backends")
    if not isinstance(backends, dict):
        return set()
    return {
        str(entry.get("runtimeId") or "")
        for entry in backends.values()
        if isinstance(entry, dict)
    }


def _owner_alive(record: dict[str, object]) -> bool:
    """Whether the session that created this record may still be running.

    ``abandoned verify-api`` records were observed to stall capacity for the
    whole 1800s owner TTL after their creating process died — the window where a
    heartbeat is fresh but nothing will ever refresh it again. Checking the pid
    shortens that window to the time it takes the owner to exit.

    Reports *alive* whenever death cannot be proven: a missing or unparseable
    ``ownerPid`` is unknown, not dead. Folding it into the dead case (``None`` ->
    0 -> not alive) would let a record without a pid be adopted out from under a
    hot session and then kept alive by the heartbeat refresh — the exact
    hijacking this guard exists to prevent.
    """
    from isolated_runtime.registry import process_is_alive

    raw = record.get("ownerPid")
    if raw is None:
        return True
    try:
        pid = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True
    if pid <= 0:
        return True
    return process_is_alive(pid)


def _reusable_verify_backend() -> VerifyBackendSeedResult | None:
    """Adopt a live, orphaned backend-only runtime instead of spawning another.

    Every seed otherwise allocated a fresh ``verify-api-*`` record, so repeated
    verify-api calls accumulated persistent (``reapable=False``) runtimes whose
    weight saturated the active capacity and parked later tests in
    ``capacity_wait`` for the full wall clock.
    """
    from isolated_runtime.registry import (
        ACTIVE_PHASES,
        DEFAULT_OWNER_TTL_SEC,
        read_registry,
    )

    registry_path = _isolated_registry_root() / "registry.json"
    if not registry_path.is_file():
        return None
    try:
        records = read_registry(registry_path)
    except RuntimeError:
        return None
    warm_pool_ids = _warm_pool_owned_runtime_ids()
    candidates = sorted(
        (
            record
            for record in records.values()
            if _reapable_reuse_candidate(
                record,
                owner_ttl_sec=DEFAULT_OWNER_TTL_SEC,
                active_phases=ACTIVE_PHASES,
                warm_pool_ids=warm_pool_ids,
                owner_alive=_owner_alive(record),
            )
        ),
        key=lambda record: float(record["heartbeatAt"]),
        reverse=True,
    )
    best: VerifyBackendSeedResult | None = None
    for record in candidates:
        api_base = f"http://127.0.0.1:{int(record['backendPort'])}"
        if not _health_ok(api_base):
            _reclaim_unreusable_backend(record)
            continue
        fingerprint = _health_source_fingerprint(api_base)
        if not fingerprint:
            # The probe failed, so its stale-epoch verdict is unknown. The
            # record still counts against capacity, but reclaiming on a failed
            # read would tear down a session's backend on a mere timeout —
            # leave it to the owner-TTL reaper. This is the fail-closed half of
            # the fingerprint check below: an *empty* fingerprint can never equal
            # a real one, so treating it as a mismatch would free live backends.
            continue
        if fingerprint != _backend_source_fingerprint():
            _reclaim_unreusable_backend(record)
            continue
        result = VerifyBackendSeedResult(
            ok=True,
            runtime_id=str(record["runtimeId"]),
            api_base=api_base,
            detail="reused orphaned backend-only runtime for verify-api",
        )
        _adopt_orphan_heartbeat(record)
        if _provider_ready(api_base) and _retrieval_ready(api_base):
            return result
        best = best or result
    return best


def _reclaim_unreusable_backend(record: dict[str, object]) -> None:
    """Free an abandoned backend that no future borrower can reuse.

    A ``verify-api-*`` backend serves borrowers only while its source fingerprint
    matches the workspace epoch. Once the code moves on, an abandoned backend can
    never be adopted again — yet as a ``reapable=False`` runtime it keeps counting
    against active capacity until its 1800s owner TTL lapses. Measured: two such
    records held 2/4 of the cap for ~28 min after their owners exited, and a
    larger backlog parks later seeds in ``capacity_wait``.

    Only a *proven* dead owner is reclaimed. A lapsed heartbeat is left to the
    reaper (the pid may have been recycled, so it proves neither liveness nor
    death), and a missing or unparseable ``ownerPid`` is unknown rather than dead
    — acting on it could tear down a session that is still working.
    """
    from isolated_runtime.reaper import release_runtime
    from isolated_runtime.registry import process_is_alive

    raw = record.get("ownerPid")
    if raw is None:
        return
    try:
        owner_pid = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return
    if owner_pid <= 0 or process_is_alive(owner_pid):
        return
    runtime_id = str(record.get("runtimeId") or "")
    owner_token = str(record.get("ownerToken") or "")
    if not runtime_id or not owner_token:
        return
    try:
        release_runtime(runtime_id, owner_token)
        logger.info(
            "verify-api reclaimed unreusable backend %s (stale epoch, owner exited)",
            runtime_id,
        )
    except Exception:
        logger.warning("verify-api reclaim failed for %s", runtime_id, exc_info=True)


def _adopt_orphan_heartbeat(record: dict[str, object]) -> None:
    """Refresh the adopted runtime's heartbeat so the reaper spares it.

    The record is only adopted once its heartbeat has lapsed past the owner TTL,
    which is also the reaper's reclamation trigger. Touching the heartbeat
    immediately after adoption closes that window, so the runtime this session
    now depends on cannot be torn down underneath it.
    """
    from isolated_runtime.allocator import heartbeat_runtime

    try:
        heartbeat_runtime(str(record["runtimeId"]), str(record["ownerToken"]))
    except (OSError, RuntimeError, ValueError) as exc:
        # Adoption is still useful when the touch fails: the caller has a live
        # backend on a healthy port, and worst case the reaper reclaims it later.
        sys.stderr.write(
            f"MYRM_VERIFY_API_ADOPT_HEARTBEAT_FAILED: runtime={record['runtimeId']} "
            f"detail={exc}\n"
        )


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
    """Adopt an orphaned backend or spawn one; retry once when the cap is full."""
    # A workspace without the server must never adopt: the pre-existing
    # "missing agent root" contract has to hold before any registry lookup, or a
    # record left by another workspace makes a broken tree look serviceable.
    if not _agent_root_present(monorepo):
        return _spawn_verify_backend_seed(monorepo=monorepo)
    reused = _reusable_verify_backend()
    if reused is not None:
        return reused
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
    from isolated_runtime.allocator import isolated_root
    from isolated_runtime.registry import (
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
    from isolated_runtime.allocator import (
        allocate_runtime,
        claim_bootstrap_slot,
        heartbeat_runtime,
        runtime_environment,
    )
    from isolated_runtime.process import record_backend_process
    from isolated_runtime.reaper import start_reaper_daemon

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
            reapable=False,
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
            "MYRM_BACKEND_HEALTH_WAIT_SEC": str(min(120, _seed_spawn_timeout_sec())),
            "MYRM_BACKEND_ENSURING_HEALTH_SEC": str(
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
        ensure_verify_backend_providers(api_base=api_base, monorepo=root)

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
