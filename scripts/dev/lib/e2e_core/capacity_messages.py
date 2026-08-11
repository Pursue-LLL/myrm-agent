"""Human-readable E2E capacity wait messages (Dev Gate UX layer).

[OUTPUT] format_* helpers + CLI: lease/mux wait lines for parallel backpressure.
Preserves machine tokens (E2E_LEASE_WAIT, E2E_MUX_ADMISSION_WAIT) for grep/tests.
"""

from __future__ import annotations

import argparse
import sys


def format_lease_wait(
    *,
    lane: str,
    elapsed_sec: int,
    wait_sec: int,
    poll_sec: int,
) -> str:
    return (
        f"E2E capacity [E2E_LEASE_WAIT]: lane={lane} "
        f"waiting for slot ({elapsed_sec}s/{wait_sec}s, poll={poll_sec}s) — "
        "do not stop other tests"
    )


def format_lease_wait_timeout(*, lane: str, wait_sec: int) -> str:
    return (
        f"E2E capacity [E2E_LEASE_WAIT_TIMEOUT]: lane={lane} "
        f"no slot after {wait_sec}s — do not stop other tests"
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
        f"E2E capacity [E2E_MUX_ADMISSION_WAIT]: lane={lane} "
        f"mux {active}/{cap} ({elapsed_sec}s/{wait_sec}s, poll={poll_sec}s) — "
        "do not stop other tests"
    )


def format_mux_wait_timeout(*, lane: str, wait_sec: int, cap: int) -> str:
    return (
        f"E2E capacity [E2E_MUX_ADMISSION_WAIT_TIMEOUT]: lane={lane} "
        f"mux cap {cap} held for {wait_sec}s — do not stop other tests"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="E2E capacity wait message formatter")
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
    else:
        raise SystemExit(f"unknown command: {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
