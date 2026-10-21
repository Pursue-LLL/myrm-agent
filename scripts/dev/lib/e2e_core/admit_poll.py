"""R141: ADMIT/bootstrap wait loops — progress tokens + phase budget (bash + Python SSOT)."""

from __future__ import annotations

import argparse
import sys


def touch_admit_progress(*, node: str) -> None:
    from e2e_session_runtime.lifecycle import touch_wall_progress

    touch_wall_progress(current_node=node)


def assert_admit_phase_budget(*, node: str) -> None:
    from e2e_session_runtime.lifecycle import assert_phase_budget

    assert_phase_budget(node)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E2E ADMIT wait progress + budget (R141)")
    parser.add_argument(
        "command",
        choices=("touch", "assert-budget"),
        help="touch=refresh progress token; assert-budget=fail-fast on phase cap",
    )
    parser.add_argument("--node", required=True, help="current_node label for snapshots")
    args = parser.parse_args(argv)
    if args.command == "touch":
        touch_admit_progress(node=args.node)
        return 0
    try:
        assert_admit_phase_budget(node=args.node)
    except TimeoutError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
