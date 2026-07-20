"""Human-readable E2E capacity wait messages (Dev Gate UX layer).

[INPUT] dev_gate_contract.py (POS: Dev Gate v2 numeric caps SSOT)
[OUTPUT] format_* helpers + CLI: lease/mux wait lines, signoff phase banners
[POS] Operator-facing stderr UX for parallel backpressure waits. Preserves machine
tokens (E2E_LEASE_WAIT, E2E_MUX_ADMISSION_WAIT) for grep/tests; does not change caps.
"""

from __future__ import annotations

import argparse
import sys
from typing import Final

SIGNOFF_CORE_PHASE_ORDER: Final[tuple[str, ...]] = (
    "ready_chrome",
    "static_dev_tests",
    "node_mux_tests",
    "harness_editable_gate",
    "wave_quiesce_live_leases",
    "chrome_live_preflight",
    "chrome_e2e_matrix",
)

SIGNOFF_PHASE_DESCRIPTIONS: Final[dict[str, str]] = {
    "ready_chrome": "Warm up Chrome hot pool · 预热 Chrome 热池",
    "static_dev_tests": "Static dev gate · 静态门禁",
    "node_mux_tests": "Mux node tests · Mux 节点测试",
    "harness_editable_gate": "Harness editable check · Harness 可编辑校验",
    "wave_quiesce_live_leases": "Wait for dead leases only · 仅等待死 lease",
    "chrome_live_preflight": "Chrome attach preflight · Chrome 附着预检",
    "chrome_e2e_matrix": "Chrome E2E matrix (37 cases) · Chrome 矩阵",
    "chrome_e2e_desktop_preflight": "Desktop preflight · 桌面预检",
    "chrome_e2e_desktop_macos": "Desktop approval E2E · 桌面审批 E2E",
    "chrome_e2e_stress_xdist4": "Stress xdist4 · 压力 xdist4",
    "chrome_e2e_fault_sigterm_goal_cache": "Fault sigterm goal+cache · 故障注入",
}


def signoff_phase_label(phase_name: str) -> str:
    normalized = phase_name.strip()
    description = SIGNOFF_PHASE_DESCRIPTIONS.get(
        normalized, f"Release check · {normalized}"
    )
    if normalized in SIGNOFF_CORE_PHASE_ORDER:
        index = SIGNOFF_CORE_PHASE_ORDER.index(normalized) + 1
        total = len(SIGNOFF_CORE_PHASE_ORDER)
        return f"Step {index}/{total} · {description}"
    return description


def format_signoff_phase_start(phase_name: str, *, elapsed_sec: int = 0) -> str:
    label = signoff_phase_label(phase_name)
    if elapsed_sec > 0:
        return f"SIGNOFF_PHASE: {label} · elapsed={elapsed_sec}s"
    return f"SIGNOFF_PHASE: {label}"


def format_lease_wait(
    *,
    lane: str,
    elapsed_sec: int,
    wait_sec: int,
    poll_sec: int,
) -> str:
    return (
        f"E2E capacity [E2E_LEASE_WAIT]: lane={lane} · waiting · "
        f"{elapsed_sec}s/{wait_sec}s · retry in {poll_sec}s · "
        "do not stop other tests · 勿停止其他测试"
    )


def format_lease_wait_timeout(*, lane: str, wait_sec: int) -> str:
    return (
        f"E2E capacity [E2E_LEASE_WAIT_TIMEOUT]: lane={lane} · "
        f"waited {wait_sec}s · run ./myrm wave status · "
        "do not kill foreign pytest"
    )


def format_mux_wait(
    *,
    lane: str,
    elapsed_sec: int,
    wait_sec: int,
    poll_sec: int,
    cap: int,
    active: int,
) -> str:
    return (
        f"E2E capacity [E2E_MUX_ADMISSION_WAIT]: lane={lane} · "
        f"mux {active}/{cap} · {elapsed_sec}s/{wait_sec}s · retry in {poll_sec}s · "
        "do not stop other tests · 勿停止其他测试"
    )


def format_mux_wait_timeout(*, lane: str, wait_sec: int, cap: int) -> str:
    return (
        f"E2E capacity [E2E_MUX_ADMISSION_WAIT_TIMEOUT]: lane={lane} · "
        f"waited {wait_sec}s · cap={cap} · run ./myrm doctor --chrome if stuck"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Format Dev Gate E2E capacity UX messages")
    sub = parser.add_subparsers(dest="command", required=True)

    lease_wait = sub.add_parser("lease-wait")
    lease_wait.add_argument("--lane", required=True)
    lease_wait.add_argument("--elapsed", type=int, required=True)
    lease_wait.add_argument("--wait-sec", type=int, required=True)
    lease_wait.add_argument("--poll-sec", type=int, required=True)

    lease_timeout = sub.add_parser("lease-timeout")
    lease_timeout.add_argument("--lane", required=True)
    lease_timeout.add_argument("--wait-sec", type=int, required=True)

    mux_wait = sub.add_parser("mux-wait")
    mux_wait.add_argument("--lane", required=True)
    mux_wait.add_argument("--elapsed", type=int, required=True)
    mux_wait.add_argument("--wait-sec", type=int, required=True)
    mux_wait.add_argument("--poll-sec", type=int, required=True)
    mux_wait.add_argument("--cap", type=int, required=True)
    mux_wait.add_argument("--active", type=int, required=True)

    mux_timeout = sub.add_parser("mux-timeout")
    mux_timeout.add_argument("--lane", required=True)
    mux_timeout.add_argument("--wait-sec", type=int, required=True)
    mux_timeout.add_argument("--cap", type=int, required=True)

    signoff_label = sub.add_parser("signoff-label")
    signoff_label.add_argument("--phase", required=True)
    signoff_label.add_argument("--elapsed", type=int, default=0)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "lease-wait":
        print(
            format_lease_wait(
                lane=args.lane,
                elapsed_sec=args.elapsed,
                wait_sec=args.wait_sec,
                poll_sec=args.poll_sec,
            )
        )
    elif args.command == "lease-timeout":
        print(format_lease_wait_timeout(lane=args.lane, wait_sec=args.wait_sec))
    elif args.command == "mux-wait":
        print(
            format_mux_wait(
                lane=args.lane,
                elapsed_sec=args.elapsed,
                wait_sec=args.wait_sec,
                poll_sec=args.poll_sec,
                cap=args.cap,
                active=args.active,
            )
        )
    elif args.command == "mux-timeout":
        print(
            format_mux_wait_timeout(lane=args.lane, wait_sec=args.wait_sec, cap=args.cap)
        )
    elif args.command == "signoff-label":
        print(format_signoff_phase_start(args.phase, elapsed_sec=args.elapsed))
    else:
        raise SystemExit(f"unknown command: {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
