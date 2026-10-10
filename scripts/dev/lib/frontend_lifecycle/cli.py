"""CLI glue for dev-stack.sh: ``python -m frontend_lifecycle admit|journal|report``.

[INPUT]
  argv from dev-stack.sh (reason, port, url, state/pid/log paths)

[OUTPUT]
  admit exit codes: 0 = kill allowed, 10 = frontend healthy (do not restart), 11 = denied
  (still compiling / not proven dead); a STACK_RESTART_* line on stderr.
  journal: appends a kill record naming the target pids.
  report: read-only comparison of journal kills with SIGTERMs in frontend.log (see report.py).

[POS]
  Thin process boundary so Bash restart paths consult the same policy as the unit tests.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from frontend_lifecycle import journal, report
from frontend_lifecycle.gate import GateContext, admit
from frontend_lifecycle.policy import Policy, Reason, Verdict

EXIT_ALLOW = 0
EXIT_HEALTHY = 10
EXIT_DENIED = 11
_VERDICT_EXIT = {
    Verdict.ALLOW: EXIT_ALLOW,
    Verdict.HEALTHY: EXIT_HEALTHY,
    Verdict.DENY: EXIT_DENIED,
}
_VERDICT_LABEL = {
    Verdict.ALLOW: "STACK_RESTART_ADMIT",
    Verdict.HEALTHY: "STACK_RESTART_HEALTHY",
    Verdict.DENY: "STACK_RESTART_DENIED",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="frontend_lifecycle")
    sub = parser.add_subparsers(dest="command", required=True)
    reasons = [reason.value for reason in Reason]

    admit_cmd = sub.add_parser(
        "admit", help="decide whether the frontend may be killed"
    )
    admit_cmd.add_argument("--reason", choices=reasons, required=True)
    admit_cmd.add_argument("--port", type=int, required=True)
    admit_cmd.add_argument("--url", required=True)
    admit_cmd.add_argument("--state-dir", type=Path, required=True)
    admit_cmd.add_argument("--pid-file", type=Path, required=True)
    admit_cmd.add_argument("--log-file", type=Path, required=True)

    kill_cmd = sub.add_parser("journal", help="record an executed kill")
    kill_cmd.add_argument("--reason", choices=reasons, required=True)
    kill_cmd.add_argument("--state-dir", type=Path, required=True)
    kill_cmd.add_argument("--port", type=int, required=True)
    kill_cmd.add_argument("--pids", default="")

    report_cmd = sub.add_parser(
        "report", help="read-only: journal kills vs SIGTERMs in frontend.log"
    )
    report_cmd.add_argument("--state-dir", type=Path, required=True)
    report_cmd.add_argument("--log-file", type=Path, required=True)
    report_cmd.add_argument(
        "--mark", action="store_true", help="restart the window after reporting"
    )
    return parser


def _report(args: argparse.Namespace) -> int:
    now = time.time()
    baseline = report.load_baseline(args.state_dir)
    if baseline is None:
        report.save_baseline(args.state_dir, args.log_file, now)
        print("FRONTEND_RESTART_REPORT baseline set now; run again later to compare")
        return 0
    print(report.render(report.build(args.state_dir, args.log_file, baseline, now)))
    if args.mark:
        report.save_baseline(args.state_dir, args.log_file, now)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "report":
        return _report(args)
    if args.command == "journal":
        journal.append(
            args.state_dir,
            "kill",
            {
                "reason": args.reason,
                "port": args.port,
                "pids": [token for token in args.pids.split() if token.isdigit()],
            },
        )
        return 0
    ctx = GateContext(
        port=args.port,
        url=args.url,
        state_dir=args.state_dir,
        pid_file=args.pid_file,
        log_file=args.log_file,
    )
    decision = admit(Reason(args.reason), ctx, Policy.from_env())
    print(
        f"{_VERDICT_LABEL[decision.verdict]}: reason={args.reason} rule={decision.rule}"
        f"{' ' + decision.detail if decision.detail else ''}",
        file=sys.stderr,
    )
    return _VERDICT_EXIT[decision.verdict]


if __name__ == "__main__":
    raise SystemExit(main())
