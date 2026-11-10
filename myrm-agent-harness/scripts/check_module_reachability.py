#!/usr/bin/env python3
"""Module-reachability gate: every unit must have a production consumer.

Every Python file below a top-level directory of the harness package must be used by production
code, in this package or by live code of the server tree, except the files under
``HARNESS_ROOT_DIRS`` (the public ``api/`` surface and the browser domain-skill scripts), which
are roots rather than units. ``--server`` audits the server tree's own files the same way, with
``SERVER_ROOT_DIRS`` as its roots. A unit that exists, passes its
own tests and is re-exported from an ``__init__.py`` but is called by nothing is a dead feature
path and fails the gate. There is no allowlist: wire the unit into a production call site (covered
by a test that drives the real entry point) or delete it.

With ``--base REV`` the gate switches to diff mode: only units that are dead now and were not dead at
the merge-base with ``REV`` fail (see ``module_reachability_diff``). The harness package, the server
tree and ``pyproject.toml`` are all read at that merge-base, so a unit orphaned by deleting its last
server consumer is caught too. It still has no baseline or allowlist, and it fails closed when the
base cannot be established.

Usage:
    python scripts/check_module_reachability.py                  # Harness units (absolute mode)
    python scripts/check_module_reachability.py --base origin/main  # Only units a change leaves unwired (CI mode)
    python scripts/check_module_reachability.py --server         # Server units
    python scripts/check_module_reachability.py --require-server # Fail when the server tree is absent
    python scripts/check_module_reachability.py --server-root DIR  # Server ``app`` package (default: monorepo sibling)
    python scripts/check_module_reachability.py --json           # Machine-readable output

Exit codes:
    0: Every unit is reachable (or the check was skipped / not evaluable, loudly)
    1: One or more unreachable units
    2: Internal error (nothing was scanned, or the --base revision could not be established)
    3: Server tree missing while it is required (--server or --require-server)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import tomllib
from pathlib import Path

_HARNESS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HARNESS_ROOT))

from scripts.module_reachability_diff import (  # noqa: E402
    Analyse,
    BaseUnavailableError,
    DiffResult,
    Locate,
    diff_against,
)
from scripts.module_reachability_engine import PUBLIC_SURFACE, Consumer, Report, Unit, analyze  # noqa: E402
from scripts.tool_registry_config import HARNESS_SRC, SERVER_SRC  # noqa: E402

HARNESS_PYPROJECT = _HARNESS_ROOT / "pyproject.toml"

# Harness directories whose files are roots rather than units: the browser domain-skill scripts are
# run from the directory listing of ``DomainSkillStore`` (domain_skills/store.py), never imported.
HARNESS_ROOT_DIRS = (PUBLIC_SURFACE, "toolkits/browser/domain_skills/builtin")

# Server directories whose files are roots rather than units, because the engine cannot see how
# they are loaded: channel providers are imported by module name from the provider registry
# (channels/providers/registry.py) and startup/ is imported by the ``run.py`` entry point, which
# lives outside the ``app`` tree.
SERVER_ROOT_DIRS = ("channels/providers", "startup")


def project_entry_points(pyproject: Path) -> tuple[str, ...]:
    """``module:attr`` targets of ``[project.scripts]`` (installed console scripts are roots)."""
    if not pyproject.is_file():
        return ()
    scripts = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {}).get("scripts", {})
    return tuple(str(target) for target in scripts.values())


def _working_tree(path: Path) -> Path:
    return path


def _server_analyser(server_root: Path) -> Analyse:
    return lambda locate: analyze(locate(server_root), root_dirs=SERVER_ROOT_DIRS)


def _harness_analyser(server_root: Path) -> Analyse:
    """Harness analysis whose consumer tree and entry points come from the tree being analysed."""

    def analyse(locate: Locate) -> Report:
        return analyze(
            locate(HARNESS_SRC),
            [Consumer(locate(server_root), SERVER_ROOT_DIRS)],
            project_entry_points(locate(HARNESS_PYPROJECT)),
            root_dirs=HARNESS_ROOT_DIRS,
        )

    return analyse


def _format_units(units: tuple[Unit, ...]) -> list[str]:
    return [f"  {unit.key}  ({unit.lines} lines)" for unit in units]


def _print_report(
    report: Report,
    failing: tuple[Unit, ...],
    label: str,
    elapsed: float,
    *,
    verbose: bool,
    diff: DiffResult | None,
    base_rev: str | None,
) -> None:
    through_server = f", {len(report.server_only)} reachable only through the server tree" if label == "harness" else ""
    print(
        f"module reachability [{label}]: {len(report.units)} units in {report.files_scanned} files"
        f"{through_server} ({elapsed:.1f}s CPU)."
    )
    if verbose and report.server_only:
        print("Server-only units:")
        print("\n".join(_format_units(report.server_only)))
    if diff is not None:
        print(
            f"diff mode: merge-base {diff.base[:10]} with {base_rev}; "
            f"{diff.preexisting} unit(s) already dead there are not counted."
        )
    if not failing:
        print("OK: " + ("every unit has a production consumer." if diff is None else "no unit was left unwired."))
        return
    verdict = "have no production consumer" if diff is None else "were left without a production consumer"
    print(f"FAIL: {len(failing)} unit(s) {verdict}:", file=sys.stderr)
    print("\n".join(_format_units(failing)), file=sys.stderr)
    print(
        "Wire each unit into a production call site covered by a test that drives the real entry point, "
        "or delete it. A re-export in an __init__.py is not a consumer and there is no allowlist.",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Every unit must have a production consumer.")
    parser.add_argument("--require-server", action="store_true", help="Fail when the server tree is absent")
    parser.add_argument("--server", action="store_true", help="Audit the server tree's own units")
    parser.add_argument("--server-root", type=Path, default=SERVER_SRC, help="Server `app` package directory")
    parser.add_argument(
        "--base",
        metavar="REV",
        help="Diff mode: fail only for units dead now that were not dead at the merge-base with REV",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--verbose", action="store_true", help="Also list server-only units")
    args = parser.parse_args(argv)

    server_root: Path = args.server_root
    if not server_root.is_dir():
        if args.server or args.require_server:
            print(f"ERROR: server tree not found at {server_root}", file=sys.stderr)
            return 3
        print(
            f"module reachability: NOT EVALUATED - server tree not found at {server_root}; "
            "units consumed only by the server cannot be told apart from dead ones in a standalone checkout."
        )
        return 0

    started = time.process_time()
    if args.server:
        label, inputs, analyse = "server", [server_root], _server_analyser(server_root)
    else:
        label, inputs = "harness", [HARNESS_SRC, HARNESS_PYPROJECT, server_root]
        analyse = _harness_analyser(server_root)

    report = analyse(_working_tree)
    elapsed = time.process_time() - started
    if not report.units:
        print("ERROR: no engine units found, nothing was scanned.", file=sys.stderr)
        return 2

    diff: DiffResult | None = None
    failing = report.dead
    if args.base:
        try:
            diff = diff_against(report, inputs, args.base, analyse)
        except BaseUnavailableError as exc:
            print(f"ERROR: cannot compare against --base {args.base}: {exc}", file=sys.stderr)
            return 2
        failing = diff.introduced

    if args.json:
        print(
            json.dumps(
                {
                    "tree": label,
                    "units": len(report.units),
                    "base": diff.base if diff else None,
                    "dead": [{"unit": unit.key, "lines": unit.lines} for unit in failing],
                    "server_only": [{"unit": unit.key, "lines": unit.lines} for unit in report.server_only],
                },
                indent=2,
            )
        )
    else:
        _print_report(report, failing, label, elapsed, verbose=args.verbose, diff=diff, base_rev=args.base)
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
