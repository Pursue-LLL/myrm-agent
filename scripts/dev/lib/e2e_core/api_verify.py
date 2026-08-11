"""Resolve the correct dev API base for Agent/server verification during parallel E2E.

Verification Plane SSOT: route API checks to a backend whose stored stack-epoch
source_fingerprint matches the workspace fingerprint. Fail-closed when no match.

[INPUT]
- runtime_identity._backend_source_fingerprint (workspace FP SSOT)
- isolated_runtime.registry (private backend ports + stateDir)
- stack-epoch.json per backend state dir (stored FP SSOT)
- stack_mutation_policy (pending drift, active lease count)

[OUTPUT]
- resolve_e2e_api_context / resolve_verify_api_base
- CLI: context-json, context-human, launch-check, verify-api (proxy curl; optional --ensure-backend seed)

[POS]
Agent-facing SSOT for API verification — eliminates stale :8080 / stale private pool false results.
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from runtime_identity import _backend_source_fingerprint
from stack_mutation_policy import (
    _default_state_dir,
    decide_drift_heal,
    pending_drift_exists,
    read_pending_drift,
)

SHARED_DEFAULT_PORT: Final[int] = 8080
PRIVATE_PORT_SCAN_START: Final[int] = 18080
PRIVATE_PORT_SCAN_END: Final[int] = 18120
HEALTH_PATHS: Final[tuple[str, ...]] = ("/api/v1/health", "/health")
HEALTH_PROBE_TIMEOUT_SEC: Final[float] = 2.0
PORT_SCAN_PROBE_TIMEOUT_SEC: Final[float] = 0.5
DEFAULT_CONTEXT_PROBE_WALL_SEC: Final[float] = 15.0
# The supervisor watchdog publishes a live probe every 30s. Allow one
# watchdog interval plus scheduling jitter, but never trust an older snapshot.
SUPERVISOR_STATE_MAX_AGE_SEC: Final[float] = 45.0
_CONTEXT_PROBE_STARTED_MONO: float | None = None
AGENT_NEVER_SAY: Final[str] = (
    "停其他pytest|只跑一个E2E|kill其他pytest|先清wave|先清wave/tab|"
    "共享只能N个session|停止并行测试|kill wave"
)
CHROME_AGENT_MCP_PORT: Final[int] = 9410
CHROME_E2E_HARNESS_PORT: Final[int] = 9333
CHROME_INSTANCE_ISOLATION_RULE: Final[str] = (
    "CHROME_INSTANCE_ISOLATION: chrome_e2e/parallel E2E must use ./myrm test harness "
    f"→ ChromeE2E :{CHROME_E2E_HARNESS_PORT}; do NOT call chrome-devtools MCP "
    f"(:{CHROME_AGENT_MCP_PORT} ChromeAgent). ChromeAgent is for URL-extraction Agent tasks only."
)
_CURL_STATUS_MARKER: Final[str] = "\n__MYRM_HTTP_STATUS__:"
_LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "localhost", "::1"})


def browser_isolation_payload() -> dict[str, object]:
    """Structured Chrome instance contract for Agent vs E2E (SSOT for e2e-context json)."""
    return {
        "agentMcp": {
            "port": CHROME_AGENT_MCP_PORT,
            "profile": "ChromeAgent",
            "allowedTasks": ["提取网址"],
            "forbiddenDuringE2e": "chrome-devtools MCP",
        },
        "e2eHarness": {
            "port": CHROME_E2E_HARNESS_PORT,
            "profile": "ChromeE2E",
            "entry": "./myrm test -m chrome_e2e",
        },
    }


def epoch_drift_attach_cap_sec(
    *,
    blocked: bool,
    epoch_match: bool,
    drift_pending: bool,
    active_leases: int,
) -> int:
    """SHARED attach drift window: seconds a new attach may wait for epoch match.

    Returns 0 when no drift cap applies (attach waits on the monotonic BOOTSTRAP
    budget). Returns >0 when the shared backend is blocked on a stale epoch.

    When drift is pending while parallel tests hold leases, SMP deliberately
    defers the shared reload (do-not-interrupt contract). A new attach must wait
    for the lease-release window plus reload instead of failing on the fixed
    base cap, so the cap scales with active leases (aligned with the BOOTSTRAP
    budget `base + leases*45`). This turns a "120s wait-then-FAIL" into a
    bounded, parallel-aware wait.
    """
    if not (blocked and not epoch_match):
        return 0
    base_raw = os.environ.get("MYRM_E2E_EPOCH_DRIFT_ATTACH_CAP_SEC", "").strip()
    base = int(base_raw) if base_raw.isdigit() else 120
    if drift_pending and active_leases > 0:
        leases = max(active_leases, 0)
        per_lease_raw = os.environ.get(
            "MYRM_E2E_EPOCH_DRIFT_ATTACH_PER_LEASE_SEC", ""
        ).strip()
        per_lease = int(per_lease_raw) if per_lease_raw.isdigit() else 45
        return base + leases * per_lease
    return base


@dataclass(frozen=True, slots=True)
class BackendCandidate:
    api_base: str
    port: int
    source: str
    state_dir: str
    stored_fingerprint: str
    workspace_fingerprint: str
    epoch_match: bool
    health_ok: bool
    epoch: int | None
    health_observable: bool = True


@dataclass(frozen=True, slots=True)
class E2eApiContext:
    verify_api_base: str
    shared_api_base: str
    workspace_fingerprint: str
    epoch_match: bool
    drift_pending: bool
    active_leases: int
    drift_action: str
    source: str
    agent_rule: str
    blocked: bool
    blocked_reason: str
    candidates: tuple[BackendCandidate, ...]


def _shared_epoch_match(ctx: E2eApiContext) -> bool:
    """Whether the shared UI backend is healthy and runs the workspace epoch."""
    shared = [candidate for candidate in ctx.candidates if candidate.source == "shared"]
    if shared:
        return any(candidate.health_ok and candidate.epoch_match for candidate in shared)
    # Empty candidates are used by focused unit fixtures. A real non-empty set
    # without a shared candidate means only API/private verification is ready.
    return ctx.epoch_match if not ctx.candidates else False


def monorepo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def shared_api_base() -> str:
    explicit = os.environ.get("MYRM_SHARED_E2E_API_BASE", "").strip()
    if explicit:
        return explicit.rstrip("/")
    port_raw = os.environ.get("MYRM_BACKEND_PORT", str(SHARED_DEFAULT_PORT)).strip()
    port = int(port_raw) if port_raw.isdigit() else SHARED_DEFAULT_PORT
    return f"http://127.0.0.1:{port}"


def _real_user_home() -> Path:
    """Resolve the real login user home, bypassing sandboxed HOME (e.g.
    Cursor's ~/.cursor2) so dev state stays on the user's real data dir."""
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError):
        return Path.home()


def shared_dev_state_dir() -> Path:
    override = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    if override:
        return Path(override).resolve()
    return _real_user_home() / ".local/state/myrm-dev"


def isolated_registry_root() -> Path:
    override = os.environ.get("MYRM_ISOLATED_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return _real_user_home() / ".local/state/myrm-isolated"


def workspace_backend_fingerprint() -> str:
    return _backend_source_fingerprint()


def _scripts_dev_dir() -> Path:
    root = monorepo_root()
    # The dev gate lives in the myrm-agent product repository.  Keep a
    # root-level fallback for older checkouts, but select the directory that
    # actually owns the wave_orchestrator package so lazy imports cannot split
    # state or fail only in context-json diagnostics.
    candidates = (
        root / "myrm-agent" / "scripts" / "dev",
        root / "scripts" / "dev",
    )
    return next(
        (candidate for candidate in candidates if (candidate / "wave_orchestrator").is_dir()),
        candidates[0],
    )


def _ensure_scripts_dev_importable() -> None:
    # The dev domain is split across two locations: e2e_core and dev_gate live
    # under myrm-agent/scripts/dev, while isolated_runtime remains a root-level
    # domain package. Inject both so lazy imports resolve regardless of which
    # package owns wave_orchestrator.
    root = monorepo_root()
    for dev_dir in (
        str(root / "myrm-agent" / "scripts" / "dev"),
        str(root / "scripts" / "dev"),
    ):
        if dev_dir not in sys.path:
            sys.path.insert(0, dev_dir)


def _read_stored_epoch(state_dir: Path) -> tuple[int | None, str]:
    epoch_file = state_dir / "stack-epoch.json"
    if not epoch_file.is_file():
        return None, ""
    try:
        raw = json.loads(epoch_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, ""
    if not isinstance(raw, dict):
        return None, ""
    epoch_raw = raw.get("epoch")
    epoch = epoch_raw if isinstance(epoch_raw, int) and epoch_raw >= 1 else None
    stored_fp = raw.get("source_fingerprint")
    if not isinstance(stored_fp, str):
        stored_fp = ""
    return epoch, stored_fp.strip()


def _context_probe_wall_sec() -> float:
    raw = os.environ.get("E2E_CONTEXT_PROBE_WALL_SEC", "").strip()
    if not raw:
        return DEFAULT_CONTEXT_PROBE_WALL_SEC
    try:
        parsed = float(raw)
    except ValueError:
        return DEFAULT_CONTEXT_PROBE_WALL_SEC
    # Never disable the probe wall: port scan without a cap caused 510s pytest hangs.
    return parsed if parsed > 0 else DEFAULT_CONTEXT_PROBE_WALL_SEC


def _begin_context_probe_wall() -> None:
    global _CONTEXT_PROBE_STARTED_MONO
    wall = _context_probe_wall_sec()
    _CONTEXT_PROBE_STARTED_MONO = time.monotonic() if wall > 0 else None


def _reset_context_probe_wall() -> None:
    global _CONTEXT_PROBE_STARTED_MONO
    _CONTEXT_PROBE_STARTED_MONO = None


def _probe_wall_remaining_sec() -> float | None:
    if _CONTEXT_PROBE_STARTED_MONO is None:
        return None
    elapsed = time.monotonic() - _CONTEXT_PROBE_STARTED_MONO
    return max(0.0, _context_probe_wall_sec() - elapsed)


def _bounded_probe_timeout(requested_sec: float) -> float:
    remaining = _probe_wall_remaining_sec()
    if remaining is None:
        return requested_sec
    if remaining <= 0:
        return 0.0
    return min(requested_sec, remaining)


def _api_health_probe(
    api_base: str,
    timeout_sec: float = HEALTH_PROBE_TIMEOUT_SEC,
    *,
    allow_retry: bool = True,
) -> bool | None:
    timeout_sec = _bounded_probe_timeout(timeout_sec)
    if timeout_sec <= 0:
        return False
    base = api_base.rstrip("/")
    permission_denied = False
    for attempt in range(2 if allow_retry else 1):
        if attempt > 0:
            # High-load transient failures (accept/read timeouts, ECONNRESET) are
            # common; one fast retry avoids misreading a healthy backend (§26.28-C).
            time.sleep(0.2)
            timeout_sec = _bounded_probe_timeout(timeout_sec)
            if timeout_sec <= 0:
                return False
        for path in HEALTH_PATHS:
            url = f"{base}{path}"
            try:
                with urllib.request.urlopen(
                    url, timeout=timeout_sec
                ) as resp:
                    if 200 <= resp.status < 300:
                        return True
            except urllib.error.URLError as exc:
                reason = exc.reason
                if isinstance(reason, ConnectionRefusedError | ConnectionResetError):
                    continue
                if _curl_loopback_get(url, timeout_sec=timeout_sec) is not None:
                    return True
                permission_denied = permission_denied or isinstance(
                    reason, PermissionError
                )
            except (TimeoutError, OSError) as exc:
                if _curl_loopback_get(url, timeout_sec=timeout_sec) is not None:
                    return True
                permission_denied = permission_denied or isinstance(
                    exc, PermissionError
                )
    return None if permission_denied else False


def _api_health_ok(
    api_base: str,
    timeout_sec: float = HEALTH_PROBE_TIMEOUT_SEC,
    *,
    allow_retry: bool = True,
) -> bool:
    """Compatibility predicate; observation code must use the tri-state probe."""
    return (
        _api_health_probe(
            api_base,
            timeout_sec=timeout_sec,
            allow_retry=allow_retry,
        )
        is True
    )


def _supervisor_state_health(state_dir: Path) -> bool | None:
    """Use a fresh supervisor live-probe snapshot when loopback is sandboxed.

    ``stack_supervisor`` writes this file from pid + port + HTTP probes. The
    E2E context command can run where Python and curl are denied loopback
    access, so a fresh live snapshot must not be misclassified as UNKNOWN.
    Stale or malformed snapshots remain UNKNOWN; this is not a warmth bypass.
    """
    if state_dir == Path() or not state_dir.is_absolute():
        return None
    path = state_dir / "supervisor-state.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    updated_at = payload.get("updated_at")
    if not isinstance(updated_at, str):
        return None
    try:
        observed_at = datetime.fromisoformat(updated_at)
    except ValueError:
        return None
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    age_sec = time.time() - observed_at.timestamp()
    if age_sec < -5.0 or age_sec > SUPERVISOR_STATE_MAX_AGE_SEC:
        return None
    backend_process = payload.get("backend_process")
    api_http_ok = payload.get("api_http_ok")
    if not isinstance(backend_process, str) or not isinstance(api_http_ok, bool):
        return None
    return backend_process == "alive" and api_http_ok


def _curl_loopback_get(url: str, *, timeout_sec: float) -> str | None:
    """Read a loopback URL when the Agent sandbox denies Python socket access."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _LOOPBACK_HOSTS:
        return None
    bounded_timeout = max(0.1, timeout_sec)
    try:
        proc = subprocess.run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--max-time",
                f"{bounded_timeout:g}",
                "--write-out",
                f"{_CURL_STATUS_MARKER}%{{http_code}}",
                url,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=bounded_timeout + 1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    body, marker, status_raw = proc.stdout.rpartition(_CURL_STATUS_MARKER)
    if proc.returncode != 0 or marker != _CURL_STATUS_MARKER:
        return None
    try:
        status = int(status_raw.strip())
    except ValueError:
        return None
    return body if 200 <= status < 300 else None


def _read_health_stack_epoch(api_base: str) -> tuple[int | None, str]:
    url = f"{api_base.rstrip('/')}/api/v1/health"
    try:
        with urllib.request.urlopen(
            url, timeout=HEALTH_PROBE_TIMEOUT_SEC
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
        ValueError,
    ):
        payload_text = _curl_loopback_get(
            url,
            timeout_sec=HEALTH_PROBE_TIMEOUT_SEC,
        )
        if payload_text is None:
            return None, ""
        try:
            payload = json.loads(payload_text)
        except (json.JSONDecodeError, ValueError):
            return None, ""
    if not isinstance(payload, dict):
        return None, ""
    stack_epoch = payload.get("stack_epoch")
    if not isinstance(stack_epoch, dict):
        return None, ""
    epoch_raw = stack_epoch.get("epoch")
    epoch = epoch_raw if isinstance(epoch_raw, int) and epoch_raw >= 1 else None
    stored_fp = stack_epoch.get("source_fingerprint")
    if not isinstance(stored_fp, str):
        stored_fp = ""
    return epoch, stored_fp.strip()


def _resolve_candidate_fingerprint(
    *,
    api_base: str,
    state_dir: Path,
    health_ok: bool,
) -> tuple[int | None, str]:
    epoch, stored_fp = _read_stored_epoch(state_dir)
    if stored_fp:
        return epoch, stored_fp
    if health_ok:
        return _read_health_stack_epoch(api_base)
    return epoch, stored_fp


def _epoch_matches(*, stored_fp: str, workspace_fp: str) -> bool:
    if not workspace_fp:
        return False
    if not stored_fp:
        return False
    return stored_fp == workspace_fp


def _port_from_api_base(api_base: str) -> int:
    explicit = os.environ.get("MYRM_BACKEND_PORT", "").strip()
    if api_base.rstrip("/").endswith(f":{SHARED_DEFAULT_PORT}") and explicit.isdigit():
        return int(explicit)
    tail = api_base.rsplit(":", 1)[-1]
    if tail.isdigit():
        return int(tail)
    return SHARED_DEFAULT_PORT


def _enumerate_registry_candidates() -> list[tuple[str, int, str, str]]:
    _ensure_scripts_dev_importable()
    from isolated_runtime.registry import ACTIVE_PHASES, read_registry

    registry_path = isolated_registry_root() / "registry.json"
    if not registry_path.is_file():
        return []
    try:
        records = read_registry(registry_path)
    except RuntimeError:
        return []
    found: list[tuple[str, int, str, str]] = []
    for record in records.values():
        if record["phase"] not in ACTIVE_PHASES:
            continue
        port = record["backendPort"]
        state_dir = record["stateDir"]
        api_base = f"http://127.0.0.1:{port}"
        found.append((api_base, port, state_dir, "isolated_registry"))
    return sorted(found, key=lambda item: item[1])


def _enumerate_port_scan_candidates(
    known_ports: set[int],
) -> list[tuple[str, int, str, str]]:
    remaining = _probe_wall_remaining_sec()
    if remaining is not None and remaining <= 0:
        return []
    found: list[tuple[str, int, str, str]] = []
    for port in range(PRIVATE_PORT_SCAN_START, PRIVATE_PORT_SCAN_END + 1):
        if port in known_ports:
            continue
        if _probe_wall_remaining_sec() is not None and _probe_wall_remaining_sec() <= 0:
            break
        api_base = f"http://127.0.0.1:{port}"
        if _api_health_ok(
            api_base, timeout_sec=PORT_SCAN_PROBE_TIMEOUT_SEC, allow_retry=False
        ):
            found.append((api_base, port, "", "port_scan"))
    return found


def _should_skip_port_scan_under_parallel_block(
    candidates: list[BackendCandidate],
) -> bool:
    """Port scan cannot mint workspace epoch under active leases — avoid 41× probe burn."""
    from e2e_lease_liveness import (
        load_wave_snapshot,
        shared_effective_lease_count,
    )

    if shared_effective_lease_count(load_wave_snapshot()) <= 0:
        return False
    if any(item.epoch_match and item.health_ok for item in candidates):
        return False
    shared = next((item for item in candidates if item.source == "shared"), None)
    if shared is None:
        return True
    return not shared.epoch_match


def _build_candidates_from_specs(
    specs: list[tuple[str, int, str, str]],
    *,
    workspace_fp: str,
) -> list[BackendCandidate]:
    candidates: list[BackendCandidate] = []
    for api_base, port, state_dir_raw, source in specs:
        state_dir = Path(state_dir_raw) if state_dir_raw else Path()
        health_result = _api_health_probe(api_base)
        supervisor_health = _supervisor_state_health(state_dir)
        if supervisor_health is not None:
            # A probe can race a supervisor restart or be denied by the
            # sandbox. Prefer the fresher supervisor live-probe result; stale
            # snapshots remain unavailable and cannot affect the decision.
            health_result = supervisor_health
        health_ok = health_result is True
        epoch, stored_fp = _resolve_candidate_fingerprint(
            api_base=api_base,
            state_dir=state_dir,
            health_ok=health_ok,
        )
        epoch_match = _epoch_matches(stored_fp=stored_fp, workspace_fp=workspace_fp)
        candidates.append(
            BackendCandidate(
                api_base=api_base.rstrip("/"),
                port=port,
                source=source,
                state_dir=state_dir_raw,
                stored_fingerprint=stored_fp,
                workspace_fingerprint=workspace_fp,
                epoch_match=epoch_match,
                health_ok=health_ok,
                epoch=epoch,
                health_observable=health_result is not None,
            )
        )
    return candidates


def enumerate_backend_candidates(*, workspace_fp: str) -> list[BackendCandidate]:
    specs: list[tuple[str, int, str, str]] = []
    pinned_api = os.environ.get("E2E_API_BASE", "").strip().rstrip("/")
    if pinned_api:
        pinned_port = _port_from_api_base(pinned_api)
        pinned_state = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
        specs.append(
            (
                pinned_api,
                pinned_port,
                pinned_state or str(shared_dev_state_dir()),
                "pinned_e2e_api_base",
            )
        )
    shared = shared_api_base()
    shared_port = _port_from_api_base(shared)
    if not pinned_api or pinned_api.rstrip("/") != shared.rstrip("/"):
        specs.append((shared, shared_port, str(shared_dev_state_dir()), "shared"))
    specs.extend(_enumerate_registry_candidates())

    candidates = _build_candidates_from_specs(specs, workspace_fp=workspace_fp)
    if any(item.epoch_match and item.health_ok for item in candidates):
        return candidates

    if _should_skip_port_scan_under_parallel_block(candidates):
        return candidates

    known_ports = {port for _, port, _, _ in specs}
    specs.extend(_enumerate_port_scan_candidates(known_ports))
    return _build_candidates_from_specs(specs, workspace_fp=workspace_fp)


def _select_verify_candidate(
    candidates: list[BackendCandidate],
    *,
    active_leases: int,
) -> BackendCandidate | None:
    matching = [item for item in candidates if item.epoch_match and item.health_ok]
    if not matching:
        return None

    def sort_key(item: BackendCandidate) -> tuple[int, int, int]:
        private_bias = 0 if item.source != "shared" else 1
        lease_private_bias = private_bias if active_leases > 0 else 0
        epoch_rank = item.epoch if item.epoch is not None else 0
        return (lease_private_bias, -epoch_rank, item.port)

    return min(matching, key=sort_key)


def _blocked_reason(
    *,
    candidates: list[BackendCandidate],
    active_leases: int,
    drift_pending: bool,
    workspace_fp: str,
) -> str:
    healthy = [item for item in candidates if item.health_ok]
    shared_candidates = [item for item in candidates if item.source == "shared"]
    observation_candidates = shared_candidates or candidates
    if observation_candidates and any(
        not item.health_observable for item in observation_candidates
    ):
        return "backend health observability unavailable; preserve runtime and peers"
    if not workspace_fp:
        return "workspace backend source_fingerprint unavailable"
    if not healthy:
        return "no healthy backend reachable; attach crash recovery required"
    stale = [item for item in healthy if not item.epoch_match]
    if stale and active_leases > 0:
        return (
            f"no backend at workspace epoch ({active_leases} active leases; "
            "workspace backend code requires PRIVATE epoch)"
        )
    if stale and drift_pending:
        return "pending workspace backend drift; PRIVATE epoch required"
    if stale:
        return "healthy shared backend is pinned to a deployed epoch; PRIVATE epoch required for workspace backend code"
    return "no verify target selected"


def _build_context_from_resolution(
    *,
    verify: BackendCandidate | None,
    candidates: list[BackendCandidate],
    shared: str,
    workspace_fp: str,
    drift_pending: bool,
    active_leases: int,
    drift_action: str,
) -> E2eApiContext:
    if verify is not None:
        if verify.source == "shared":
            rule = (
                "shared backend is healthy and runs the workspace epoch; SHARED browser "
                "sessions may launch after launch-check; do not restart or stop peers"
            )
        else:
            rule = (
                "verify-api routed to an epoch-matched isolated backend; this proves "
                "API-only readiness, not SHARED browser readiness because shared :3000 "
                "always proxies :8080; follow next_action and do not stop peers"
            )
        return E2eApiContext(
            verify_api_base=verify.api_base,
            shared_api_base=shared.rstrip("/"),
            workspace_fingerprint=workspace_fp,
            epoch_match=True,
            drift_pending=drift_pending,
            active_leases=active_leases,
            drift_action=drift_action,
            source=verify.source,
            agent_rule=rule,
            blocked=False,
            blocked_reason="",
            candidates=tuple(candidates),
        )

    blocked_reason = _blocked_reason(
        candidates=candidates,
        active_leases=active_leases,
        drift_pending=drift_pending,
        workspace_fp=workspace_fp,
    )
    fallback_base = shared.rstrip("/")
    for item in candidates:
        if item.source == "shared" and item.health_ok:
            fallback_base = item.api_base
            break
    healthy = [item for item in candidates if item.health_ok]
    stale = [item for item in healthy if not item.epoch_match]
    shared_candidates = [item for item in candidates if item.source == "shared"]
    observation_candidates = shared_candidates or candidates
    unobservable = [
        item for item in observation_candidates if not item.health_observable
    ]
    if unobservable:
        action = (
            "Preserve the runtime and peers; rerun through the normal ./myrm test "
            "harness where loopback health is observable; never infer a crash or restart"
        )
    elif not healthy:
        action = (
            "Run ./myrm ready --attach --chrome for single-flight backend-only crash heal, "
            "then reread ./myrm e2e-context json"
        )
    elif stale:
        action = (
            "Do not promote or restart shared :8080 from a browser session; the node "
            "planner must declare PRIVATE for workspace backend code, while tests targeting "
            "the deployed shared epoch remain SHARED; do not change mode after collect"
        )
    else:
        action = "Follow the node planner result and preserve the deployed shared epoch"
    rule = (
        f"BLOCKED: {blocked_reason}. {action}; "
        "do not curl shared :8080 or stop other tests."
    )
    return E2eApiContext(
        verify_api_base=fallback_base,
        shared_api_base=shared.rstrip("/"),
        workspace_fingerprint=workspace_fp,
        epoch_match=False,
        drift_pending=drift_pending,
        active_leases=active_leases,
        drift_action=drift_action,
        source="blocked",
        agent_rule=rule,
        blocked=True,
        blocked_reason=blocked_reason,
        candidates=tuple(candidates),
    )


def resolve_e2e_api_context(
    *,
    monorepo: Path | None = None,
    state_dir: Path | None = None,
    retry_after_apply: bool = True,
) -> E2eApiContext:
    try:
        return _resolve_e2e_api_context_impl(
            monorepo=monorepo,
            state_dir=state_dir,
            retry_after_apply=retry_after_apply,
        )
    finally:
        _reset_context_probe_wall()


def _resolve_e2e_api_context_impl(
    *,
    monorepo: Path | None = None,
    state_dir: Path | None = None,
    retry_after_apply: bool = True,
) -> E2eApiContext:
    resolved_state = state_dir or _default_state_dir()
    shared = shared_api_base()
    workspace_fp = workspace_backend_fingerprint()
    from e2e_lease_liveness import (
        load_wave_snapshot,
        shared_effective_lease_count,
    )

    wave_snapshot = load_wave_snapshot()
    active_leases = shared_effective_lease_count(wave_snapshot)

    # P0-A: drift apply removed from observation path — Coordinator daemon owns mutation.
    # Here we only read drift state for context reporting.
    drift_pending = pending_drift_exists(resolved_state)
    drift_action = decide_drift_heal(
        active_leases=active_leases,
        drift_pending=drift_pending,
    ).value

    # Probe wall starts AFTER workspace fingerprint calc (git status on a large
    # monorepo under high load can exhaust a 15s budget by itself, starving
    # health probes → healthy backends misread as unreachable → BLOCKED, §26.28-C).
    _begin_context_probe_wall()
    candidates = enumerate_backend_candidates(workspace_fp=workspace_fp)
    verify = _select_verify_candidate(candidates, active_leases=active_leases)

    pending = read_pending_drift(resolved_state)
    if pending is not None and drift_pending:
        _ = pending.reason

    return _build_context_from_resolution(
        verify=verify,
        candidates=candidates,
        shared=shared,
        workspace_fp=workspace_fp,
        drift_pending=drift_pending,
        active_leases=active_leases,
        drift_action=drift_action,
    )


def resolve_verify_api_base() -> str:
    ctx = resolve_e2e_api_context()
    if ctx.blocked:
        return ctx.shared_api_base
    return ctx.verify_api_base


def _candidate_to_dict(candidate: BackendCandidate) -> dict[str, object]:
    return asdict(candidate)


def _mux_context_fields() -> dict[str, object]:
    from dev_gate_contract import MUX_COLD_ATTACH_SLOTS
    from mux_upstream_admission import read_mux_cold_attach_status

    snapshot_available = True
    try:
        mux = read_mux_cold_attach_status()
    except (OSError, PermissionError):
        snapshot_available = False
        mux = {
            "active": 0,
            "maxSlots": MUX_COLD_ATTACH_SLOTS,
            "saturated": False,
            "handProbeAllowed": True,
        }
    return {
        "muxColdAttachActive": mux["active"],
        "muxColdAttachMax": mux["maxSlots"],
        "muxColdAttachSaturated": mux["saturated"],
        "muxHandProbeAllowed": mux["handProbeAllowed"],
        "muxSnapshotAvailable": snapshot_available,
    }


from e2e_parallel_status import (
    cap_headroom_fields as _cap_headroom_fields,
)
from e2e_parallel_status import (
    format_cap_headroom_human as _format_cap_headroom_human,
)
from e2e_parallel_status import (
    format_queue_human as _format_queue_human,
)
from e2e_parallel_status import (
    load_parallel_runtime_snapshot as _load_parallel_runtime_snapshot,  # noqa: F401
)
from e2e_parallel_status import (
    resolve_cap_headroom_active_test_count as _resolve_cap_headroom_active_test_count,
)
from e2e_parallel_status import (
    resolve_parallel_runtime_snapshot as _resolve_parallel_runtime_snapshot,
)


def _load_orchestrator_observability() -> tuple[dict[str, object], dict[str, object]]:
    try:
        from browser_orchestrator import (
            browser_orchestrator_snapshot,
            orchestrator_queue_observability,
        )

        snap = browser_orchestrator_snapshot()
        return snap, orchestrator_queue_observability(snap)
    except ImportError:
        return {"health": "UNKNOWN"}, {}


def _cohere_mux_observability(
    mux_fields: dict[str, object],
    browser_orchestrator: dict[str, object],
) -> dict[str, object]:
    """Keep legacy cold-attach fields consistent with the authoritative plane.

    The compatibility mux probe can still read a stale status file after the
    Browser Orchestrator daemon has become unreachable.  Reporting that stale
    value as an available snapshot contradicts ``browserOrchestrator`` and
    lets callers launch with an unobservable data plane.  Unknown stays
    fail-closed; a healthy/degraded but observable plane keeps the probe data.
    """
    health = str(browser_orchestrator.get("health") or "UNKNOWN").upper()
    mux_available = browser_orchestrator.get("mux_snapshot_available")
    if mux_available is not True or health in {"UNKNOWN", "FAILED"}:
        return {**mux_fields, "muxSnapshotAvailable": False}
    return mux_fields


def _compute_next_action(
    ctx: E2eApiContext,
    *,
    headroom: dict[str, object],
    active_tests: list[dict[str, object]],
    mux_fields: dict[str, object],
    parallel_snapshot: dict[str, object] | None = None,
) -> str:
    from dev_gate_contract import (
        LIVE_AGENT_BODY_WALL_CLOCK_SEC,
        LIVE_AGENT_PYTEST_WALL_CAP_SEC,
        LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
        admit_wall_clock_sec,
    )

    admit_wall_cap = float(admit_wall_clock_sec())
    admit_active = 0
    shared_candidates = [
        candidate for candidate in ctx.candidates if candidate.source == "shared"
    ]
    shared_match = _shared_epoch_match(ctx)
    if any(not candidate.health_observable for candidate in shared_candidates):
        return "OBSERVABILITY_UNKNOWN"
    shared_healthy = any(candidate.health_ok for candidate in shared_candidates)
    if shared_candidates and not shared_healthy:
        # Crash heal must win over hung-peer FAIL_FAST: peers stuck in bootstrap
        # while :8080 is down cannot block the single-flight backend-only recovery.
        return "ATTACH_CRASH_HEAL"
    for row in active_tests:
        wall_phase = str(row.get("wall_phase") or "").strip().lower()
        admit_elapsed = row.get("admit_elapsed_sec")
        if wall_phase == "admit":
            admit_active += 1
            if isinstance(admit_elapsed, (int, float)):
                if float(admit_elapsed) >= admit_wall_cap:
                    from e2e_cluster_launch_policy import (
                        cluster_fail_fast_suppressed_for_active_test,
                    )

                    if not cluster_fail_fast_suppressed_for_active_test(row):
                        return "FAIL_FAST"
            elif isinstance(row.get("elapsed_sec"), (int, float)) and float(
                row["elapsed_sec"]
            ) >= float(LIVE_SINGLE_TEST_WALL_CLOCK_SEC):
                from e2e_cluster_launch_policy import (
                    cluster_fail_fast_suppressed_for_active_test,
                )

                if not cluster_fail_fast_suppressed_for_active_test(row):
                    return "FAIL_FAST"
        body_elapsed = row.get("body_elapsed_sec")
        if isinstance(body_elapsed, (int, float)):
            try:
                from transport_supervisor import live_agent_body_wall_cap_sec

                body_wall_cap = float(live_agent_body_wall_cap_sec())
            except ImportError:
                body_wall_cap = float(LIVE_AGENT_BODY_WALL_CLOCK_SEC)
            if float(body_elapsed) >= body_wall_cap:
                from e2e_cluster_launch_policy import (
                    cluster_fail_fast_suppressed_for_active_test,
                )

                if not cluster_fail_fast_suppressed_for_active_test(row):
                    return "FAIL_FAST"
        current_node = row.get("current_node")
        node_elapsed = row.get("node_elapsed_sec")
        if isinstance(current_node, str) and isinstance(node_elapsed, (int, float)):
            from e2e_stall_guard import (
                parallel_active_test_node_stuck_fail_fast,
            )

            if parallel_active_test_node_stuck_fail_fast(row):
                from e2e_cluster_launch_policy import (
                    cluster_fail_fast_suppressed_for_active_test,
                )

                if not cluster_fail_fast_suppressed_for_active_test(row):
                    return "FAIL_FAST"
        process_elapsed = row.get("elapsed_sec")
        wall_phase = str(row.get("wall_phase") or "").strip().lower()
        if (
            isinstance(process_elapsed, (int, float))
            and wall_phase not in ("bootstrap", "admit")
            and float(process_elapsed) >= float(LIVE_AGENT_PYTEST_WALL_CAP_SEC)
        ):
            from e2e_cluster_launch_policy import (
                cluster_fail_fast_suppressed_for_active_test,
            )

            if not cluster_fail_fast_suppressed_for_active_test(row):
                return "FAIL_FAST"
    if (
        not shared_match
        and shared_healthy
        and ctx.active_leases > 0
    ):
        # Running SHARED sessions pin the healthy shared backend generation.
        # Workspace drift means new backend code must use PRIVATE; it must not
        # serialize unrelated SHARED sessions behind an idle-only restart.
        return "PRIVATE_EPOCH_REQUIRED"
    if (
        not shared_match
        and ctx.active_leases == 0
        and any(
            candidate.health_ok and not candidate.epoch_match
            for candidate in shared_candidates
        )
    ):
        return "PRIVATE_EPOCH_REQUIRED"
    if headroom.get("parallelQueueExpected") is True:
        reasons = headroom.get("queueReasons", [])
        reason_list = (
            [str(item) for item in reasons] if isinstance(reasons, list) else []
        )
        # A PRIVATE credit queue is session-layer state owned by the admitted
        # PRIVATE session. It must not alter cluster launch readiness.
        operation_queue = [
            item for item in reason_list if item != "private_credit_queue"
        ]
        if operation_queue or mux_fields.get("muxColdAttachSaturated") is True:
            return "OPERATION_BACKPRESSURE"
    if ctx.blocked and admit_active > 0:
        # Epoch-aligned SHARED launches immediately. A blocked epoch must not
        # create a hidden SHARED session queue; PRIVATE has its own explicit
        # collect-time bypass and bounded credit queue.
        if (
            shared_match
            and str(
                getattr(ctx, "verify_api_base", "") or ctx.shared_api_base or ""
            ).strip()
        ):
            return "PARALLEL_OK" if active_tests else "READY"
        return "PRIVATE_EPOCH_REQUIRED"
    if not shared_match:
        return "PRIVATE_EPOCH_REQUIRED"
    if mux_fields.get("muxColdAttachSaturated") is True:
        return "OPERATION_BACKPRESSURE"
    snapshot = parallel_snapshot if parallel_snapshot is not None else {}
    snapshot_unavailable = isinstance(snapshot.get("snapshot_error"), str) and bool(
        str(snapshot.get("snapshot_error")).strip()
    )
    if ctx.drift_pending and ctx.active_leases == 0 and not snapshot_unavailable:
        return "PRIVATE_EPOCH_REQUIRED"
    if ctx.blocked:
        return "SHPOIB_OR_VERIFY_API"
    if active_tests:
        return "PARALLEL_OK"
    return "READY"


def _compute_stack_reuse(ctx: E2eApiContext, *, next_action: str) -> str:
    """Machine-readable stack reuse hint for Agent (browser-mcp §1b SSOT)."""
    if next_action == "ATTACH_CRASH_HEAL":
        return "attach_crash_heal"
    if next_action == "PRIVATE_EPOCH_REQUIRED":
        return "private_epoch"
    if next_action == "SHPOIB_OR_VERIFY_API":
        return "verify_api"
    if _shared_epoch_match(ctx):
        return "attach"
    if ctx.active_leases > 0:
        return "defer_parallel"
    if ctx.blocked:
        return "verify_api"
    return "private_epoch"


def _format_agent_decision_human(
    *,
    ctx: E2eApiContext,
    headroom: dict[str, object],
    active_tests: list[dict[str, object]],
    mux_fields: dict[str, object],
) -> list[str]:
    from dev_gate_contract import (
        E2E_BODY_WALL_EXCEEDED_TOKEN,
        LIVE_AGENT_BODY_WALL_CLOCK_SEC,
    )
    from e2e_readiness import evaluate_chrome_e2e_readiness

    readiness = evaluate_chrome_e2e_readiness(
        ctx,
        headroom=headroom,
        active_tests=active_tests,
        mux_fields=mux_fields,
    )
    lines = [
        f"NEXT_ACTION={readiness.next_action}",
        f"MYRM_READINESS_STATUS={readiness.status}",
        f"MYRM_READINESS_TOKEN={readiness.token}",
        f"E2E_LAUNCH_ALLOWED={'yes' if readiness.launch_allowed else 'no'}",
        f"E2E_READY_CHROME_FULL={'yes' if readiness.ready_chrome_full else 'no'}",
        f"E2E_STACK_REUSE={_compute_stack_reuse(ctx, next_action=readiness.next_action)}",
        f"AGENT_NEVER_SAY={AGENT_NEVER_SAY}",
    ]
    batch_rows = [row for row in active_tests if row.get("batch_mode") is True]
    if batch_rows:
        lines.append(
            "E2E_FILE_BATCH_CONTEXT: "
            + "; ".join(
                f"pid={row.get('pid')} test={row.get('test_id')}" for row in batch_rows
            )
            + " (process_elapsed≠single-test BODY; prefer path::test_name)"
        )
    for row in active_tests:
        current_node = row.get("current_node")
        body_elapsed = row.get("body_elapsed_sec")
        node_elapsed = row.get("node_elapsed_sec")
        if not current_node and body_elapsed is None and node_elapsed is None:
            continue
        pid = row.get("pid")
        parts = [f"pid={pid}"]
        if current_node:
            parts.append(f"current_node={current_node}")
        if isinstance(body_elapsed, (int, float)):
            parts.append(f"body_elapsed={float(body_elapsed):.0f}s")
            if float(body_elapsed) >= float(LIVE_AGENT_BODY_WALL_CLOCK_SEC):
                parts.append(f"{E2E_BODY_WALL_EXCEEDED_TOKEN}=yes")
        if isinstance(node_elapsed, (int, float)):
            parts.append(f"node_elapsed={float(node_elapsed):.0f}s")
        lines.append(f"E2E_TEST_PROGRESS: {' '.join(str(p) for p in parts)}")
    return lines


def _context_to_dict(
    ctx: E2eApiContext,
    *,
    parallel_snapshot: dict[str, object] | None = None,
    mux_fields: dict[str, object] | None = None,
    wave_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    from e2e_lease_liveness import (
        build_lease_liveness,
        lease_liveness_to_dict,
        load_wave_snapshot,
        wave_lease_counts,
    )

    resolved_mux = mux_fields or _mux_context_fields()
    resolved_parallel = parallel_snapshot
    if resolved_parallel is None:
        resolved_parallel, _ = _resolve_parallel_runtime_snapshot()
    resolved_wave = wave_snapshot or load_wave_snapshot()
    counts = wave_lease_counts(resolved_wave)
    active_tests_raw = resolved_parallel.get("active_tests")
    active_tests = (
        [item for item in active_tests_raw if isinstance(item, dict)]
        if isinstance(active_tests_raw, list)
        else []
    )
    liveness_rows = build_lease_liveness(resolved_wave, active_tests=active_tests)
    from dev_gate_status import dev_gate_status as _dev_gate_status

    dev_gate_payload = _dev_gate_status()
    active_test_count, observability_mismatch = _resolve_cap_headroom_active_test_count(
        resolved_parallel,
        wave_leases_effective=counts.effective_total,
        dev_gate=dev_gate_payload,
    )
    if observability_mismatch:
        resolved_parallel = {
            **resolved_parallel,
            "parallel_observability_mismatch": True,
        }
    browser_orchestrator_payload: dict[str, object] = {"health": "UNKNOWN"}
    orchestrator_obs: dict[str, object] = {}
    browser_orchestrator_payload, orchestrator_obs = _load_orchestrator_observability()
    resolved_mux = _cohere_mux_observability(
        resolved_mux,
        browser_orchestrator_payload,
    )
    headroom = _cap_headroom_fields(
        lease_counts=counts,
        mux_fields=resolved_mux,
        active_test_count=active_test_count,
        parallel_snapshot=resolved_parallel,
        observability_mismatch=observability_mismatch,
        orchestrator_observability=orchestrator_obs,
    )
    payload = asdict(ctx)
    payload["candidates"] = [_candidate_to_dict(item) for item in ctx.candidates]
    payload["verify_epoch_match"] = ctx.epoch_match
    payload["epoch_match"] = _shared_epoch_match(ctx)
    payload["verifyTarget"] = ctx.verify_api_base
    payload.update(resolved_mux)
    payload["parallelSnapshot"] = resolved_parallel
    payload["capHeadroom"] = headroom
    payload["leaseLiveness"] = lease_liveness_to_dict(liveness_rows)
    payload["devGate"] = dev_gate_payload
    payload["browserOrchestrator"] = browser_orchestrator_payload
    payload["orchestrator"] = {
        "queueDepth": orchestrator_obs.get("queueDepth", 0),
        "estimatedWaitSec": orchestrator_obs.get("estimatedWaitSec", 0),
        "operationSloSec": orchestrator_obs.get("operationSloSec", 20),
        "withinOperationSlo": orchestrator_obs.get("withinOperationSlo", True),
        "activeOps": orchestrator_obs.get("activeOps", 0),
        "effectiveCredits": orchestrator_obs.get("effectiveCredits", 4),
    }
    observe_json = os.environ.get("MYRM_E2E_CONTEXT_JSON", "").strip() == "1"
    if not observe_json:
        try:
            from dev_gate_coordinator import (
                default_socket_path,
                request,
            )

            metrics = request(
                {"operation": "snapshot", "session_id": "__health__"},
                socket_path=default_socket_path(),
                timeout_sec=0.5,
            )
            depth = metrics.get("asyncQueueDepth")
            if isinstance(depth, int):
                payload["devGateAsyncQueueDepth"] = depth
        except (ConnectionError, OSError, RuntimeError, TimeoutError, ImportError):
            pass
    if not observe_json:
        try:
            from e2e_browser_pool import browser_identity_snapshot

            payload["browserPool"] = browser_identity_snapshot()
        except ImportError:
            payload["browserPool"] = {
                "canonical": False,
                "next_action": "OBSERVABILITY_UNKNOWN",
            }
        try:
            from host_resource_governor import (
                host_resource_governor_snapshot,
            )

            payload["hostGovernor"] = host_resource_governor_snapshot()
        except ImportError:
            payload["hostGovernor"] = {"enabled": False, "effective_browser_slots": 4}
        try:
            from e2e_orchestrator import orchestrator_snapshot

            lifecycle = orchestrator_snapshot()
            payload["sessionLifecycle"] = lifecycle
            payload["phase"] = lifecycle.get("phase")
            payload["budgets_remaining"] = lifecycle.get("budgets_remaining")
        except (ImportError, OSError, RuntimeError, ValueError):
            payload["sessionLifecycle"] = {
                "phase": "UNKNOWN",
                "next_action": "OBSERVABILITY_UNKNOWN",
            }
    try:
        from e2e_auth_provisioner import auth_template_status

        payload["authTemplateStatus"] = auth_template_status(
            workspace_fingerprint=ctx.workspace_fingerprint
        )
    except ImportError:
        payload["authTemplateStatus"] = {
            "status": "UNKNOWN",
            "next_action": "OBSERVABILITY_UNKNOWN",
        }
    if payload.get("muxColdAttachSaturated") is True:
        payload["agent_rule"] = (
            f"{ctx.agent_rule} "
            "MUX_COLD_ATTACH_SATURATED: launch or retain the session; browser "
            "operations use bounded internal backpressure (P99 SLO ≤20s)."
        )
    active_count = active_test_count
    if active_count > 0:
        payload["agent_rule"] = (
            f"{payload['agent_rule']} "
            f"PARALLEL_E2E_ACTIVE={active_count}: use active_tests[] from e2e-context; "
            "do not pgrep; do not stop other pytest."
        )
    if headroom.get("parallelQueueExpected") is True:
        reasons = headroom.get("queueReasons", [])
        reason_str = (
            ",".join(str(item) for item in reasons)
            if isinstance(reasons, list) and reasons
            else "unknown"
        )
        rules: list[str] = []
        if "private_credit_queue" in reason_str.split(","):
            rules.append(
                f"PRIVATE_SESSION_QUEUE reasons={reason_str}: retain the admitted "
                "PRIVATE session; bounded ADMIT ≤900s with progress."
            )
        operation_reasons = [
            reason
            for reason in reason_str.split(",")
            if reason and reason != "private_credit_queue"
        ]
        if operation_reasons or headroom.get("queueLayer") == "operation":
            rules.append(
                f"OPERATION_BACKPRESSURE reasons={reason_str}: launch or retain the "
                "session; internal operation P99 SLO ≤20s with progress."
            )
        queue_rule = " ".join(rules)
        payload["agent_rule"] = (
            f"{payload.get('agent_rule', ctx.agent_rule)} {queue_rule} "
            "Do not stop/kill peer pytest; do not pipe ./myrm test to tail|head."
        )
    if headroom.get("queueLayer") == "operation":
        depth = headroom.get("operationQueueDepth", 0)
        est_wait = headroom.get("estimatedOperationWaitSec", 0)
        within_slo = headroom.get("operationWithinSlo", True)
        slo_note = "normal_backpressure" if within_slo else "exceeds_slo_investigate"
        payload["agent_rule"] = (
            f"{payload.get('agent_rule', ctx.agent_rule)} "
            f"OPERATION_BACKPRESSURE: queueDepth={depth} "
            f"estimatedWaitSec={est_wait} ({slo_note}): continue launch; "
            "do not kill peer; open_page>120s or node>10min no progress=bug."
        )
    stale_leases = [
        row
        for row in liveness_rows
        if row.owner_pid is not None and not row.owner_alive
    ]
    if stale_leases:
        payload["agent_rule"] = (
            f"{payload.get('agent_rule', ctx.agent_rule)} "
            "STALE_LEASE_SUSPECT: owner test.sh dead but lease active; "
            "keep peer state intact and let Coordinator reap automatically; "
            "re-read e2e-context with bounded retries; do NOT run wave reap or kill pytest."
        )
    next_action = _compute_next_action(
        ctx,
        headroom=headroom,
        active_tests=active_tests,
        mux_fields=resolved_mux,
    )
    payload["next_action"] = next_action
    payload["agent_never_say"] = AGENT_NEVER_SAY
    payload["browserIsolation"] = browser_isolation_payload()
    payload["agent_rule"] = (
        f"{payload.get('agent_rule', ctx.agent_rule)} {CHROME_INSTANCE_ISOLATION_RULE}"
    )
    return payload


def _cmd_context_json(_args: argparse.Namespace) -> int:
    os.environ["MYRM_E2E_CONTEXT_JSON"] = "1"
    ctx = resolve_e2e_api_context()
    sys.stdout.write(json.dumps(_context_to_dict(ctx), indent=2, sort_keys=True) + "\n")
    return 0


def _cmd_context_human(_args: argparse.Namespace) -> int:
    from e2e_lease_liveness import (
        build_lease_liveness,
        format_lease_liveness_human,
        load_wave_snapshot,
        wave_lease_counts,
    )

    ctx = resolve_e2e_api_context()
    wave_snapshot = load_wave_snapshot()
    counts = wave_lease_counts(wave_snapshot)
    drift_note = "yes" if ctx.drift_pending else "no"
    match_note = "yes" if _shared_epoch_match(ctx) else "no"
    sys.stdout.write(
        "E2E_VERIFY_API="
        f"{ctx.verify_api_base} "
        f"(shared={ctx.shared_api_base} drift_pending={drift_note} "
        f"epoch_match={match_note} wave_leases_total={ctx.active_leases} "
        f"wave_leases_effective={counts.effective_total} source={ctx.source} "
        f"blocked={'yes' if ctx.blocked else 'no'})\n"
    )
    sys.stdout.write(f"WORKSPACE_FINGERPRINT={ctx.workspace_fingerprint}\n")
    try:
        from e2e_auth_provisioner import auth_template_status

        auth_status = auth_template_status(
            workspace_fingerprint=ctx.workspace_fingerprint
        )
        sys.stdout.write(
            "E2E_AUTH_TEMPLATE="
            f"status={auth_status['status']} "
            f"next_action={auth_status['next_action']} "
            f"runtime_fp={auth_status['runtimeFingerprint']}\n"
        )
    except ImportError:
        pass
    try:
        from e2e_browser_pool import browser_identity_snapshot

        browser_identity = browser_identity_snapshot()
        sys.stdout.write(
            "E2E_BROWSER_IDENTITY="
            f"canonical={'yes' if browser_identity['canonical'] else 'no'} "
            f"port={browser_identity['chromePort']} "
            f"profile={browser_identity['chromeDataDir']}\n"
        )
    except ImportError:
        pass
    try:
        from host_resource_governor import (
            host_resource_governor_snapshot,
        )

        gov = host_resource_governor_snapshot()
        sys.stdout.write(
            "E2E_HOST_GOVERNOR="
            f"effective={gov.get('effective_browser_slots', '?')}/"
            f"{gov.get('max_browser_slots', 4)} "
            f"load_1m={gov.get('load_avg_1m', 0):.2f} "
            f"memory={gov.get('memory_pressure', 'unknown')} "
            f"enabled={'yes' if gov.get('enabled') else 'no'}\n"
        )
    except ImportError:
        pass
    if ctx.blocked:
        sys.stdout.write(f"BLOCKED_REASON={ctx.blocked_reason}\n")
        if not _shared_epoch_match(ctx):
            sys.stdout.write(
                "E2E_BLOCKED_EPOCH: workspace backend differs from the deployed "
                "shared epoch; use the node planner's PRIVATE immutable epoch for "
                "workspace backend code, while tests targeting the deployed shared "
                "epoch remain SHARED; do not wait, restart shared :8080, or stop peers.\n"
            )
    mux_fields = _mux_context_fields()
    parallel_snapshot, parallel_lines = _resolve_parallel_runtime_snapshot()
    from dev_gate_status import dev_gate_status as _dev_gate_status

    dev_gate_payload = _dev_gate_status()
    active_test_count, observability_mismatch = _resolve_cap_headroom_active_test_count(
        parallel_snapshot,
        wave_leases_effective=counts.effective_total,
        dev_gate=dev_gate_payload,
    )
    if observability_mismatch:
        parallel_snapshot = {
            **parallel_snapshot,
            "parallel_observability_mismatch": True,
        }
    _browser_orchestrator_payload, orchestrator_obs = (
        _load_orchestrator_observability()
    )
    mux_fields = _cohere_mux_observability(mux_fields, _browser_orchestrator_payload)
    active_tests_raw = parallel_snapshot.get("active_tests")
    active_tests = (
        [item for item in active_tests_raw if isinstance(item, dict)]
        if isinstance(active_tests_raw, list)
        else []
    )
    sys.stdout.write(
        "MUX_COLD_ATTACH="
        f"{mux_fields['muxColdAttachActive']}/{mux_fields['muxColdAttachMax']} "
        f"saturated={'yes' if mux_fields['muxColdAttachSaturated'] else 'no'} "
        f"handProbe={'yes' if mux_fields['muxHandProbeAllowed'] else 'no'}\n"
    )
    try:
        from e2e_mux_transport_queue import (
            format_transport_queue_human,
        )

        sys.stdout.write(f"{format_transport_queue_human()}\n")
    except ImportError:
        pass
    sys.stdout.write(
        _format_cap_headroom_human(
            lease_counts=counts,
            mux_fields=mux_fields,
            active_test_count=active_test_count,
            parallel_snapshot=parallel_snapshot,
            orchestrator_observability=orchestrator_obs,
        )
        + "\n"
    )
    admit_count = int(parallel_snapshot.get("admit_active_count", 0))
    body_count = int(parallel_snapshot.get("body_active_count", 0))
    sys.stdout.write(
        f"E2E_SESSIONS_ACTIVE: admit={admit_count} body={body_count} "
        f"total={active_test_count}\n"
    )
    try:
        from stack_heal_coordinator import coordinator_snapshot

        heal = coordinator_snapshot()
        leader = heal.get("leaderPid")
        if leader is not None:
            sys.stdout.write(f"E2E_STACK_HEAL: leader_pid={leader}\n")
    except ImportError:
        pass
    queue_human = _format_queue_human(
        lease_counts=counts,
        mux_fields=mux_fields,
        active_test_count=active_test_count,
        parallel_snapshot=parallel_snapshot,
        orchestrator_observability=orchestrator_obs,
    )
    if queue_human is not None:
        sys.stdout.write(f"{queue_human}\n")
    liveness_rows = build_lease_liveness(wave_snapshot, active_tests=active_tests)
    for line in format_lease_liveness_human(liveness_rows):
        sys.stdout.write(f"{line}\n")
    for line in parallel_lines:
        sys.stdout.write(f"{line}\n")
    headroom = _cap_headroom_fields(
        lease_counts=counts,
        mux_fields=mux_fields,
        active_test_count=active_test_count,
        parallel_snapshot=parallel_snapshot,
        observability_mismatch=observability_mismatch,
        orchestrator_observability=orchestrator_obs,
    )
    for line in _format_agent_decision_human(
        ctx=ctx,
        headroom=headroom,
        active_tests=active_tests,
        mux_fields=mux_fields,
    ):
        sys.stdout.write(f"{line}\n")
    sys.stdout.write(
        "E2E_PARALLEL_SNAPSHOT_JSON="
        f"{json.dumps(parallel_snapshot, ensure_ascii=False)}\n"
    )
    enriched = _context_to_dict(
        ctx,
        parallel_snapshot=parallel_snapshot,
        mux_fields=mux_fields,
        wave_snapshot=wave_snapshot,
    )
    lifecycle = enriched.get("sessionLifecycle")
    if isinstance(lifecycle, dict):
        sys.stdout.write(
            "E2E_SESSION_LIFECYCLE="
            f"profile={lifecycle.get('profile')} phase={lifecycle.get('phase')} "
            f"remaining={lifecycle.get('remaining_sec')}s\n"
        )
    sys.stdout.write(f"AGENT_RULE={enriched['agent_rule']}\n")
    return 0


def _cmd_verify_api(args: argparse.Namespace) -> int:
    ctx = resolve_e2e_api_context(
        retry_after_apply=not bool(getattr(args, "ensure_backend", False))
    )
    if ctx.blocked and bool(getattr(args, "ensure_backend", False)):
        from verify_backend_seed import ensure_verify_backend_seed

        seed = ensure_verify_backend_seed(monorepo=monorepo_root())
        sys.stderr.write(
            f"MYRM_VERIFY_API_SEED: ok={seed.ok} runtime={seed.runtime_id} "
            f"api={seed.api_base} detail={seed.detail}\n"
        )
        if seed.ok:
            ctx = resolve_e2e_api_context(retry_after_apply=False)
    if ctx.blocked:
        sys.stderr.write(f"MYRM_VERIFY_API_BLOCKED: {ctx.blocked_reason}\n")
        sys.stderr.write(f"AGENT_RULE={ctx.agent_rule}\n")
        if bool(getattr(args, "ensure_backend", False)):
            sys.stderr.write(
                "Hint: --ensure-backend seed failed or SHPOIB cap full; "
                "wait for auto queue (do not stop other pytest).\n"
            )
        else:
            sys.stderr.write(
                "Hint: retry with ./myrm verify-api --ensure-backend … "
                "(parallel leases defer shared reload; do not stop other pytest).\n"
            )
        return 2
    method = str(args.method).upper()
    path = str(args.path)
    if not path.startswith("/"):
        path = f"/{path}"
    url = f"{ctx.verify_api_base.rstrip('/')}{path}"
    sys.stderr.write(
        f"MYRM_VERIFY_API: {method} {url} "
        f"(shared={ctx.shared_api_base} drift_pending={ctx.drift_pending} "
        f"verify_epoch_match={ctx.epoch_match} "
        f"shared_epoch_match={_shared_epoch_match(ctx)} "
        f"wave_leases_total={ctx.active_leases} source={ctx.source})\n"
    )
    curl_cmd: list[str] = [
        "curl",
        "-sS",
        "-w",
        "\nHTTP:%{http_code}\n",
        "-X",
        method,
        url,
    ]
    if args.data is not None:
        curl_cmd.extend(["-H", "Content-Type: application/json", "-d", args.data])
    proc = subprocess.run(curl_cmd, check=False)
    return proc.returncode


def _cmd_launch_check(_args: argparse.Namespace) -> int:
    from e2e_readiness import _cmd_check

    return int(_cmd_check(_args))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ctx_json = sub.add_parser("context-json")
    ctx_json.set_defaults(handler=_cmd_context_json)

    ctx_human = sub.add_parser("context-human")
    ctx_human.set_defaults(handler=_cmd_context_human)

    launch_check = sub.add_parser("launch-check")
    launch_check.set_defaults(handler=_cmd_launch_check)

    verify = sub.add_parser("verify-api")
    verify.add_argument("method", choices=("GET", "POST", "PUT", "PATCH", "DELETE"))
    verify.add_argument("path")
    verify.add_argument("data", nargs="?", default=None)
    verify.add_argument(
        "--ensure-backend",
        action="store_true",
        help="When BLOCKED, seed one backend-only isolated runtime (SHPOIB cap)",
    )
    verify.set_defaults(handler=_cmd_verify_api)

    ns = parser.parse_args(argv)
    handler = getattr(ns, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(ns))


if __name__ == "__main__":
    raise SystemExit(main())
