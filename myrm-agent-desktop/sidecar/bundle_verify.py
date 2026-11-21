# [INPUT]
# - bundle_inventory::first_party_modules, harness_data_files, domain_tool_scripts, HARNESS_PACKAGE,
#   CHANNEL_SDKS_NOT_SHIPPED, MONTY_REQUIRED_MODULES, MONTY_WORKER_DIR, monty_worker_name (POS: what the bundle must
#   contain and which channel SDKs stay out)
# - PyInstaller.archive.readers::CArchiveReader (POS: reads the modules archived inside the bundle's executable)
#
# [OUTPUT]
# - bundle_problems: one sentence per way the finished bundle departs from the inventory or, on macOS, from the
#   interpreter layout that keeps the first launch short
# - main: the CLI; exits 1 when the bundle has a problem
#
# [POS]
# Post-build gate: the build fails when the finished bundle lacks an inventory item (a module, a data file, the Monty
# worker that runs the agent's browser scripts), holds a channel SDK that is meant to stay out, or (macOS) ships the
# standard library's extension modules as dozens of separate files.
#
# The header is a comment because the docstring below is the CLI's --help text.
"""Check a built sidecar bundle against bundle_inventory: every first-party module and data file in, channel SDKs out.

PyInstaller answers a hidden import it cannot resolve with a warning and builds on, so a bundle that lost modules still
builds, starts and passes /health. This reads the finished bundle and fails the build instead. On macOS it also counts
the standard library's extension modules the bundle ships as separate files: macOS scans every native file of a fresh
install the first time it is loaded, so each one delays the first launch after an install or an update. A uv-managed
Python links nearly all of them into libpython; the python.org build ships dozens beside it. Run it with the server
venv's Python, which has PyInstaller's archive reader:

    python bundle_verify.py --executable <myrmagent-backend> --server-app <app dir> --harness-dir <harness package dir>
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from pathlib import Path

from bundle_inventory import (
    CHANNEL_SDKS_NOT_SHIPPED,
    HARNESS_PACKAGE,
    MONTY_REQUIRED_MODULES,
    MONTY_WORKER_DIR,
    domain_tool_scripts,
    first_party_modules,
    harness_data_files,
    monty_worker_name,
)

# How many offenders a problem names; the full list is the build's own business.
NAMED_OFFENDERS = 8

# The most standard-library extension modules (`lib-dynload/*.so`) a macOS bundle may ship as separate files. A uv-managed
# Python keeps one outside libpython (`_dbm`), the python.org build ships 59; the margin absorbs a release that splits a
# module or two out, while the fallback to the python.org layout still fails.
MAX_STDLIB_EXTENSION_FILES = 5


def bundled_module_names(executable: Path) -> set[str]:
    """Every module archived in the executable's PYZ: PyInstaller keeps them inside the executable, not as files."""
    from PyInstaller.archive.readers import CArchiveReader  # only the server venv has PyInstaller

    reader = CArchiveReader(str(executable))
    names: set[str] = set()
    for entry_name, entry in reader.toc.items():
        if entry[-1] == "z":  # an embedded PYZ archive
            names.update(reader.open_embedded_archive(entry_name).toc)
    return names


def missing_modules(expected: Iterable[str], bundled: AbstractSet[str]) -> list[str]:
    return sorted(set(expected) - bundled)


def bundled_sdks(bundled: AbstractSet[str]) -> list[str]:
    """The packages of CHANNEL_SDKS_NOT_SHIPPED of which the bundle holds a module."""
    return sorted({name.partition(".")[0] for name in bundled} & set(CHANNEL_SDKS_NOT_SHIPPED))


def missing_files(internal: Path, harness_dir: Path, files: Iterable[Path]) -> list[Path]:
    """The harness files that are not under `internal`, the bundle's data directory, at their own relative path."""
    return [file for file in files if not (internal / HARNESS_PACKAGE / file.relative_to(harness_dir)).is_file()]


def stdlib_extension_files(internal: Path) -> list[Path]:
    """The standard library's extension modules the bundle ships as files; PyInstaller keeps them under `lib-dynload`."""
    return sorted(internal.rglob("lib-dynload/*.so"))


def monty_problems(internal: Path, bundled: AbstractSet[str]) -> list[str]:
    """What keeps the agent's browser scripts from running in the bundle: the client modules or the worker executable."""
    problems: list[str] = []
    if absent := missing_modules(MONTY_REQUIRED_MODULES, bundled):
        problems.append(f"the Monty client modules are not in the bundle: {absent}")
    worker = internal / MONTY_WORKER_DIR / monty_worker_name()
    if not worker.is_file():
        problems.append(f"the Monty worker is not in the bundle at {worker.relative_to(internal).as_posix()}")
    elif not os.access(worker, os.X_OK):
        problems.append(f"the Monty worker in the bundle is not executable: {worker.relative_to(internal).as_posix()}")
    return problems


def bundle_problems(executable: Path, app_dir: Path, harness_dir: Path, *, platform: str = sys.platform) -> list[str]:
    """What is wrong with the bundle, one sentence each; empty when it is as the inventory asks (and, on macOS, lean)."""
    bundled = bundled_module_names(executable)
    problems: list[str] = []
    for package, modules in first_party_modules(app_dir, harness_dir).items():
        missing = missing_modules(modules, bundled)
        if missing:
            problems.append(
                f"{len(missing)} of {len(modules)} {package} modules are not in the bundle: {missing[:NAMED_OFFENDERS]}"
            )
    if sdks := bundled_sdks(bundled):
        problems.append(f"channel SDKs that are meant to stay out are in the bundle: {sdks}")
    internal = executable.parent / "_internal"
    shipped_as_files = {
        "domain tool scripts": domain_tool_scripts(harness_dir),
        "harness data files": harness_data_files(harness_dir),
    }
    for label, files in shipped_as_files.items():
        if absent := missing_files(internal, harness_dir, files):
            names = [file.name for file in absent[:NAMED_OFFENDERS]]
            problems.append(f"{len(absent)} of {len(files)} {label} are not in the bundle: {names}")
    problems += monty_problems(internal, bundled)
    extensions = stdlib_extension_files(internal) if platform == "darwin" else []
    if len(extensions) > MAX_STDLIB_EXTENSION_FILES:
        problems.append(
            f"{len(extensions)} standard-library extension modules ship as separate files (at most "
            f"{MAX_STDLIB_EXTENSION_FILES} expected): macOS scans each one the first time a fresh install loads it; "
            "freeze with a uv-managed Python (UV_PYTHON_PREFERENCE=only-managed), which links them into libpython"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--executable", type=Path, required=True, help="the bundle's entry executable")
    parser.add_argument("--server-app", type=Path, required=True, help="the server's app/ directory")
    parser.add_argument("--harness-dir", type=Path, required=True, help="the harness package directory the build used")
    args = parser.parse_args(argv)

    problems = bundle_problems(args.executable, args.server_app, args.harness_dir)
    for problem in problems:
        print(f"[bundle-verify] FAIL: {problem}", file=sys.stderr)
    if not problems:
        print(
            "[bundle-verify] OK: first-party modules, tool scripts, harness data files and the Monty worker are bundled; "
            "channel SDKs are not"
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
