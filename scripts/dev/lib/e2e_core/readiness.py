"""Chrome E2E readiness SSOT — unified predicate for ready/launch-check/context/preflight.

[INPUT]
- api_verify.resolve_e2e_api_context + cluster snapshots (POS: Agent SSOT)

[OUTPUT]
- evaluate_chrome_e2e_readiness() -> ChromeE2eReadinessVerdict
- resolve_chrome_e2e_readiness() loads live cluster state
- CLI: emit (shell tokens), check (exit 0/2)

[POS]
Single readiness predicate shared by ./myrm ready --chrome, ./myrm e2e-context,
launch-check, and chrome-e2e-preflight attach gate. Prevents blocked context from
returning unconditional E2E_LAUNCH_OK.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from e2e_core.api_verify import (
    E2eApiContext,
    _cap_headroom_fields,
    _cohere_mux_observability,
    _compute_next_action,
    _load_orchestrator_observability,
    _load_parallel_runtime_snapshot,
    _mux_context_fields,
    _resolve_cap_headroom_active_test_count,
    _shared_epoch_match,
    resolve_e2e_api_context,
)

ReadinessStatus = Literal["READY", "WAIT", "FAIL"]

_LAUNCH_ALLOWED_ACTIONS: Final[frozenset[str]] = frozenset(
    {"READY", "PARALLEL_OK", "OPERATION_BACKPRESSURE", "ATTACH_CRASH_HEAL"}
)


@dataclass(frozen=True, slots=True)
class ChromeE2eReadinessVerdict:
    status: ReadinessStatus
    token: str
    reason: str
    next_action: str
    launch_allowed: bool
    attach_allowed: bool
    ready_chrome_full: bool
    blocked: bool
    epoch_match: bool


def _status_for_next_action(next_action: str, *, ctx_blocked: bool) -> ReadinessStatus:
    if next_action in ("FAIL_FAST",):
        return "FAIL"
    if next_action in (
        "OBSERVABILITY_UNKNOWN",
        "PLANE_DEGRADED",
        "PLANE_DEGRADED_DEFER",
    ):
        return "WAIT"
    if next_action in ("READY", "PARALLEL_OK", "OPERATION_BACKPRESSURE"):
        return "READY"
    if ctx_blocked or next_action in (
        "ATTACH_CRASH_HEAL",
        "SHPOIB_OR_VERIFY_API",
        "PRIVATE_EPOCH_REQUIRED",
    ):
        return "WAIT"
    return "READY"


def _token_for_verdict(
    *, status: ReadinessStatus, next_action: str, ctx: E2eApiContext
) -> str:
    if status == "READY":
        return "READY"
    if status == "FAIL":
        return f"FAIL:{next_action}"
    if ctx.blocked:
        return f"WAIT:BLOCKED_{next_action}"
    return f"WAIT:{next_action}"


def _observability_unknown(
    mux_fields: dict[str, object],
    parallel_snapshot: dict[str, object],
) -> bool:
    if mux_fields.get("muxSnapshotAvailable") is False:
        return True
    snapshot_error = parallel_snapshot.get("snapshot_error")
    return isinstance(snapshot_error, str) and bool(snapshot_error.strip())


def _reason_for_verdict(*, next_action: str, ctx: E2eApiContext) -> str:
    if next_action == "OBSERVABILITY_UNKNOWN":
        return (
            "cluster observability incomplete (muxSnapshot or parallel snapshot unavailable); "
            "do not infer idle from active_test_count=0"
        )
    if next_action in {"PLANE_DEGRADED", "PLANE_DEGRADED_DEFER"}:
        return (
            "browser data plane not observable after auto-converge; "
            "read dataPlane.agentRule — do not wait for peer; "
            "wave idle: ./myrm restart --chrome if converge failed"
        )
    if next_action == "FAIL_FAST":
        return (
            "cluster has hung chrome_e2e peer — run ./myrm e2e-context; "
            "do not stop other pytest"
        )
    if next_action == "PARALLEL_OK":
        return "parallel chrome_e2e active; healthy shared backend generation remains pinned"
    if next_action == "PRIVATE_EPOCH_REQUIRED":
        return "workspace backend code requires a PRIVATE immutable epoch; do not restart shared :8080"
    if ctx.blocked:
        blocked_reason = ctx.blocked_reason.strip() or "verification plane blocked"
        return f"{blocked_reason}; NEXT_ACTION={next_action}"
    if next_action == "OPERATION_BACKPRESSURE":
        return (
            "browser operation credits are saturated; launch remains allowed and "
            "the session receives bounded operation-level backpressure"
        )
    if next_action == "ATTACH_CRASH_HEAL":
        return (
            "shared backend is down; session remains launchable and attach preflight "
            "performs single-flight backend-only recovery"
        )
    if next_action == "SHPOIB_OR_VERIFY_API":
        return "no epoch-matched backend — verify-api or SHPOIB seed required"
    return "cluster ready for chrome_e2e launch"


def _shpoib_launch_bypass_enabled() -> bool:
    """PRIVATE chrome_e2e sets MYRM_E2E_SHPOIB before launch gate — bootstrap owns backend epoch."""
    return os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1"


def _launch_allowed(*, next_action: str, ctx: E2eApiContext) -> bool:
    if next_action == "FAIL_FAST":
        return False
    if next_action in _LAUNCH_ALLOWED_ACTIONS:
        return True
    # Workspace drift is a routing decision, not an admission blocker. The
    # generic launch-check runs before pytest collection knows the node profile;
    # test.sh subsequently routes SHARED to the healthy deployed epoch or
    # PRIVATE to an immutable workspace backend and keeps the profile-specific
    # gate fail-closed.
    if next_action == "PRIVATE_EPOCH_REQUIRED":
        return True
    # R298: SHPOIB PRIVATE tests seed isolated backend in bootstrap — shared epoch block is OK.
    if next_action == "SHPOIB_OR_VERIFY_API" and _shpoib_launch_bypass_enabled():
        return True
    if ctx.blocked:
        return False
    return False


def _ready_chrome_full(
    *, next_action: str, ctx: E2eApiContext, mux_fields: dict[str, object]
) -> bool:
    if ctx.blocked or not _shared_epoch_match(ctx):
        return False
    if next_action in (
        "FAIL_FAST",
        "ATTACH_CRASH_HEAL",
        "SHPOIB_OR_VERIFY_API",
        "PRIVATE_EPOCH_REQUIRED",
    ):
        return False
    if mux_fields.get("muxColdAttachSaturated") is True:
        return False
    return bool(mux_fields.get("muxSnapshotAvailable", True))


def _launch_force_bypass_enabled() -> bool:
    return (
        os.environ.get("MYRM_E2E_LAUNCH_FORCE", "").strip() == "1"
        or os.environ.get("MYRM_E2E_P0A_GATE", "").strip() == "1"
    )


def evaluate_chrome_e2e_readiness(
    ctx: E2eApiContext,
    *,
    headroom: dict[str, object],
    active_tests: list[dict[str, object]],
    mux_fields: dict[str, object],
    parallel_snapshot: dict[str, object] | None = None,
) -> ChromeE2eReadinessVerdict:
    shared_epoch_match = _shared_epoch_match(ctx)
    if _launch_force_bypass_enabled():
        return ChromeE2eReadinessVerdict(
            status="READY",
            token="READY",
            reason=(
                "launch-force bypass — parallel attach allowed; "
                "do not stop other pytest"
            ),
            next_action="PARALLEL_OK",
            launch_allowed=True,
            attach_allowed=True,
            ready_chrome_full=False,
            blocked=ctx.blocked,
            epoch_match=shared_epoch_match,
        )
    snapshot = parallel_snapshot if parallel_snapshot is not None else {}
    if _observability_unknown(mux_fields, snapshot):
        return ChromeE2eReadinessVerdict(
            status="WAIT",
            token="WAIT:OBSERVABILITY_UNKNOWN",
            reason=_reason_for_verdict(
                next_action="OBSERVABILITY_UNKNOWN",
                ctx=ctx,
            ),
            next_action="OBSERVABILITY_UNKNOWN",
            launch_allowed=False,
            attach_allowed=True,
            ready_chrome_full=False,
            blocked=ctx.blocked,
            epoch_match=shared_epoch_match,
        )
    next_action = _compute_next_action(
        ctx,
        headroom=headroom,
        active_tests=active_tests,
        mux_fields=mux_fields,
        parallel_snapshot=snapshot,
    )
    status = _status_for_next_action(next_action, ctx_blocked=ctx.blocked)
    token = _token_for_verdict(status=status, next_action=next_action, ctx=ctx)
    reason = _reason_for_verdict(next_action=next_action, ctx=ctx)
    return ChromeE2eReadinessVerdict(
        status=status,
        token=token,
        reason=reason,
        next_action=next_action,
        launch_allowed=_launch_allowed(next_action=next_action, ctx=ctx),
        attach_allowed=next_action != "FAIL_FAST",
        ready_chrome_full=_ready_chrome_full(
            next_action=next_action,
            ctx=ctx,
            mux_fields=mux_fields,
        ),
        blocked=ctx.blocked,
        epoch_match=shared_epoch_match,
    )


def _build_readiness_verdict() -> ChromeE2eReadinessVerdict:
    from e2e_core.lease_liveness import (
        load_wave_snapshot,
        wave_lease_counts,
    )

    ctx = resolve_e2e_api_context()
    epoch_match_flag = _shared_epoch_match(ctx)
    plane_snap = None
    plane_auto_converge = os.environ.get("MYRM_PLANE_AUTO_CONVERGE", "1").strip() != "0"
    try:
        from e2e_core.plane_health import (
            ensure_plane_before_probe,
            plane_next_action_for_snapshot,
        )

        plane_snap = ensure_plane_before_probe(
            allow_converge=plane_auto_converge,
            epoch_match=epoch_match_flag,
            drift_pending=bool(ctx.drift_pending),
        )
        plane_action = plane_next_action_for_snapshot(plane_snap)
        if plane_action == "PLANE_DEGRADED":
            return ChromeE2eReadinessVerdict(
                status="WAIT",
                token="WAIT:PLANE_DEGRADED",
                reason=plane_snap.agent_rule,
                next_action="PLANE_DEGRADED",
                launch_allowed=False,
                attach_allowed=True,
                ready_chrome_full=False,
                blocked=ctx.blocked,
                epoch_match=epoch_match_flag,
            )
    except ImportError:
        pass
    (
        browser_orchestrator,
        orchestrator_observability,
    ) = _load_orchestrator_observability()
    mux_fields = _cohere_mux_observability(
        _mux_context_fields(),
        browser_orchestrator,
    )
    parallel_snapshot, _lines = _load_parallel_runtime_snapshot()
    counts = wave_lease_counts(load_wave_snapshot())
    active_tests_raw = parallel_snapshot.get("active_tests")
    active_tests = (
        [item for item in active_tests_raw if isinstance(item, dict)]
        if isinstance(active_tests_raw, list)
        else []
    )
    from dev_gate.status import dev_gate_status

    active_test_count, observability_mismatch = _resolve_cap_headroom_active_test_count(
        parallel_snapshot,
        wave_leases_effective=counts.effective_total,
        dev_gate=dev_gate_status(),
    )
    if observability_mismatch:
        parallel_snapshot = {
            **parallel_snapshot,
            "parallel_observability_mismatch": True,
        }
    headroom = _cap_headroom_fields(
        lease_counts=counts,
        mux_fields=mux_fields,
        active_test_count=active_test_count,
        parallel_snapshot=parallel_snapshot,
        observability_mismatch=observability_mismatch,
        orchestrator_observability=orchestrator_observability,
    )
    if headroom.get("registryObservabilityUnknown") is True:
        return ChromeE2eReadinessVerdict(
            status="WAIT",
            token="WAIT:OBSERVABILITY_UNKNOWN",
            reason=_reason_for_verdict(
                next_action="OBSERVABILITY_UNKNOWN",
                ctx=ctx,
            ),
            next_action="OBSERVABILITY_UNKNOWN",
            launch_allowed=False,
            attach_allowed=True,
            ready_chrome_full=False,
            blocked=ctx.blocked,
            epoch_match=_shared_epoch_match(ctx),
        )
    return evaluate_chrome_e2e_readiness(
        ctx,
        headroom=headroom,
        active_tests=active_tests,
        mux_fields=mux_fields,
        parallel_snapshot=parallel_snapshot,
    )


def resolve_chrome_e2e_readiness() -> ChromeE2eReadinessVerdict:
    """Read-only readiness verdict — must not kill/reap/prune/restart peers (P0-A)."""
    return _build_readiness_verdict()


def resolve_chrome_e2e_readiness_stable(
    *, max_attempts: int = 3, retry_interval_sec: float = 0.1
) -> ChromeE2eReadinessVerdict:
    """Re-sample only transient observability UNKNOWN with bounded progress."""
    attempts = max(1, int(max_attempts))
    verdict = resolve_chrome_e2e_readiness()
    for attempt in range(1, attempts):
        if verdict.next_action not in {
            "OBSERVABILITY_UNKNOWN",
            "PLANE_DEGRADED",
        }:
            return verdict
        sys.stderr.write(
            f"E2E_OBSERVABILITY_RETRY: attempt={attempt + 1}/{attempts} "
            "fresh_snapshot=yes\n"
        )
        sys.stderr.flush()
        if retry_interval_sec > 0:
            time.sleep(retry_interval_sec)
        verdict = resolve_chrome_e2e_readiness()
    return verdict


def format_shell_tokens(verdict: ChromeE2eReadinessVerdict) -> str:
    lines = [
        f"MYRM_READINESS_STATUS={verdict.status}",
        f"MYRM_READINESS_TOKEN={verdict.token}",
        f"NEXT_ACTION={verdict.next_action}",
        f"E2E_LAUNCH_ALLOWED={'yes' if verdict.launch_allowed else 'no'}",
        f"E2E_ATTACH_ALLOWED={'yes' if verdict.attach_allowed else 'no'}",
        f"E2E_READY_CHROME_FULL={'yes' if verdict.ready_chrome_full else 'no'}",
        f"E2E_CONTEXT_BLOCKED={'yes' if verdict.blocked else 'no'}",
        f"E2E_EPOCH_MATCH={'yes' if verdict.epoch_match else 'no'}",
        f"MYRM_READINESS_REASON={verdict.reason}",
    ]
    return "\n".join(lines)


def launch_denial_line(verdict: ChromeE2eReadinessVerdict) -> str | None:
    if verdict.launch_allowed:
        return None
    return (
        f"E2E_LAUNCH_DENIED: {verdict.token}; {verdict.reason}; "
        "run ./myrm e2e-context json and execute agent_rule (do not force launch "
        "or stop other pytest)"
    )


def _cmd_emit(_args: argparse.Namespace) -> int:
    verdict = resolve_chrome_e2e_readiness_stable()
    sys.stdout.write(format_shell_tokens(verdict) + "\n")
    if verdict.status == "FAIL":
        return 2
    return 0


def _launch_check_wall_sec() -> float:
    from dev_gate.contract import e2e_launch_check_wall_sec

    return e2e_launch_check_wall_sec()


def _readiness_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    lib = Path(__file__).resolve().parent
    scripts_dev = lib.parent
    monorepo = scripts_dev.parent.parent
    paths = [str(lib), str(scripts_dev), str(monorepo / "scripts" / "dev")]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join([*paths, existing] if existing else paths)
    return env


def _parse_emit_fields(stdout: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        fields[key.strip()] = value.strip()
    return fields


def _cmd_check_inprocess(_args: argparse.Namespace) -> int:
    verdict = resolve_chrome_e2e_readiness_stable()
    if verdict.launch_allowed:
        sys.stdout.write("E2E_LAUNCH_OK\n")
        sys.stdout.write(f"E2E_READINESS={verdict.token}\n")
        return 0
    denial = launch_denial_line(verdict)
    if denial:
        sys.stderr.write(denial + "\n")
    return 2


def _parse_emit_launch_allowed(stdout: str) -> tuple[bool, str]:
    fields = _parse_emit_fields(stdout)
    launch_allowed = fields.get("E2E_LAUNCH_ALLOWED", "no").lower() == "yes"
    token = fields.get("MYRM_READINESS_TOKEN", "UNKNOWN")
    return launch_allowed, token


def _cmd_check(_args: argparse.Namespace) -> int:
    if os.environ.get("MYRM_E2E_LAUNCH_CHECK_SUBPROCESS", "1") != "1":
        return _cmd_check_inprocess(_args)
    wall = _launch_check_wall_sec()
    lib = Path(__file__).resolve().parent
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "e2e_core.readiness", "emit"],
            capture_output=True,
            text=True,
            timeout=wall,
            check=False,
            cwd=str(lib),
            env=_readiness_subprocess_env(),
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"E2E_LAUNCH_CHECK_TIMEOUT: readiness probe exceeded {int(wall)}s "
            "(do not stop other pytest)\n"
        )
        return 2
    launch_allowed, token = _parse_emit_launch_allowed(proc.stdout)
    if launch_allowed:
        sys.stdout.write("E2E_LAUNCH_OK\n")
        sys.stdout.write(f"E2E_READINESS={token}\n")
        return 0
    fields = _parse_emit_fields(proc.stdout)
    reason = fields.get("MYRM_READINESS_REASON", proc.stderr.strip() or "launch denied")
    sys.stderr.write(
        f"E2E_LAUNCH_DENIED: {token}; {reason}; "
        "run ./myrm e2e-context json and execute agent_rule (do not force launch "
        "or stop other pytest)\n"
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    emit = sub.add_parser("emit", help="Print shell readiness tokens on stdout")
    emit.set_defaults(handler=_cmd_emit)

    check = sub.add_parser("check", help="Exit 0 when launch allowed; else exit 2")
    check.set_defaults(handler=_cmd_check)

    ns = parser.parse_args(argv)
    handler = getattr(ns, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(ns))


if __name__ == "__main__":
    raise SystemExit(main())
