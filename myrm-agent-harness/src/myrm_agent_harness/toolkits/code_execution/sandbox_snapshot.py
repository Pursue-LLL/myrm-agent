"""Sandbox environment bootstrap snapshot generator.

Captures initial workspace state (working directory, top-level directory entries,
git status, installed language runtimes, package managers, and recommended PM)
without deep recursive traversals. A snapshot starts up to ten processes in turn: three git commands (the ``git config``
listing behind the status command is capped at 5 s, the others at 1 s) and one version command per runtime binary
found, up to seven, at 1 s each; for an ordinary repository layout the caps add up to 14 s. In a git repository it
took 0.3-0.7 s typically and 1.5 s at most (four batches, macOS, machine load 11-26). A runtime is listed only when
its binary ran and reported a version; package managers and CLI tools are listed by their presence on PATH.

Injected into initial task context / observation (never polluting immutable
system prompt) so the agent does not spend turns on pwd, ls and which.

[INPUT]
- workspace_path: str | Path to workspace directory
- max_entries: int = 25 (max top-level entries to report)
- core.security.detection.content_boundary::sanitize, detect_suspicious, strip_invisible_unicode (POS: untrusted-text neutralisation)

[OUTPUT]
- SandboxBootstrapSnapshot: Dataclass holding structured sandbox metadata
- generate_sandbox_bootstrap_snapshot: Probes host & workspace and returns snapshot
- format_bootstrap_snapshot_xml: Formats snapshot into a compact, model-friendly XML block; entry names are rendered as single-line plain text

[POS]
Harness code_execution sandbox snapshot generator.
Safe, non-recursive, cache-preserving, resilient to timeouts and permission errors.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.core.security.detection.content_boundary import (
    detect_suspicious,
    sanitize,
    strip_invisible_unicode,
)
from myrm_agent_harness.core.security.safe_git import hardened_git_argv

logger = logging.getLogger(__name__)

# Common build/cache/vcs directories to skip or compact
_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "env",
        ".idea",
        ".vscode",
        "target",
        "dist",
        "build",
    }
)

_CORE_RUNTIMES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Python", ("python3", "python")),
    ("Node.js", ("node",)),
    ("Bun", ("bun",)),
    ("Go", ("go",)),
    ("Rust", ("rustc",)),
    ("Java", ("java",)),
)

_CORE_TOOLS: tuple[str, ...] = ("git", "curl", "jq", "docker", "make", "tar", "rg")

# ``None`` means the status probe gave no answer (timeout, refused layout, git missing): that is never reported as clean.
_GIT_STATE_LABEL: dict[bool | None, str] = {True: "dirty", False: "clean", None: "unknown"}

# A top-level entry name is third-party text in a system message, so it is shown as one short line of plain text:
# line breaks, control and bidirectional characters become spaces, framing markers are neutralised, a name that reads as an
# instruction is withheld, and a long name is cut.
_MAX_ENTRY_NAME_CHARS = 80
_LINE_BREAKS_AND_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
_WITHHELD_ENTRY_NAME = "[name withheld]"

# ``java -version`` prints e.g. ``openjdk version "21.0.4" 2024-07-16`` or ``java version "1.8.0_391"``.
_JAVA_VERSION = re.compile(r'version "([^"]+)"')


@dataclass(frozen=True)
class SandboxBootstrapSnapshot:
    """Immutable snapshot of the sandbox workspace and runtime environment."""

    working_dir: str
    top_level_entries: tuple[str, ...]
    total_entries_count: int
    git_branch: str | None = None
    git_dirty: bool | None = None
    runtimes: tuple[str, ...] = ()
    package_managers: tuple[str, ...] = ()
    recommended_package_manager: str | None = None
    available_tools: tuple[str, ...] = ()

    @property
    def is_git_repo(self) -> bool:
        return self.git_branch is not None


def _run_quick_command(cmd: Sequence[str], timeout: float = 1.0, *, merge_stderr: bool = False) -> tuple[int, str]:
    """Run a fast subprocess command with a strict timeout; ``merge_stderr`` is for a tool that reports on stderr."""
    try:
        proc = subprocess.run(
            list(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("Sandbox snapshot quick command failed: %s (%s)", cmd, exc)
        return -1, ""


def _probe_git_state(workspace: Path) -> tuple[str | None, bool | None]:
    """Quickly probe git branch and cleanliness using git CLI or .git directory."""
    git_dir = workspace / ".git"
    if not git_dir.exists():
        return None, None

    if not shutil.which("git"):
        return "detected (git cli missing)", None

    rc_branch, branch_out = _run_quick_command(
        ["git", "-C", str(workspace), "rev-parse", "--abbrev-ref", "HEAD"], timeout=1.0
    )
    if rc_branch != 0 or not branch_out:
        branch_out = "HEAD"

    try:
        status_cmd = hardened_git_argv(("status", "--porcelain"), repo_dir=workspace)
    except OSError:
        return branch_out, None
    rc_status, status_out = _run_quick_command(status_cmd, timeout=1.0)
    is_dirty = bool(status_out) if rc_status == 0 else None

    return branch_out, is_dirty


def _probe_runtimes() -> list[str]:
    """The runtimes whose binary ran and reported a version.

    A binary on PATH that does not run (a toolchain proxy with nothing installed, a launcher stub) is not an
    installed runtime, so it is left out and the next binary of the same runtime is tried.
    """
    detected: list[str] = []
    for label, binaries in _CORE_RUNTIMES:
        for bin_name in binaries:
            if shutil.which(bin_name) and (version := _probe_runtime_version(bin_name)):
                detected.append(f"{label} {version}")
                break
    return detected


def _probe_runtime_version(bin_name: str) -> str:
    """Fetch short version string for a given runtime binary."""
    if bin_name in ("python3", "python"):
        rc, out = _run_quick_command(
            [bin_name, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')"]
        )
        if rc == 0 and out:
            return out
    elif bin_name == "node":
        rc, out = _run_quick_command(["node", "-v"])
        if rc == 0 and out:
            return out.lstrip("v")
    elif bin_name == "bun":
        rc, out = _run_quick_command(["bun", "--version"])
        if rc == 0 and out:
            return out
    elif bin_name == "go":
        rc, out = _run_quick_command(["go", "env", "GOVERSION"])
        if rc == 0 and out:
            return out.removeprefix("go")
    elif bin_name == "rustc":
        rc, out = _run_quick_command(["rustc", "--version"])
        if rc == 0 and out:
            parts = out.split()
            if len(parts) >= 2:
                return parts[1]
    elif bin_name == "java":
        rc, out = _run_quick_command(["java", "-version"], merge_stderr=True)
        if rc == 0 and (match := _JAVA_VERSION.search(out)):
            return match.group(1)
    return ""


def _probe_package_managers(workspace: Path) -> tuple[tuple[str, ...], str | None]:
    """Detect available package managers and infer the recommended one from lockfiles."""
    available: list[str] = []
    candidates = ("pnpm", "bun", "yarn", "npm", "uv", "poetry", "pip", "cargo", "go")
    for cand in candidates:
        if shutil.which(cand):
            available.append(cand)

    recommended: str | None = None

    # Priority 1: Direct lockfile markers in workspace
    if (workspace / "pnpm-lock.yaml").exists() and "pnpm" in available:
        recommended = "pnpm"
    elif (workspace / "bun.lockb").exists() or (workspace / "bun.lock").exists():
        if "bun" in available:
            recommended = "bun"
    elif (workspace / "yarn.lock").exists() and "yarn" in available:
        recommended = "yarn"
    elif (workspace / "package-lock.json").exists() and "npm" in available:
        recommended = "npm"
    elif (workspace / "uv.lock").exists() and "uv" in available:
        recommended = "uv"
    elif (workspace / "poetry.lock").exists() and "poetry" in available:
        recommended = "poetry"
    elif (workspace / "Cargo.lock").exists() and "cargo" in available:
        recommended = "cargo"
    elif (workspace / "go.sum").exists() and "go" in available:
        recommended = "go"

    # Priority 2: Config file inference when lockfile is absent
    if not recommended:
        if (workspace / "package.json").exists():
            for pref in ("pnpm", "bun", "npm"):
                if pref in available:
                    recommended = pref
                    break
        elif (workspace / "pyproject.toml").exists() or (workspace / "requirements.txt").exists():
            for pref in ("uv", "poetry", "pip"):
                if pref in available:
                    recommended = pref
                    break
        elif (workspace / "Cargo.toml").exists() and "cargo" in available:
            recommended = "cargo"
        elif (workspace / "go.mod").exists() and "go" in available:
            recommended = "go"

    return tuple(available), recommended


def _probe_tools() -> list[str]:
    """Detect presence of common command-line utility tools."""
    found: list[str] = []
    for tool in _CORE_TOOLS:
        if shutil.which(tool):
            found.append(tool)
    return found


def _scan_top_level_entries(workspace: Path, max_entries: int) -> tuple[tuple[str, ...], int]:
    """Shallow non-recursive scan of the workspace directory with limit."""
    entries: list[str] = []
    total_count = 0

    try:
        with os.scandir(workspace) as it:
            raw_entries: list[os.DirEntry[str]] = list(it)
    except (OSError, PermissionError) as exc:
        logger.debug("Failed to scan workspace %s: %s", workspace, exc)
        return (), 0

    # Sort entries: directories first with trailing slash, then files
    sorted_entries = sorted(raw_entries, key=lambda e: (not e.is_dir(), e.name.lower()))
    for entry in sorted_entries:
        name = entry.name
        if name in _IGNORED_DIRS:
            continue
        total_count += 1
        if len(entries) < max_entries:
            display_name = f"{name}/" if entry.is_dir() else name
            entries.append(display_name)

    return tuple(entries), total_count


def generate_sandbox_bootstrap_snapshot(
    workspace_path: str | Path,
    *,
    max_entries: int = 25,
) -> SandboxBootstrapSnapshot:
    """Generate a lightweight, non-recursive bootstrap snapshot of the sandbox environment.

    Process-starting probes are capped at 1 s each, the ``git config`` listing behind the status command at 5 s, so a
    snapshot can block for 14 s when binaries hang: call it from a thread when an event loop is running and bound
    the wait. Any probe failure is handled gracefully to guarantee non-crashing execution.

    Args:
        workspace_path: Path to the workspace root directory.
        max_entries: Maximum number of top-level directory items to report.

    Returns:
        Structured SandboxBootstrapSnapshot instance.
    """
    path = Path(workspace_path).resolve()
    if not path.is_dir():
        return SandboxBootstrapSnapshot(
            working_dir=str(path),
            top_level_entries=(),
            total_entries_count=0,
        )

    # 1. Scan top-level workspace entries
    top_entries, total_count = _scan_top_level_entries(path, max_entries=max_entries)

    # 2. Check git state
    branch, is_dirty = _probe_git_state(path)

    # 3. Detect installed runtimes
    runtimes = _probe_runtimes()

    # 4. Detect package managers and recommend primary choice
    package_managers, recommended_pm = _probe_package_managers(path)

    # 5. Detect core CLI utilities
    tools = _probe_tools()

    return SandboxBootstrapSnapshot(
        working_dir=str(path),
        top_level_entries=top_entries,
        total_entries_count=total_count,
        git_branch=branch,
        git_dirty=is_dirty,
        runtimes=tuple(runtimes),
        package_managers=package_managers,
        recommended_package_manager=recommended_pm,
        available_tools=tuple(tools),
    )


def _display_entry_name(name: str) -> str:
    """The entry name as it may appear in the prompt; an ordinary name comes back unchanged."""
    cleaned = sanitize(_LINE_BREAKS_AND_CONTROLS.sub(" ", strip_invisible_unicode(name)))
    if detect_suspicious(cleaned):
        return _WITHHELD_ENTRY_NAME
    if len(cleaned) > _MAX_ENTRY_NAME_CHARS:
        return cleaned[:_MAX_ENTRY_NAME_CHARS] + "..."
    return cleaned


def format_bootstrap_snapshot_xml(snapshot: SandboxBootstrapSnapshot) -> str:
    """Format the snapshot into a clean, compact XML observation for the initial prompt/observation.

    Designed for maximum model adherence and zero ambiguity while maintaining token efficiency (about 250 tokens
    for a repository with a full 25-entry listing).
    """
    lines: list[str] = ["<sandbox_environment_snapshot>"]

    # Working Directory and Git
    wd_line = f"Working Directory: {snapshot.working_dir}"
    if snapshot.git_branch:
        wd_line += f" (Git: {snapshot.git_branch}, {_GIT_STATE_LABEL[snapshot.git_dirty]})"
    lines.append(wd_line)

    # Top-level workspace entries
    if snapshot.top_level_entries:
        entries_str = ", ".join(_display_entry_name(entry) for entry in snapshot.top_level_entries)
        if snapshot.total_entries_count > len(snapshot.top_level_entries):
            entries_str += f" ... (+{snapshot.total_entries_count - len(snapshot.top_level_entries)} more)"
        lines.append(f"Workspace Contents: {entries_str}")
    else:
        lines.append("Workspace Contents: [empty directory]")

    # Runtimes
    if snapshot.runtimes:
        lines.append(f"Available Runtimes: {', '.join(snapshot.runtimes)}")

    # Package Managers & Recommendation
    if snapshot.package_managers:
        pm_parts: list[str] = []
        for pm in snapshot.package_managers:
            if pm == snapshot.recommended_package_manager:
                pm_parts.append(f"{pm} (recommended for this project)")
            else:
                pm_parts.append(pm)
        lines.append(f"Package Managers: {', '.join(pm_parts)}")

    # Available Tools
    if snapshot.available_tools:
        lines.append(f"CLI Tools: {', '.join(snapshot.available_tools)}")

    lines.append(
        "Guidance: You have full access to the above sandbox workspace. "
        "Use the recommended package manager and paths directly without blind directory probing. "
        "The Git state and file list were captured when the conversation began; re-check them with a tool if you need current values."
    )
    lines.append("</sandbox_environment_snapshot>")
    return "\n".join(lines)
