"""Resolve the correct dev API base for Agent/server verification during parallel E2E.

Verification Plane SSOT: route API checks to a backend whose stored stack-epoch
source_fingerprint matches the workspace fingerprint. Fail-closed when no match.

[INPUT]
- runtime_identity._backend_source_fingerprint (workspace FP SSOT)
- isolated_runtime_registry (private backend ports + stateDir)
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
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
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
_CONTEXT_PROBE_STARTED_MONO: float | None = None
AGENT_NEVER_SAY: Final[str] = (
    "停其他pytest|只跑一个E2E|kill其他pytest|先清wave|停止并行测试|kill wave"
)
_CURL_STATUS_MARKER: Final[str] = "\n__MYRM_HTTP_STATUS__:"
_LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "localhost", "::1"})


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


def monorepo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def shared_api_base() -> str:
    explicit = os.environ.get("MYRM_SHARED_E2E_API_BASE", "").strip()
    if explicit:
        return explicit.rstrip("/")
    port_raw = os.environ.get("MYRM_BACKEND_PORT", str(SHARED_DEFAULT_PORT)).strip()
    port = int(port_raw) if port_raw.isdigit() else SHARED_DEFAULT_PORT
    return f"http://127.0.0.1:{port}"


def shared_dev_state_dir() -> Path:
    override = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    if override:
        return Path(override).resolve()
    return Path.home() / ".local/state/myrm-dev"


def isolated_registry_root() -> Path:
    override = os.environ.get("MYRM_ISOLATED_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return Path.home() / ".local/state/myrm-isolated"


def workspace_backend_fingerprint() -> str:
    return _backend_source_fingerprint()


def _scripts_dev_dir() -> Path:
    return monorepo_root() / "scripts" / "dev"


def _ensure_scripts_dev_importable() -> None:
    dev_dir = str(_scripts_dev_dir())
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
    return parsed if parsed > 0 else 0.0


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


def _api_health_ok(
    api_base: str, timeout_sec: float = HEALTH_PROBE_TIMEOUT_SEC
) -> bool:
    timeout_sec = _bounded_probe_timeout(timeout_sec)
    if timeout_sec <= 0:
        return False
    base = api_base.rstrip("/")
    for path in HEALTH_PATHS:
        url = f"{base}{path}"
        try:
            with urllib.request.urlopen(url, timeout=timeout_sec) as resp:  # noqa: S310
                if 200 <= resp.status < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            if _curl_loopback_get(url, timeout_sec=timeout_sec) is not None:
                return True
    return False


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
        with urllib.request.urlopen(  # noqa: S310
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
    from isolated_runtime_registry import ACTIVE_PHASES, read_registry  # noqa: PLC0415

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
        if _api_health_ok(api_base, timeout_sec=PORT_SCAN_PROBE_TIMEOUT_SEC):
            found.append((api_base, port, "", "port_scan"))
    return found


def _should_skip_port_scan_under_parallel_block(
    candidates: list[BackendCandidate],
) -> bool:
    """Port scan cannot mint workspace epoch under active leases — avoid 41× probe burn."""
    from e2e_lease_liveness import (
        load_wave_snapshot,
        wave_lease_counts,
    )  # noqa: PLC0415

    if wave_lease_counts(load_wave_snapshot()).total <= 0:
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
        health_ok = _api_health_ok(api_base)
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
            )
        )
    return candidates


def enumerate_backend_candidates(*, workspace_fp: str) -> list[BackendCandidate]:
    specs: list[tuple[str, int, str, str]] = []
    shared = shared_api_base()
    shared_port = _port_from_api_base(shared)
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

    return sorted(matching, key=sort_key)[0]


def _blocked_reason(
    *,
    candidates: list[BackendCandidate],
    active_leases: int,
    drift_pending: bool,
    workspace_fp: str,
) -> str:
    healthy = [item for item in candidates if item.health_ok]
    if not workspace_fp:
        return "workspace backend source_fingerprint unavailable"
    if not healthy:
        return "no healthy backend reachable; run ./myrm ready --attach"
    stale = [item for item in healthy if not item.epoch_match]
    if stale and active_leases > 0:
        return (
            f"no backend at workspace epoch ({active_leases} active leases; "
            "SMP may defer shared reload)"
        )
    if stale and drift_pending:
        return "pending stack drift; no private backend at workspace epoch"
    if stale:
        return (
            "all healthy backends run stale code; retry with "
            "./myrm verify-api --ensure-backend (do not restart shared stack during parallel E2E)"
        )
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
        rule = (
            "verify-api routed to epoch-matched backend; "
            "do not curl shared :8080; "
            "do not use Chrome Settings UI to verify new server logic during drift "
            "(shared :3000 always proxies :8080)"
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
    rule = (
        f"BLOCKED: {blocked_reason}. "
        "Use verify-api only; do not curl shared :8080; do not stop other tests."
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
    _begin_context_probe_wall()
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
    retry_after_apply: bool = True,  # noqa: ARG001 — kept for caller compat; drift apply moved to Coordinator
) -> E2eApiContext:
    root = (monorepo or monorepo_root()).resolve()
    resolved_state = state_dir or _default_state_dir()
    shared = shared_api_base()
    workspace_fp = workspace_backend_fingerprint()
    from e2e_lease_liveness import (
        load_wave_snapshot,
        wave_lease_counts,
    )  # noqa: PLC0415

    wave_snapshot = load_wave_snapshot()
    lease_counts = wave_lease_counts(wave_snapshot)
    active_leases = lease_counts.total

    # P0-A: drift apply removed from observation path — Coordinator daemon owns mutation.
    # Here we only read drift state for context reporting.
    drift_pending = pending_drift_exists(resolved_state)
    drift_action = decide_drift_heal(
        active_leases=active_leases,
        drift_pending=drift_pending,
    ).value

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
    from dev_gate_contract import MUX_COLD_ATTACH_SLOTS  # noqa: PLC0415
    from mux_upstream_admission import read_mux_cold_attach_status  # noqa: PLC0415

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


def _server_tests_support_dir() -> Path:
    return monorepo_root() / "myrm-agent" / "myrm-agent-server"


def _load_parallel_runtime_snapshot() -> tuple[dict[str, object], list[str]]:
    """SSOT parallel chrome_e2e processes + flock holders for Agent diagnosis."""
    support_dir = _server_tests_support_dir()
    inserted = False
    support_text = str(support_dir)
    if support_text not in sys.path:
        sys.path.insert(0, support_text)
        inserted = True
    try:
        from tests.support.e2e_parallel_snapshot import (  # noqa: PLC0415
            format_parallel_snapshot_human,
            parallel_snapshot_to_dict,
            snapshot_live_e2e_processes,
        )

        snapshot = snapshot_live_e2e_processes()
        return parallel_snapshot_to_dict(snapshot), format_parallel_snapshot_human(
            snapshot
        )
    except Exception as exc:
        fallback: dict[str, object] = {
            "agent_stream_lock": None,
            "desktop_approval_lock": None,
            "active_tests": [],
            "active_test_count": "UNKNOWN",
            "snapshot_error": str(exc),
            "snapshot_unavailable": True,
        }
        return fallback, [
            "E2E_PARALLEL_ACTIVE: UNAVAILABLE (fail-closed: treat as non-zero)",
            f"E2E_PARALLEL_SNAPSHOT_ERROR={exc}",
        ]
    finally:
        if inserted:
            sys.path.remove(support_text)


def _safe_active_test_count(snapshot: dict[str, object]) -> int:
    """Extract active_test_count; fail-closed returns 1 when UNKNOWN/invalid.

    P0-A: snapshot unavailable must never report 0 (which would trigger
    restart/heal while parallel sessions are actually running).
    """
    raw = snapshot.get("active_test_count", 0)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return 1


def _compute_queue_state(
    *,
    live_agent_shpoib_count: int,
    mux_fields: dict[str, object],
    parallel_snapshot: dict[str, object] | None,
) -> tuple[bool, list[str]]:
    del live_agent_shpoib_count, mux_fields, parallel_snapshot
    from dev_gate_status import dev_gate_status  # noqa: PLC0415

    status = dev_gate_status()
    reasons: list[str] = []
    if int(status["private_waiting"]) > 0:
        reasons.append("private_credit_queue")
    try:
        from e2e_mux_transport_queue import transport_queue_snapshot  # noqa: PLC0415

        if transport_queue_snapshot().blocked:
            reasons.append("mux_transport_queue")
    except ImportError:
        pass
    return len(reasons) > 0, reasons


def _cap_headroom_fields(
    *,
    lease_counts: object,
    mux_fields: dict[str, object],
    active_test_count: int,
    parallel_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    from dev_gate_contract import MUX_COLD_ATTACH_SLOTS  # noqa: PLC0415
    from dev_gate_status import dev_gate_status  # noqa: PLC0415
    from e2e_lease_liveness import WaveLeaseCounts  # noqa: PLC0415

    counts = (
        lease_counts
        if isinstance(lease_counts, WaveLeaseCounts)
        else WaveLeaseCounts(
            total=int(getattr(lease_counts, "total", lease_counts)),
            live_agent_shpoib=int(
                getattr(lease_counts, "live_agent_shpoib", lease_counts)
            ),
            live_agent_shared_hot=0,
            read_page=0,
            effective_total=int(getattr(lease_counts, "total", lease_counts)),
            effective_live_agent_shpoib=int(
                getattr(lease_counts, "live_agent_shpoib", lease_counts)
            ),
            effective_live_agent_shared_hot=0,
            effective_read_page=0,
        )
    )
    mux_active = int(mux_fields.get("muxColdAttachActive", 0))
    mux_max = int(mux_fields.get("muxColdAttachMax", MUX_COLD_ATTACH_SLOTS))
    queue_expected, queue_reasons = _compute_queue_state(
        live_agent_shpoib_count=counts.effective_live_agent_shpoib,
        mux_fields=mux_fields,
        parallel_snapshot=parallel_snapshot,
    )
    dev_gate = dev_gate_status()
    return {
        "waveLeasesActive": counts.total,
        "waveLeasesEffective": counts.effective_total,
        "muxColdAttachRemaining": max(0, mux_max - mux_active),
        "activeTestCount": active_test_count,
        "parallelQueueExpected": queue_expected,
        "queueReasons": queue_reasons,
        "sharedUnlimited": True,
        "sharedActive": int(dev_gate["shared_active"]),
        "privateActive": int(dev_gate["private_active"]),
        "privateWaiting": int(dev_gate["private_waiting"]),
        "privateActiveCredits": int(dev_gate["private_active_credits"]),
        "privateCapacityCredits": int(dev_gate["private_capacity_credits"]),
        "privateAvailableCredits": int(dev_gate.get("private_available_credits", 0)),
        "privateCreditIdleReason": str(
            dev_gate.get("private_credit_idle_reason", "unknown")
        ),
    }


def _format_cap_headroom_human(
    *,
    lease_counts: object,
    mux_fields: dict[str, object],
    active_test_count: int,
    parallel_snapshot: dict[str, object] | None = None,
) -> str:
    headroom = _cap_headroom_fields(
        lease_counts=lease_counts,
        mux_fields=mux_fields,
        active_test_count=active_test_count,
        parallel_snapshot=parallel_snapshot,
    )
    mux_active = int(mux_fields.get("muxColdAttachActive", 0))
    mux_max = int(mux_fields.get("muxColdAttachMax", 0))
    saturated = "yes" if mux_fields.get("muxColdAttachSaturated") else "no"
    queue = "yes" if headroom["parallelQueueExpected"] else "no"
    reasons = headroom.get("queueReasons", [])
    reason_note = ""
    if isinstance(reasons, list) and reasons:
        reason_note = f" queue_reasons={','.join(str(item) for item in reasons)}"
    return (
        "E2E_CAP_HEADROOM: "
        f"shared=unlimited active={headroom['sharedActive']} "
        f"private={headroom['privateActiveCredits']}/"
        f"{headroom['privateCapacityCredits']} "
        f"private_available={headroom['privateAvailableCredits']} "
        f"private_idle={headroom['privateCreditIdleReason']} "
        f"private_waiting={headroom['privateWaiting']} "
        f"mux_cold_attach={mux_active}/{mux_max} saturated={saturated} "
        f"active_tests={active_test_count} queue_expected={queue}{reason_note} "
        "(do not stop other pytest)"
    )


def _format_queue_human(
    *,
    lease_counts: object,
    mux_fields: dict[str, object],
    active_test_count: int,
    parallel_snapshot: dict[str, object] | None = None,
) -> str | None:
    headroom = _cap_headroom_fields(
        lease_counts=lease_counts,
        mux_fields=mux_fields,
        active_test_count=active_test_count,
        parallel_snapshot=parallel_snapshot,
    )
    if not headroom["parallelQueueExpected"]:
        return None
    reasons = headroom.get("queueReasons", [])
    reason_str = (
        ",".join(str(item) for item in reasons)
        if isinstance(reasons, list) and reasons
        else "unknown"
    )
    return (
        "E2E_QUEUE_HUMAN: "
        f"reason={reason_str} "
        f"(private={headroom['privateActiveCredits']}/"
        f"{headroom['privateCapacityCredits']} "
        f"waiting={headroom['privateWaiting']} active_tests={active_test_count}). "
        "Only PRIVATE runtime creation queues in ADMIT (≤900s); "
        "SHARED logical sessions are unlimited. "
        "NEVER stop/kill other pytest. "
        "Progress on stderr: E2E_PRIVATE_ADMIT_WAIT every 30s. "
        "Do NOT pipe './myrm test' to tail|head — hides progress."
    )


def _compute_next_action(
    ctx: E2eApiContext,
    *,
    headroom: dict[str, object],
    active_tests: list[dict[str, object]],
    mux_fields: dict[str, object],
    parallel_snapshot: dict[str, object] | None = None,
) -> str:
    from dev_gate_contract import (  # noqa: PLC0415
        E2E_ADMISSION_WALL_CLOCK_SEC,
        LIVE_AGENT_BODY_WALL_CLOCK_SEC,
        LIVE_AGENT_PYTEST_WALL_CAP_SEC,
        LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
    )

    admit_active = 0
    for row in active_tests:
        wall_phase = str(row.get("wall_phase") or "").strip().lower()
        admit_elapsed = row.get("admit_elapsed_sec")
        if wall_phase == "admit":
            admit_active += 1
            if isinstance(admit_elapsed, (int, float)):
                if float(admit_elapsed) >= float(E2E_ADMISSION_WALL_CLOCK_SEC):
                    return "FAIL_FAST"
            elif isinstance(row.get("elapsed_sec"), (int, float)):
                if float(row["elapsed_sec"]) >= float(LIVE_SINGLE_TEST_WALL_CLOCK_SEC):
                    return "FAIL_FAST"
        body_elapsed = row.get("body_elapsed_sec")
        if isinstance(body_elapsed, (int, float)):
            try:
                from transport_supervisor import live_agent_body_wall_cap_sec

                body_wall_cap = float(live_agent_body_wall_cap_sec())
            except ImportError:
                body_wall_cap = float(LIVE_AGENT_BODY_WALL_CLOCK_SEC)
            if float(body_elapsed) >= body_wall_cap:
                return "FAIL_FAST"
        current_node = row.get("current_node")
        node_elapsed = row.get("node_elapsed_sec")
        if isinstance(current_node, str) and isinstance(node_elapsed, (int, float)):
            from e2e_stall_guard import (  # noqa: PLC0415
                parallel_active_test_node_stuck_fail_fast,
            )

            if parallel_active_test_node_stuck_fail_fast(row):
                return "FAIL_FAST"
        process_elapsed = row.get("elapsed_sec")
        wall_phase = str(row.get("wall_phase") or "").strip().lower()
        if isinstance(process_elapsed, (int, float)) and wall_phase not in (
            "bootstrap",
            "admit",
        ):
            if float(process_elapsed) >= float(LIVE_AGENT_PYTEST_WALL_CAP_SEC):
                return "FAIL_FAST"
    if headroom.get("parallelQueueExpected") is True:
        return "QUEUE"
    if ctx.blocked and admit_active > 0:
        return "ADMIT_STACK_HEAL_WAIT"
    if ctx.blocked and not ctx.epoch_match:
        return "SHPOIB_OR_VERIFY_API"
    if mux_fields.get("muxColdAttachSaturated") is True:
        return "QUEUE"
    snapshot = parallel_snapshot if parallel_snapshot is not None else {}
    snapshot_unavailable = isinstance(snapshot.get("snapshot_error"), str) and bool(
        str(snapshot.get("snapshot_error")).strip()
    )
    if ctx.drift_pending and ctx.active_leases == 0 and not snapshot_unavailable:
        return "RESTART_WHEN_IDLE"
    if ctx.blocked:
        return "SHPOIB_OR_VERIFY_API"
    if active_tests:
        return "PARALLEL_OK"
    return "READY"


def _compute_stack_reuse(ctx: E2eApiContext, *, next_action: str) -> str:
    """Machine-readable stack reuse hint for Agent (browser-mcp §1b SSOT)."""
    if next_action == "SHPOIB_OR_VERIFY_API":
        return "verify_api"
    if ctx.epoch_match:
        return "attach"
    if ctx.active_leases > 0:
        return "defer_parallel"
    if next_action == "RESTART_WHEN_IDLE":
        return "restart_when_idle"
    if ctx.blocked:
        return "verify_api"
    return "restart_when_idle"


def _format_agent_decision_human(
    *,
    ctx: E2eApiContext,
    headroom: dict[str, object],
    active_tests: list[dict[str, object]],
    mux_fields: dict[str, object],
) -> list[str]:
    from dev_gate_contract import (  # noqa: PLC0415
        E2E_BODY_WALL_EXCEEDED_TOKEN,
        LIVE_AGENT_BODY_WALL_CLOCK_SEC,
    )
    from e2e_readiness import evaluate_chrome_e2e_readiness  # noqa: PLC0415

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
    from e2e_lease_liveness import (  # noqa: PLC0415
        build_lease_liveness,
        lease_liveness_to_dict,
        load_wave_snapshot,
        wave_lease_counts,
    )

    resolved_mux = mux_fields or _mux_context_fields()
    resolved_parallel = parallel_snapshot
    if resolved_parallel is None:
        resolved_parallel, _ = _load_parallel_runtime_snapshot()
    resolved_wave = wave_snapshot or load_wave_snapshot()
    counts = wave_lease_counts(resolved_wave)
    active_tests_raw = resolved_parallel.get("active_tests")
    active_tests = (
        [item for item in active_tests_raw if isinstance(item, dict)]
        if isinstance(active_tests_raw, list)
        else []
    )
    liveness_rows = build_lease_liveness(resolved_wave, active_tests=active_tests)
    headroom = _cap_headroom_fields(
        lease_counts=counts,
        mux_fields=resolved_mux,
        active_test_count=_safe_active_test_count(resolved_parallel),
        parallel_snapshot=resolved_parallel,
    )
    payload = asdict(ctx)
    payload["candidates"] = [_candidate_to_dict(item) for item in ctx.candidates]
    payload["verifyTarget"] = ctx.verify_api_base
    payload.update(resolved_mux)
    payload["parallelSnapshot"] = resolved_parallel
    payload["capHeadroom"] = headroom
    payload["leaseLiveness"] = lease_liveness_to_dict(liveness_rows)
    from dev_gate_status import dev_gate_status  # noqa: PLC0415

    payload["devGate"] = dev_gate_status()
    try:
        from dev_gate_coordinator import default_socket_path, request  # noqa: PLC0415

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
    try:
        from browser_orchestrator import browser_orchestrator_snapshot  # noqa: PLC0415

        payload["browserOrchestrator"] = browser_orchestrator_snapshot()
    except ImportError:
        payload["browserOrchestrator"] = {"health": "UNKNOWN"}
    try:
        from e2e_auth_provisioner import auth_template_status  # noqa: PLC0415

        payload["authTemplateStatus"] = auth_template_status(
            workspace_fingerprint=ctx.workspace_fingerprint
        )
    except ImportError:
        payload["authTemplateStatus"] = {
            "status": "UNKNOWN",
            "next_action": "OBSERVABILITY_UNKNOWN",
        }
    try:
        from e2e_browser_pool import browser_identity_snapshot  # noqa: PLC0415

        payload["browserPool"] = browser_identity_snapshot()
    except ImportError:
        payload["browserPool"] = {
            "canonical": False,
            "next_action": "OBSERVABILITY_UNKNOWN",
        }
    try:
        from host_resource_governor import (
            host_resource_governor_snapshot,
        )  # noqa: PLC0415

        payload["hostGovernor"] = host_resource_governor_snapshot()
    except ImportError:
        payload["hostGovernor"] = {"enabled": False, "effective_browser_slots": 4}
    try:
        from e2e_orchestrator import orchestrator_snapshot  # noqa: PLC0415

        lifecycle = orchestrator_snapshot()
        payload["sessionLifecycle"] = lifecycle
        payload["phase"] = lifecycle.get("phase")
        payload["budgets_remaining"] = lifecycle.get("budgets_remaining")
    except Exception:
        pass
    if payload.get("muxColdAttachSaturated") is True:
        payload["agent_rule"] = (
            f"{ctx.agent_rule} "
            "MUX_COLD_ATTACH_SATURATED: do not hand new_page/navigate; "
            "use verify-api or ./myrm test -m chrome_e2e (auto queue ≤900s)."
        )
    active_count = _safe_active_test_count(resolved_parallel)
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
        payload["agent_rule"] = (
            f"{payload.get('agent_rule', ctx.agent_rule)} "
            f"QUEUE_EXPECTED=yes reasons={reason_str}: read E2E_QUEUE_HUMAN; "
            "auto ADMIT queue ≤900s; do not stop/kill other pytest; "
            "do not pipe ./myrm test to tail|head."
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
            "./myrm wave reap; do NOT ask user to kill pytest."
        )
    next_action = _compute_next_action(
        ctx,
        headroom=headroom,
        active_tests=active_tests,
        mux_fields=resolved_mux,
    )
    payload["next_action"] = next_action
    payload["agent_never_say"] = AGENT_NEVER_SAY
    return payload


def _cmd_context_json(_args: argparse.Namespace) -> int:
    ctx = resolve_e2e_api_context()
    sys.stdout.write(json.dumps(_context_to_dict(ctx), indent=2, sort_keys=True) + "\n")
    return 0


def _cmd_context_human(_args: argparse.Namespace) -> int:
    from e2e_lease_liveness import (  # noqa: PLC0415
        build_lease_liveness,
        format_lease_liveness_human,
        load_wave_snapshot,
        wave_lease_counts,
    )

    ctx = resolve_e2e_api_context()
    wave_snapshot = load_wave_snapshot()
    counts = wave_lease_counts(wave_snapshot)
    drift_note = "yes" if ctx.drift_pending else "no"
    match_note = "yes" if ctx.epoch_match else "no"
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
        from e2e_auth_provisioner import auth_template_status  # noqa: PLC0415

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
        from e2e_browser_pool import browser_identity_snapshot  # noqa: PLC0415

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
        )  # noqa: PLC0415

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
        if not ctx.epoch_match:
            sys.stdout.write(
                "E2E_BLOCKED_EPOCH: shared reload deferred "
                f"({ctx.active_leases} active leases); use SHPOIB verify-api; "
                "do not stop other tests.\n"
            )
    mux_fields = _mux_context_fields()
    parallel_snapshot, parallel_lines = _load_parallel_runtime_snapshot()
    active_test_count = _safe_active_test_count(parallel_snapshot)
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
        )  # noqa: PLC0415

        sys.stdout.write(f"{format_transport_queue_human()}\n")
    except ImportError:
        pass
    sys.stdout.write(
        _format_cap_headroom_human(
            lease_counts=counts,
            mux_fields=mux_fields,
            active_test_count=active_test_count,
            parallel_snapshot=parallel_snapshot,
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
        from stack_heal_coordinator import coordinator_snapshot  # noqa: PLC0415

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
        from verify_backend_seed import ensure_verify_backend_seed  # noqa: PLC0415

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
        f"epoch_match={ctx.epoch_match} wave_leases_total={ctx.active_leases} source={ctx.source})\n"
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
    from e2e_readiness import _cmd_check  # noqa: PLC0415

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
