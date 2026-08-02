"""Chrome E2E readiness SSOT — unified predicate for ready/launch-check/context/preflight.

[INPUT]
- e2e_api_verify.resolve_e2e_api_context + cluster snapshots (POS: Agent SSOT)

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
import sys
from dataclasses import dataclass
from typing import Final, Literal

from e2e_api_verify import (
    E2eApiContext,
    _cap_headroom_fields,
    _compute_next_action,
    _load_parallel_runtime_snapshot,
    _mux_context_fields,
    resolve_e2e_api_context,
)

ReadinessStatus = Literal["READY", "WAIT", "FAIL"]

_LAUNCH_ALLOWED_ACTIONS: Final[frozenset[str]] = frozenset(
    {"READY", "PARALLEL_OK", "QUEUE"}
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
    if next_action == "OBSERVABILITY_UNKNOWN":
        return "WAIT"
    if ctx_blocked or next_action in (
        "SHPOIB_OR_VERIFY_API",
        "ADMIT_STACK_HEAL_WAIT",
        "RESTART_WHEN_IDLE",
        "QUEUE",
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
    if next_action == "FAIL_FAST":
        return (
            "cluster has hung chrome_e2e peer — run ./myrm e2e-context; "
            "do not stop other pytest"
        )
    if ctx.blocked:
        blocked_reason = ctx.blocked_reason.strip() or "verification plane blocked"
        return f"{blocked_reason}; NEXT_ACTION={next_action}"
    if next_action == "QUEUE":
        return (
            "PRIVATE ADMIT queue expected; launch may defer — do not stop other pytest"
        )
    if next_action == "ADMIT_STACK_HEAL_WAIT":
        return "shared stack heal in ADMIT — wait for peer recovery"
    if next_action == "RESTART_WHEN_IDLE":
        return "pending drift — restart when wave idle"
    if next_action == "SHPOIB_OR_VERIFY_API":
        return "no epoch-matched backend — verify-api or SHPOIB seed required"
    if next_action == "PARALLEL_OK":
        return "parallel chrome_e2e active; stack attach allowed"
    return "cluster ready for chrome_e2e launch"


def _launch_allowed(*, next_action: str, ctx: E2eApiContext) -> bool:
    if next_action == "FAIL_FAST":
        return False
    if next_action in _LAUNCH_ALLOWED_ACTIONS:
        return True
    # R219-D: blocked epoch + parallel peers must enter ADMIT/queue in test.sh — not hard deny.
    if next_action == "ADMIT_STACK_HEAL_WAIT":
        return True
    if ctx.blocked:
        return False
    return False


def _ready_chrome_full(
    *, next_action: str, ctx: E2eApiContext, mux_fields: dict[str, object]
) -> bool:
    if ctx.blocked or not ctx.epoch_match:
        return False
    if next_action in ("FAIL_FAST", "SHPOIB_OR_VERIFY_API", "RESTART_WHEN_IDLE"):
        return False
    if mux_fields.get("muxColdAttachSaturated") is True:
        return False
    if not mux_fields.get("muxSnapshotAvailable", True):
        return False
    return True


def _launch_force_bypass_enabled() -> bool:
    return os.environ.get("MYRM_E2E_LAUNCH_FORCE", "").strip() == "1" or (
        os.environ.get("E2E_SIGNOFF", "").strip() == "1"
    )


def evaluate_chrome_e2e_readiness(
    ctx: E2eApiContext,
    *,
    headroom: dict[str, object],
    active_tests: list[dict[str, object]],
    mux_fields: dict[str, object],
    parallel_snapshot: dict[str, object] | None = None,
) -> ChromeE2eReadinessVerdict:
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
            epoch_match=ctx.epoch_match,
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
            epoch_match=ctx.epoch_match,
        )
    next_action = _compute_next_action(
        ctx,
        headroom=headroom,
        active_tests=active_tests,
        mux_fields=mux_fields,
        parallel_snapshot=snapshot,
    )
    if ctx.blocked and next_action in ("READY", "PARALLEL_OK"):
        next_action = "SHPOIB_OR_VERIFY_API"
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
        epoch_match=ctx.epoch_match,
    )


def _build_readiness_verdict() -> ChromeE2eReadinessVerdict:
    from e2e_lease_liveness import (
        load_wave_snapshot,
        wave_lease_counts,
    )  # noqa: PLC0415

    ctx = resolve_e2e_api_context()
    mux_fields = _mux_context_fields()
    parallel_snapshot, _lines = _load_parallel_runtime_snapshot()
    counts = wave_lease_counts(load_wave_snapshot())
    active_tests_raw = parallel_snapshot.get("active_tests")
    active_tests = (
        [item for item in active_tests_raw if isinstance(item, dict)]
        if isinstance(active_tests_raw, list)
        else []
    )
    active_test_count = int(parallel_snapshot.get("active_test_count", 0))
    headroom = _cap_headroom_fields(
        lease_counts=counts,
        mux_fields=mux_fields,
        active_test_count=active_test_count,
        parallel_snapshot=parallel_snapshot,
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
        "run ./myrm e2e-context; maintainer override MYRM_E2E_LAUNCH_FORCE=1 "
        "(do not stop other pytest)"
    )


def _cmd_emit(_args: argparse.Namespace) -> int:
    verdict = resolve_chrome_e2e_readiness()
    sys.stdout.write(format_shell_tokens(verdict) + "\n")
    if verdict.status == "FAIL":
        return 2
    return 0


def _cmd_check(_args: argparse.Namespace) -> int:
    verdict = resolve_chrome_e2e_readiness()
    if verdict.launch_allowed:
        sys.stdout.write("E2E_LAUNCH_OK\n")
        sys.stdout.write(f"E2E_READINESS={verdict.token}\n")
        return 0
    denial = launch_denial_line(verdict)
    if denial:
        sys.stderr.write(denial + "\n")
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
