"""Harness distribution probe that does not import the harness package.

[INPUT]
- find_spec("myrm_agent_harness") (POS: locates the installed package without running its __init__)
- myrm_agent_harness/runtime/install_guard/_generated/core_ip_manifest.py (POS: core IP source list)

[OUTPUT]
- CLI: two lines on stdout — distribution mode (`source` / `compiled` / `incomplete`), package dir
- exit 1 when the package is not installed; uncaught errors propagate as a non-zero exit

[POS]
Readiness gates only need "is this the monorepo source tree". Importing
`myrm_agent_harness.runtime.install_guard.probe` runs the `myrm_agent_harness.runtime` package
init, which loads ~4000 modules (3.5s CPU, 10-25s wall on a loaded dev box) for a path
comparison. The source case is decided from the manifest file alone; any other layout defers to
the real `get_distribution_mode()` so the answer stays identical.
"""

from __future__ import annotations

import runpy
import sys
from importlib.util import find_spec
from pathlib import Path

_MANIFEST_RELPATH = Path("runtime/install_guard/_generated/core_ip_manifest.py")


def harness_package_dir() -> Path | None:
    spec = find_spec("myrm_agent_harness")
    if spec is None:
        return None
    if spec.origin:
        return Path(spec.origin).resolve().parent
    locations = spec.submodule_search_locations
    return Path(next(iter(locations))).resolve() if locations else None


def distribution_mode(pkg_dir: Path) -> str:
    manifest = runpy.run_path(str(pkg_dir / _MANIFEST_RELPATH))
    if all((pkg_dir / relpath).is_file() for relpath in manifest["CORE_IP_SOURCE_RELPATHS"]):
        return "source"
    from myrm_agent_harness.runtime.install_guard.probe import get_distribution_mode

    return get_distribution_mode().value


def main() -> int:
    pkg_dir = harness_package_dir()
    if pkg_dir is None:
        return 1
    print(distribution_mode(pkg_dir))
    print(pkg_dir)
    return 0


if __name__ == "__main__":
    # Running by path puts this directory first on sys.path, where sibling modules could shadow
    # what the fallback imports; `python -c` callers used the cwd, so keep that.
    if sys.path and Path(sys.path[0]).resolve() == Path(__file__).resolve().parent:
        sys.path[0] = ""
    raise SystemExit(main())
