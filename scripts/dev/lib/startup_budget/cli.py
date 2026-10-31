"""``python -m startup_budget check|measure``: the gate and its stub-pricing companion.

[INPUT]
  argv: --samples N (default 3), measure only: --stub MODULE (repeatable)
  startup_budget.runner::take_samples (POS: process boundary; one cold child interpreter per sample)
  startup_budget.budget::BUDGET / best / evaluate / render (POS: pure policy; the limits and the
  judging rule)

[OUTPUT]
  check: a STARTUP_BUDGET line (best sample vs limits); exit 0 within budget, 14 over budget,
  15 not measurable.
  measure: one line per sample plus the best; always exit 0 unless not measurable (15).

[POS]
  Thin entry point so a maintainer and the pytest gate read the same numbers. ``measure --stub``
  prices a lazy-load idea on the full app: run it without and with the stub and compare the
  best samples; differences below ~1 s CPU are within the noise of a loaded machine.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from startup_budget import budget, runner

EXIT_OK = 0
EXIT_OVER_BUDGET = 14
EXIT_UNMEASURABLE = 15
DEFAULT_SAMPLES = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="startup_budget")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "measure"):
        command = sub.add_parser(name)
        command.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
        if name == "measure":
            command.add_argument(
                "--stub", action="append", default=[], metavar="MODULE"
            )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.samples < 1:
        print("--samples must be at least 1", file=sys.stderr)
        return EXIT_UNMEASURABLE
    stubs = getattr(args, "stub", [])
    try:
        samples = runner.take_samples(args.samples, stubs)
    except runner.ProbeError as exc:
        print(f"STARTUP_BUDGET unmeasurable: {exc}", file=sys.stderr)
        return EXIT_UNMEASURABLE

    best = budget.best(samples)
    if args.command == "measure":
        for sample in samples:
            print(budget.render(sample))
        print(f"best of {len(samples)}: {budget.render(best)}")
        return EXIT_OK

    print(budget.render(best))
    findings = budget.evaluate(best)
    for finding in findings:
        print(f"STARTUP_BUDGET_EXCEEDED {finding.render()}", file=sys.stderr)
    return EXIT_OVER_BUDGET if findings else EXIT_OK
