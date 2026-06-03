#!/usr/bin/env python3
"""Verify pinned harness release + platform core packages exist on PyPI.

[INPUT]
- myrm-agent-server/docker/read_harness_pypi_spec.py (harness PyPI pin parser)

[OUTPUT]
- exit 0 when main + current-platform core packages are on PyPI; exit 1 otherwise

[POS]
CI preflight for server/docker/tauri builds that install harness from PyPI.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _resolve_platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        return "darwin-arm64" if machine in {"arm64", "aarch64"} else "darwin-x64"
    if system == "linux":
        return "linux-arm64" if machine in {"arm64", "aarch64"} else "linux-x64"
    if system in {"windows", "mingw", "msys", "cygwin"}:
        return "win32-arm64" if machine in {"arm64", "aarch64"} else "win32-x64"
    raise SystemExit(f"Unsupported platform for harness PyPI check: {system} {machine}")


def _read_pip_spec(server_root: Path) -> str:
    script = server_root / "docker" / "read_harness_pypi_spec.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _parse_version(spec: str) -> str:
    if "==" not in spec:
        raise SystemExit(f"Could not parse harness version from spec: {spec}")
    return spec.rsplit("==", maxsplit=1)[-1]


def _pypi_exists(package: str, version: str) -> bool:
    url = f"https://pypi.org/pypi/{package}/{version}/json"
    request = urllib.request.Request(url, headers={"User-Agent": "myrm-check-harness-pypi"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def _candidate_roots() -> list[Path]:
    here = Path(__file__).resolve().parent
    agent_root = here.parent.parent
    roots: list[Path] = []
    monorepo = os.environ.get("MYRM_MONOREPO_ROOT", "").strip()
    if monorepo:
        roots.append(Path(monorepo))
    roots.append(agent_root)
    legacy = agent_root.parent.parent
    if legacy not in roots:
        roots.append(legacy)
    return roots


def _server_root() -> Path:
    for root in _candidate_roots():
        for rel in ("myrm-agent/myrm-agent-server", "myrm-agent-server"):
            candidate = root / rel
            if (candidate / "pyproject.toml").is_file():
                return candidate
    raise SystemExit(
        "myrm-agent-server not found; run from myrm-agent or vortexai monorepo root."
    )


def main() -> int:
    server_root = _server_root()
    spec = _read_pip_spec(server_root)
    version = _parse_version(spec)
    platform_key = _resolve_platform_key()
    core_package = f"myrm-agent-harness-core-{platform_key}"

    missing: list[str] = []
    if not _pypi_exists("myrm-agent-harness", version):
        missing.append(f"myrm-agent-harness=={version}")
    if not _pypi_exists(core_package, version):
        missing.append(f"{core_package}=={version}")

    if missing:
        print("Missing harness packages on PyPI:", ", ".join(missing), file=sys.stderr)
        print(
            "Publish from myrm-agent-harness: push tag v* → .github/workflows/publish-pypi.yml",
            file=sys.stderr,
        )
        print("Then: myrm harness sync-lock", file=sys.stderr)
        return 1

    print(f"PyPI OK: myrm-agent-harness=={version} and {core_package}=={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
