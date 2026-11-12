"""Runtime Identity SSOT for Chrome MCP E2E drift detection.

[INPUT]
- stack-epoch.json via stack-epoch.sh (POS: Backend generation SSOT for parallel Agent drift)
- git work tree of the backend server and harness (POS: committed, uncommitted and untracked source the backend imports without restarting)
- `frontend_epoch.py` / `browser_epoch.py` epoch readers (POS: frontend dev-server, Chrome CDP and mux generation stamps)
- `endpoint_health.py` verdicts (POS: stack-core and attach health for the CLI)
- e2e_core.dev_ports::shared_api_base / shared_ui_base (POS: Default ports of the user, shared dev and isolated stacks — SSOT)

[OUTPUT]
- `build_health_json()` / CLI: unified `CHROME_E2E_HEALTH_JSON` with `runtimeId` and four epochs
- `read_backend_epoch()`: `stored_source_fingerprint` + `workspace_source_fingerprint` + `epoch_match`
- `collect_runtime_parts()` / `compute_runtime_id()` / `compute_hot_pool_runtime_id()` / `read_stack_scoped_runtime_id()`: the four epochs and the ids derived from them
- CLI `--require-stack-core`: exit 2 when stack core or API health is not ready
- `read_current_runtime_id()` / `--drift --expect`: see `runtime_probe.py` (mechanical RUNTIME_DRIFT check)

[POS]
Dev infrastructure module. Aggregates immutable runtime identity for MCP UI E2E preflight.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

# 作为脚本直接执行时（`python .../e2e_core/runtime_identity.py`），sys.path[0] 指向模块自身所在
# 目录而非 dev lib 根，导致模块级导入 e2e_core.* / dev_gate.* 失败；
# 自举 dev lib 根（当前目录的父目录或向上两级），与 dev_gate/cli.py 保持同模式。
if __package__ in (None, ""):
    _lib_root = str(Path(__file__).resolve().parent.parent)
    if _lib_root not in sys.path:
        sys.path.insert(0, _lib_root)

from e2e_core.browser_epoch import read_chrome_epoch, read_mux_epoch
from e2e_core.dev_ports import shared_api_base, shared_ui_base
from e2e_core.endpoint_health import (
    api_health_errors,
    attach_endpoint_errors,
    attach_health_errors,
    format_attach_endpoint_failure,
    read_attach_health_errors,
    signoff_stream_holder_health_errors,
    stack_core_health_errors,
)
from e2e_core.epoch_state import read_json_file, stack_epoch_file
from e2e_core.frontend_epoch import read_frontend_epoch, read_frontend_hot_state
from e2e_core.runtime_types import (
    BackendEpoch,
    FrontendEpoch,
    HealthJsonPayload,
    RuntimeIdentityParts,
)


def read_backend_epoch() -> BackendEpoch | None:
    epoch_path = stack_epoch_file()
    raw = read_json_file(epoch_path)
    if raw is None:
        from dev_paths import scripts_dev_dir

        dev_dir = scripts_dev_dir(Path(__file__))
        dev_dir_str = str(dev_dir)
        if dev_dir_str not in sys.path:
            sys.path.insert(0, dev_dir_str)
        from wave_orchestrator.paths import _real_user_home

        fallback = _real_user_home() / ".local/state/myrm-dev/stack-epoch.json"
        if fallback != epoch_path:
            raw = read_json_file(fallback)
    if raw is None:
        return None
    epoch = raw.get("epoch")
    if not isinstance(epoch, int) or epoch < 1:
        return None
    backend_pid = raw.get("backend_pid")
    if backend_pid is not None and not isinstance(backend_pid, int):
        backend_pid = None
    started_at = raw.get("started_at")
    if not isinstance(started_at, str):
        started_at = ""
    harness_fingerprint = raw.get("harness_fingerprint")
    if not isinstance(harness_fingerprint, str):
        harness_fingerprint = ""
    stored_source_fingerprint = raw.get("source_fingerprint")
    if not isinstance(stored_source_fingerprint, str):
        stored_source_fingerprint = ""
    workspace_source_fingerprint = _backend_source_fingerprint()
    epoch_match = (
        bool(stored_source_fingerprint)
        and bool(workspace_source_fingerprint)
        and stored_source_fingerprint == workspace_source_fingerprint
    )
    return {
        "epoch": epoch,
        "backend_pid": backend_pid,
        "started_at": started_at,
        "harness_fingerprint": harness_fingerprint,
        "stored_source_fingerprint": stored_source_fingerprint,
        "workspace_source_fingerprint": workspace_source_fingerprint,
        "epoch_match": epoch_match,
    }


def _backend_source_fingerprint() -> str:
    """Hash backend and harness source changes that do not restart the server."""
    root = Path(__file__).resolve().parents[4]
    server_dir = Path(os.environ.get("MYRM_SERVER_DIR", root / "myrm-agent-server"))
    harness_dir = Path(
        os.environ.get("MYRM_HARNESS_DIR", root / "myrm-agent-harness")
    )
    tracked_groups = (
        (server_dir, ("app", "pyproject.toml", "uv.lock")),
        (harness_dir, ("src", "pyproject.toml")),
    )
    digest = hashlib.sha256()
    found = False
    for repo, paths in tracked_groups:
        if not repo.is_dir():
            continue
        try:
            diff = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "diff",
                    "--no-ext-diff",
                    "--binary",
                    "HEAD",
                    "--",
                    *paths,
                ],
                check=False,
                capture_output=True,
                timeout=10,
            ).stdout
            untracked = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                    "--",
                    *paths,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.splitlines()
            tree = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"],
                check=False,
                capture_output=True,
                timeout=10,
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        digest.update(str(repo).encode("utf-8"))
        digest.update(tree)
        digest.update(diff)
        found = True
        for relative in sorted(item for item in untracked if item):
            try:
                digest.update(relative.encode("utf-8"))
                digest.update((repo / relative).read_bytes())
            except OSError:
                continue
    return digest.hexdigest()[:16] if found else ""


def collect_runtime_parts(
    *,
    frontend_dir: Path | None = None,
    cdp_port: int | None = None,
    profile_dir: Path | None = None,
    upstream_ready: bool = False,
    ws_stamp_matches: bool = False,
    mux_daemon_count: int = 0,
    upstream_generation: int = 0,
) -> RuntimeIdentityParts:
    return {
        "backend_epoch": read_backend_epoch(),
        "frontend_epoch": read_frontend_epoch(frontend_dir),
        "chrome_epoch": read_chrome_epoch(cdp_port, profile_dir),
        "mux_epoch": read_mux_epoch(
            upstream_ready=upstream_ready,
            ws_stamp_matches=ws_stamp_matches,
            mux_daemon_count=mux_daemon_count,
            upstream_generation=upstream_generation,
        ),
    }


def _canonical_parts_for_hash(parts: RuntimeIdentityParts) -> dict[str, object]:
    mux = parts["mux_epoch"]
    mux_identity: dict[str, object] | None = None
    if mux is not None:
        mux_identity = {
            "daemon_pid": mux["daemon_pid"],
            "ws_url": mux["ws_url"],
            "upstream_generation": mux.get("upstream_generation", 0),
        }
    chrome = parts["chrome_epoch"]
    chrome_identity: dict[str, object] | None = None
    if chrome is not None:
        chrome_identity = {
            "browser_id": chrome["browser_id"],
            "cdp_port": chrome["cdp_port"],
        }
    return {
        "backend_epoch": parts["backend_epoch"],
        "frontend_epoch": parts["frontend_epoch"],
        "chrome_epoch": chrome_identity,
        "mux_epoch": mux_identity,
    }


def compute_runtime_id(parts: RuntimeIdentityParts) -> str:
    canonical = json.dumps(
        _canonical_parts_for_hash(parts), sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:32]


def _stable_hot_pool_epoch_parts(parts: RuntimeIdentityParts) -> RuntimeIdentityParts:
    """Keep process/browser generations while excluding HMR source changes."""
    stable = _stable_stack_epoch_parts(parts)
    return {
        **stable,
        "chrome_epoch": parts["chrome_epoch"],
        "mux_epoch": parts["mux_epoch"],
    }


def compute_hot_pool_runtime_id(parts: RuntimeIdentityParts) -> str:
    """Identity for shared infrastructure ownership, independent of source warmth."""
    return compute_runtime_id(_stable_hot_pool_epoch_parts(parts))


def _stable_stack_epoch_parts(parts: RuntimeIdentityParts) -> RuntimeIdentityParts:
    """Drop git-diff fingerprints so isolated E2E drift checks survive in-session edits."""
    backend = parts["backend_epoch"]
    frontend = parts["frontend_epoch"]
    stable_backend: BackendEpoch | None = None
    stable_frontend: FrontendEpoch | None = None
    if backend is not None:
        stable_backend = {
            **backend,
            "stored_source_fingerprint": "",
            "workspace_source_fingerprint": "",
            "epoch_match": True,
            "harness_fingerprint": backend.get("harness_fingerprint", ""),
        }
    if frontend is not None:
        stable_frontend = {**frontend, "source_fingerprint": ""}
    return {
        "backend_epoch": stable_backend,
        "frontend_epoch": stable_frontend,
        "chrome_epoch": None,
        "mux_epoch": None,
    }


def read_stack_scoped_runtime_id() -> str:
    """Backend + frontend fingerprint for isolated E2E (ignores shared Chrome/mux noise)."""
    frontend_dir: Path | None = None
    override = os.getenv("MYRM_FRONTEND_DIR", "").strip()
    if override:
        frontend_dir = Path(override)
    parts: RuntimeIdentityParts = {
        "backend_epoch": read_backend_epoch(),
        "frontend_epoch": read_frontend_epoch(frontend_dir),
        "chrome_epoch": None,
        "mux_epoch": None,
    }
    return compute_runtime_id(_stable_stack_epoch_parts(parts))


def build_health_json(
    *,
    ui_base: str,
    api_base: str,
    mux_daemon_count: int,
    upstream_ready: bool,
    ws_stamp_matches: bool,
    shell_hot: bool,
    client_hot: bool,
    attach_mode: bool,
    auto_hot: bool = False,
    upstream_generation: int = 0,
    frontend_dir: Path | None = None,
    cdp_port: int | None = None,
    profile_dir: Path | None = None,
) -> HealthJsonPayload:
    parts = collect_runtime_parts(
        frontend_dir=frontend_dir,
        cdp_port=cdp_port,
        profile_dir=profile_dir,
        upstream_ready=upstream_ready,
        ws_stamp_matches=ws_stamp_matches,
        mux_daemon_count=mux_daemon_count,
        upstream_generation=upstream_generation,
    )
    runtime_id = compute_hot_pool_runtime_id(parts)
    if auto_hot:
        shell_hot, client_hot = read_frontend_hot_state(parts["frontend_epoch"])
    backend = parts["backend_epoch"]
    stack_epoch: int | None = backend["epoch"] if backend is not None else None

    return {
        "ui": ui_base,
        "api": api_base,
        "muxDaemons": mux_daemon_count,
        "upstreamReady": upstream_ready,
        "wsStampMatch": ws_stamp_matches,
        "shellHot": shell_hot,
        "clientHot": client_hot,
        "stackEpoch": stack_epoch,
        "attachMode": attach_mode,
        "runtimeId": runtime_id,
        "backendEpoch": parts["backend_epoch"],
        "frontendEpoch": parts["frontend_epoch"],
        "chromeEpoch": parts["chrome_epoch"],
        "muxEpoch": parts["mux_epoch"],
    }


def runtime_ids_equal(left: str, right: str) -> bool:
    return left.strip() == right.strip() and bool(left.strip())


def main() -> None:
    import argparse

    from e2e_core.runtime_probe import probe_runtime_context, run_drift_check

    parser = argparse.ArgumentParser(
        description="Runtime identity SSOT for Chrome MCP E2E"
    )
    parser.add_argument(
        "--drift", action="store_true", help="Compare current runtimeId to --expect"
    )
    parser.add_argument("--expect", default="", help="Expected runtimeId for --drift")
    parser.add_argument(
        "--auto-probe",
        action="store_true",
        help="Probe mux/CDP/frontend paths (SSOT for preflight and runtime-drift)",
    )
    parser.add_argument(
        "--ui", default=os.getenv("E2E_UI_BASE", shared_ui_base())
    )
    parser.add_argument(
        "--api", default=os.getenv("E2E_API_BASE", shared_api_base())
    )
    parser.add_argument("--mux-daemons", type=int, default=0)
    parser.add_argument("--upstream-ready", action="store_true")
    parser.add_argument("--ws-stamp-match", action="store_true")
    parser.add_argument("--shell-hot", action="store_true")
    parser.add_argument("--client-hot", action="store_true")
    parser.add_argument(
        "--auto-hot",
        action="store_true",
        help="Derive shell/client warmth from frontendEpoch and the cached warmth record",
    )
    parser.add_argument("--attach-mode", action="store_true")
    parser.add_argument(
        "--require-attach-ready",
        action="store_true",
        help="Exit 2 unless the unified snapshot is safe for read-only parallel attach",
    )
    parser.add_argument(
        "--require-stack-core",
        action="store_true",
        help="Exit 2 unless mux/upstream/epochs are live (ignores shellHot/clientHot compile windows; probes API /health only, not UI curl)",
    )
    parser.add_argument(
        "--require-read-attach-ready",
        action="store_true",
        help="Exit 2 for READ lane without shared_hot: stack core + UI/API reachability; no clientHot gate",
    )
    parser.add_argument(
        "--require-signoff-stream-ready",
        action="store_true",
        help="Exit 2 unless mux/CDP/backend identity is live for signoff stream-lock holder (ignores clientHot/frontendEpoch under parallel SMP defer)",
    )
    parser.add_argument("--frontend-dir", default="")
    parser.add_argument("--cdp-port", type=int, default=0)
    parser.add_argument("--profile-dir", default="")
    args = parser.parse_args()

    if args.drift:
        raise SystemExit(run_drift_check(args.expect))

    mux_daemon_count = args.mux_daemons
    upstream_ready = args.upstream_ready
    ws_stamp_match = args.ws_stamp_match
    frontend_dir = Path(args.frontend_dir) if args.frontend_dir else None
    profile_dir = Path(args.profile_dir) if args.profile_dir else None
    cdp_port = args.cdp_port if args.cdp_port > 0 else None

    if args.auto_probe:
        ctx = probe_runtime_context()
        mux_daemon_count = ctx["mux_daemon_count"]
        upstream_ready = ctx["upstream_ready"]
        upstream_generation = ctx["upstream_generation"]
        ws_stamp_match = ctx["ws_stamp_matches"]
        if not args.frontend_dir and ctx["frontend_dir"]:
            frontend_dir = Path(ctx["frontend_dir"])
        if not args.profile_dir:
            profile_dir = Path(ctx["profile_dir"])
        if args.cdp_port <= 0:
            cdp_port = ctx["cdp_port"]

    payload = build_health_json(
        ui_base=args.ui,
        api_base=args.api,
        mux_daemon_count=mux_daemon_count,
        upstream_ready=upstream_ready,
        ws_stamp_matches=ws_stamp_match,
        shell_hot=args.shell_hot,
        client_hot=args.client_hot,
        attach_mode=args.attach_mode,
        auto_hot=args.auto_hot,
        upstream_generation=upstream_generation if args.auto_probe else 0,
        frontend_dir=frontend_dir,
        cdp_port=cdp_port,
        profile_dir=profile_dir,
    )
    if args.require_attach_ready:
        errors = attach_health_errors(payload) + attach_endpoint_errors(
            args.ui, args.api
        )
        if errors:
            print(format_attach_endpoint_failure(errors), file=sys.stderr)
            raise SystemExit(2)
    if args.require_read_attach_ready:
        errors = read_attach_health_errors(payload) + attach_endpoint_errors(
            args.ui, args.api
        )
        if errors:
            print(format_attach_endpoint_failure(errors), file=sys.stderr)
            raise SystemExit(2)
    if args.require_signoff_stream_ready:
        errors = signoff_stream_holder_health_errors(payload) + api_health_errors(
            args.api
        )
        if errors:
            print(
                "CHROME_E2E_SIGNOFF_STREAM_NOT_READY: " + ", ".join(errors),
                file=sys.stderr,
            )
            raise SystemExit(2)
    if args.require_stack_core:
        errors = stack_core_health_errors(payload) + api_health_errors(args.api)
        if errors:
            print(
                "CHROME_E2E_STACK_CORE_NOT_READY: " + ", ".join(errors), file=sys.stderr
            )
            raise SystemExit(2)
    print(f"CHROME_E2E_HEALTH_JSON={json.dumps(payload, separators=(',', ':'))}")


if __name__ == "__main__":
    main()
