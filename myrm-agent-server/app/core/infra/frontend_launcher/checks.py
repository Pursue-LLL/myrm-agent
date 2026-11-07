"""[INPUT]
- .common (POS: shared constants and error type)

[OUTPUT]
- check_node_environment, check_build_artifacts

[POS]
Frontend launcher: node version and build-artifact checks.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .common import (
    _FRONTEND_DIR,
    _MIN_NODE_VERSION,
    FrontendEnvironmentError,
    _resolve_standalone_dir,
    logger,
)


def check_node_environment() -> str:
    """Verify Node.js is installed and meets minimum version requirement.

    Returns:
        Node.js version string (e.g. "20.11.0")

    Raises:
        FrontendEnvironmentError: If Node.js is missing or version is too old.
    """
    node_bin = shutil.which("node")
    if not node_bin:
        raise FrontendEnvironmentError(
            f"Node.js is not installed. Please install Node.js >= {_MIN_NODE_VERSION}: https://nodejs.org/"
        )

    try:
        result = subprocess.run(
            [node_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version_str = result.stdout.strip().lstrip("v")
        major = int(version_str.split(".")[0])
        if major < _MIN_NODE_VERSION:
            raise FrontendEnvironmentError(
                f"Node.js {version_str} is too old. Please upgrade to >= {_MIN_NODE_VERSION}: https://nodejs.org/"
            )
        return version_str
    except (subprocess.TimeoutExpired, ValueError, IndexError) as exc:
        raise FrontendEnvironmentError(f"Failed to detect Node.js version: {exc}") from exc


def check_build_artifacts(*, auto_build: bool = True) -> Path:
    """Verify Next.js standalone build artifacts exist.

    If missing and auto_build is True, attempts to run bun run build automatically.

    Returns:
        Path to the standalone server.js

    Raises:
        FrontendEnvironmentError: If build artifacts are missing or incomplete.
    """
    standalone_dir = _resolve_standalone_dir()
    server_js = standalone_dir / "server.js"

    if not server_js.is_file() and auto_build:
        bun_bin = shutil.which("bun")
        if not bun_bin:
            for candidate in [
                Path.home() / ".bun" / "bin" / "bun",
                Path("/opt/homebrew/bin/bun"),
                Path("/usr/local/bin/bun"),
            ]:
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    bun_bin = str(candidate)
                    break

        package_json = _FRONTEND_DIR / "package.json"
        if bun_bin and package_json.is_file():
            logger.info("[Frontend] Standalone build missing. Auto-building via %s...", bun_bin)
            print("⏳ 前端构建产物不存在，正在自动执行 bun run build 构建 Standalone 服务（首次约需 20~30 秒）...")
            try:
                subprocess.run(
                    [bun_bin, "run", "build"],
                    cwd=str(_FRONTEND_DIR),
                    check=True,
                    timeout=300,
                )
                standalone_dir = _resolve_standalone_dir()
                server_js = standalone_dir / "server.js"
            except Exception as e:
                logger.warning("[Frontend] Auto-build failed: %s", e)

    if not server_js.is_file():
        raise FrontendEnvironmentError(
            f"Frontend build not found at {standalone_dir}\n"
            "Please build the frontend first:\n"
            "  cd myrm-agent-frontend && bun run build"
        )
    static_dir = _FRONTEND_DIR / ".next" / "static"
    if not static_dir.is_dir():
        raise FrontendEnvironmentError(
            f"Frontend static assets not found at {static_dir}\n"
            "The build appears incomplete. Please rebuild:\n"
            "  cd myrm-agent-frontend && bun run build"
        )
    return server_js
