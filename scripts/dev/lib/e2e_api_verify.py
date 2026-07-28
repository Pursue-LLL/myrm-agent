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
- CLI: context-json, verify-api (proxy curl; optional --ensure-backend seed)

[POS]
Agent-facing SSOT for API verification — eliminates stale :8080 / stale private pool false results.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from runtime_identity import _backend_source_fingerprint
from stack_mutation_policy import (
    _default_state_dir,
    apply_pending_drift_if_idle,
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
AGENT_NEVER_SAY: Final[str] = (
    "停其他pytest|只跑一个E2E|kill其他pytest|先清wave|停止并行测试|kill wave"
)


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


def _api_health_ok(
    api_base: str, timeout_sec: float = HEALTH_PROBE_TIMEOUT_SEC
) -> bool:
    base = api_base.rstrip("/")
    for path in HEALTH_PATHS:
        url = f"{base}{path}"
        try:
            with urllib.request.urlopen(url, timeout=timeout_sec) as resp:  # noqa: S310
                if 200 <= resp.status < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return False


def _read_health_stack_epoch(api_base: str) -> tuple[int | None, str]:
    url = f"{api_base.rstrip('/')}/api/v1/health"
    try:
        with urllib.request.urlopen(
            url, timeout=HEALTH_PROBE_TIMEOUT_SEC
        ) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
        ValueError,
    ):
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
    found: list[tuple[str, int, str, str]] = []
    for port in range(PRIVATE_PORT_SCAN_START, PRIVATE_PORT_SCAN_END + 1):
        if port in known_ports:
            continue
        api_base = f"http://127.0.0.1:{port}"
        if _api_health_ok(api_base, timeout_sec=PORT_SCAN_PROBE_TIMEOUT_SEC):
            found.append((api_base, port, "", "port_scan"))
    return found


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

    if pending_drift_exists(resolved_state) and active_leases == 0:
        apply_pending_drift_if_idle(monorepo_root=root, state_dir=resolved_state)

    drift_pending = pending_drift_exists(resolved_state)
    drift_action = decide_drift_heal(
        active_leases=active_leases,
        drift_pending=drift_pending,
    ).value

    candidates = enumerate_backend_candidates(workspace_fp=workspace_fp)
    verify = _select_verify_candidate(candidates, active_leases=active_leases)

    if verify is None and retry_after_apply and active_leases == 0 and drift_pending:
        apply_result = apply_pending_drift_if_idle(
            monorepo_root=root, state_dir=resolved_state
        )
        if apply_result.action == "applied":
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
    from mux_upstream_admission import read_mux_cold_attach_status  # noqa: PLC0415

    mux = read_mux_cold_attach_status()
    return {
        "muxColdAttachActive": mux["active"],
        "muxColdAttachMax": mux["maxSlots"],
        "muxColdAttachSaturated": mux["saturated"],
        "muxHandProbeAllowed": mux["handProbeAllowed"],
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
        fallback = {
            "agent_stream_lock": None,
            "desktop_approval_lock": None,
            "active_tests": [],
            "active_test_count": 0,
            "snapshot_error": str(exc),
        }
        return fallback, [
            "E2E_PARALLEL_ACTIVE: unavailable",
            f"E2E_PARALLEL_SNAPSHOT_ERROR={exc}",
        ]
    finally:
        if inserted:
            sys.path.remove(support_text)


def _lock_holder_active(
    parallel_snapshot: dict[str, object] | None,
    key: str,
) -> bool:
    if parallel_snapshot is None:
        return False
    holder = parallel_snapshot.get(key)
    if not isinstance(holder, dict):
        return False
    pid = holder.get("pid")
    return isinstance(pid, int) and pid > 0


def _compute_queue_state(
    *,
    live_agent_shpoib_count: int,
    mux_fields: dict[str, object],
    parallel_snapshot: dict[str, object] | None,
) -> tuple[bool, list[str]]:
    from dev_gate_contract import LIVE_SHPOIB_MAX_CONCURRENT  # noqa: PLC0415

    reasons: list[str] = []
    if bool(mux_fields.get("muxColdAttachSaturated", False)):
        reasons.append("mux_cold_attach")
    if live_agent_shpoib_count >= LIVE_SHPOIB_MAX_CONCURRENT:
        reasons.append("wave_cap")
    if _lock_holder_active(parallel_snapshot, "agent_stream_lock"):
        reasons.append("shared_hot_stream_lock")
    if _lock_holder_active(parallel_snapshot, "desktop_approval_lock"):
        reasons.append("desktop_approval_lock")
    return len(reasons) > 0, reasons


def _cap_headroom_fields(
    *,
    lease_counts: object,
    mux_fields: dict[str, object],
    active_test_count: int,
    parallel_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    from dev_gate_contract import (  # noqa: PLC0415
        LIVE_SHARED_HOT_MAX_CONCURRENT,
        LIVE_SHPOIB_MAX_CONCURRENT,
        MUX_COLD_ATTACH_SLOTS,
    )
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
        )
    )
    mux_active = int(mux_fields.get("muxColdAttachActive", 0))
    mux_max = int(mux_fields.get("muxColdAttachMax", MUX_COLD_ATTACH_SLOTS))
    queue_expected, queue_reasons = _compute_queue_state(
        live_agent_shpoib_count=counts.live_agent_shpoib,
        mux_fields=mux_fields,
        parallel_snapshot=parallel_snapshot,
    )
    return {
        "waveLeasesActive": counts.total,
        "liveAgentShpoibLeases": counts.live_agent_shpoib,
        "liveAgentSharedHotLeases": counts.live_agent_shared_hot,
        "readPageLeases": counts.read_page,
        "shpoibMaxConcurrent": LIVE_SHPOIB_MAX_CONCURRENT,
        "sharedHotMaxConcurrent": LIVE_SHARED_HOT_MAX_CONCURRENT,
        "muxColdAttachRemaining": max(0, mux_max - mux_active),
        "activeTestCount": active_test_count,
        "parallelQueueExpected": queue_expected,
        "queueReasons": queue_reasons,
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
        f"live_agent_shpoib={headroom['liveAgentShpoibLeases']}/{headroom['shpoibMaxConcurrent']} "
        f"read_page_leases={headroom['readPageLeases']} "
        f"wave_leases_total={headroom['waveLeasesActive']} "
        f"shared_hot_max={headroom['sharedHotMaxConcurrent']} "
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
    shpoib_max = int(headroom["shpoibMaxConcurrent"])
    reasons = headroom.get("queueReasons", [])
    reason_str = (
        ",".join(str(item) for item in reasons)
        if isinstance(reasons, list) and reasons
        else "unknown"
    )
    return (
        "E2E_QUEUE_HUMAN: "
        f"reason={reason_str} "
        f"(live_agent_shpoib={headroom['liveAgentShpoibLeases']}/{shpoib_max} "
        f"read_page_leases={headroom['readPageLeases']} "
        f"wave_leases_total={headroom['waveLeasesActive']} "
        f"active_tests={active_test_count}). "
        "New ./myrm test runs AUTO-QUEUE in ADMIT (≤900s). "
        "NEVER stop/kill other pytest. "
        "Progress on stderr: E2E capacity [E2E_LEASE_WAIT] / "
        "E2E_SHPOIB_BOOTSTRAP_PROGRESS every 30s. "
        "Do NOT pipe './myrm test' to tail|head — hides progress."
    )


def _compute_next_action(
    ctx: E2eApiContext,
    *,
    headroom: dict[str, object],
    active_tests: list[dict[str, object]],
    mux_fields: dict[str, object],
) -> str:
    from dev_gate_contract import (  # noqa: PLC0415
        LIVE_AGENT_PYTEST_WALL_CAP_SEC,
        LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
    )

    for row in active_tests:
        body_elapsed = row.get("body_elapsed_sec")
        if isinstance(body_elapsed, (int, float)):
            if float(body_elapsed) >= float(LIVE_SINGLE_TEST_WALL_CLOCK_SEC):
                return "FAIL_FAST"
        process_elapsed = row.get("elapsed_sec")
        if isinstance(process_elapsed, (int, float)):
            if float(process_elapsed) >= float(LIVE_AGENT_PYTEST_WALL_CAP_SEC):
                return "FAIL_FAST"
    if headroom.get("parallelQueueExpected") is True:
        return "QUEUE"
    if ctx.blocked and not ctx.epoch_match:
        return "SHPOIB_OR_VERIFY_API"
    if mux_fields.get("muxColdAttachSaturated") is True:
        return "QUEUE"
    if ctx.drift_pending and ctx.active_leases == 0:
        return "RESTART_WHEN_IDLE"
    if active_tests:
        return "PARALLEL_OK"
    return "READY"


def _format_agent_decision_human(
    *,
    ctx: E2eApiContext,
    headroom: dict[str, object],
    active_tests: list[dict[str, object]],
    mux_fields: dict[str, object],
) -> list[str]:
    next_action = _compute_next_action(
        ctx,
        headroom=headroom,
        active_tests=active_tests,
        mux_fields=mux_fields,
    )
    lines = [
        f"NEXT_ACTION={next_action}",
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
        if not current_node and body_elapsed is None:
            continue
        pid = row.get("pid")
        parts = [f"pid={pid}"]
        if current_node:
            parts.append(f"current_node={current_node}")
        if isinstance(body_elapsed, (int, float)):
            parts.append(f"body_elapsed={float(body_elapsed):.0f}s")
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
        active_test_count=int(resolved_parallel.get("active_test_count", 0)),
        parallel_snapshot=resolved_parallel,
    )
    payload = asdict(ctx)
    payload["candidates"] = [_candidate_to_dict(item) for item in ctx.candidates]
    payload["verifyTarget"] = ctx.verify_api_base
    payload.update(resolved_mux)
    payload["parallelSnapshot"] = resolved_parallel
    payload["capHeadroom"] = headroom
    payload["leaseLiveness"] = lease_liveness_to_dict(liveness_rows)
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
    active_count = int(resolved_parallel.get("active_test_count", 0))
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
        f"epoch_match={match_note} wave_leases_total={ctx.active_leases} source={ctx.source} "
        f"blocked={'yes' if ctx.blocked else 'no'})\n"
    )
    sys.stdout.write(f"WORKSPACE_FINGERPRINT={ctx.workspace_fingerprint}\n")
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
    active_test_count = int(parallel_snapshot.get("active_test_count", 0))
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
    sys.stdout.write(
        _format_cap_headroom_human(
            lease_counts=counts,
            mux_fields=mux_fields,
            active_test_count=active_test_count,
            parallel_snapshot=parallel_snapshot,
        )
        + "\n"
    )
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ctx_json = sub.add_parser("context-json")
    ctx_json.set_defaults(handler=_cmd_context_json)

    ctx_human = sub.add_parser("context-human")
    ctx_human.set_defaults(handler=_cmd_context_human)

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
