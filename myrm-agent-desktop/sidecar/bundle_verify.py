# [INPUT]
# - bundle_inventory::first_party_modules, harness_data_files, domain_tool_scripts, HARNESS_PACKAGE,
#   CHANNEL_SDKS_NOT_SHIPPED (POS: what the bundle must contain and which channel SDKs stay out)
# - PyInstaller.archive.readers::CArchiveReader (POS: reads the modules archived inside the bundle's executable)
#
# [OUTPUT]
# - bundle_problems: one sentence per way the finished bundle departs from the inventory
# - main: the CLI; exits 1 when the bundle has a problem
#
# [POS]
# Post-build gate: the build fails when the finished bundle lacks an inventory item or holds a channel SDK that is meant
# to stay out.
#
# The header is a comment because the docstring below is the CLI's --help text.
"""Check a built sidecar bundle against bundle_inventory: every first-party module and data file in, channel SDKs out.

PyInstaller answers a hidden import it cannot resolve with a warning and builds on, so a bundle that lost modules still
builds, starts and passes /health. This reads the finished bundle and fails the build instead. Run it with the server
venv's Python, which has PyInstaller's archive reader:

    python bundle_verify.py --executable <myrmagent-backend> --server-app <app dir> --harness-dir <harness package dir>
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from pathlib import Path

from bundle_inventory import (
    CHANNEL_SDKS_NOT_SHIPPED,
    HARNESS_PACKAGE,
    domain_tool_scripts,
    first_party_modules,
    harness_data_files,
)

# How many offenders a problem names; the full list is the build's own business.
NAMED_OFFENDERS = 8


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


def bundle_problems(executable: Path, app_dir: Path, harness_dir: Path) -> list[str]:
    """What is wrong with the bundle, one sentence each; empty when it is as the inventory asks."""
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
        print("[bundle-verify] OK: first-party modules, tool scripts and harness data files are bundled; channel SDKs are not")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
