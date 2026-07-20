"""Runtime Identity SSOT for Chrome MCP E2E drift detection.

[INPUT]
- stack-epoch.json via stack-epoch.sh (POS: Backend generation SSOT for parallel Agent drift)
- frontend .next/dev-server.lock via frontend-warmup.sh (POS: Frontend compile warmth gate)
- CDP GET /json/version on :9333 (POS: Myrm E2E Chrome attach endpoint)
- ~/.local/state/cdmcp-mux daemon.pid + upstream-ws-url (POS: mux daemon generation stamp)

[OUTPUT]
- `build_health_json()` / CLI: unified `CHROME_E2E_HEALTH_JSON` with `runtimeId` and four epochs
- `stack_core_health_errors()` / `api_health_errors()`: stack keepalive (mux epochs + API `/api/v1/health`; no UI curl)
- CLI `--require-stack-core`: exit 2 when stack core or API health is not ready
- `read_current_runtime_id()` / `--drift --expect`: see `runtime_probe.py` (mechanical RUNTIME_DRIFT check)

[POS]
Dev infrastructure module. Aggregates immutable runtime identity for MCP UI E2E preflight.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict


class BackendEpoch(TypedDict):
    epoch: int
    backend_pid: int | None
    started_at: str
    harness_fingerprint: str
    source_fingerprint: str


class FrontendEpoch(TypedDict):
    generation: str
    source_fingerprint: str
    pid: int | None
    started_at: str
    port: int | None
    bundler_mode: str


class ChromeEpoch(TypedDict):
    cdp_port: int
    browser_id: str
    web_socket_url: str
    profile_dir: str


class MuxEpoch(TypedDict):
    daemon_pid: int | None
    ws_url: str
    upstream_ready: bool
    upstream_generation: int


class RuntimeIdentityParts(TypedDict):
    backend_epoch: BackendEpoch | None
    frontend_epoch: FrontendEpoch | None
    chrome_epoch: ChromeEpoch | None
    mux_epoch: MuxEpoch | None


class RuntimeProbeContext(TypedDict):
    mux_daemon_count: int
    upstream_ready: bool
    upstream_generation: int
    ws_stamp_matches: bool
    frontend_dir: str
    cdp_port: int
    profile_dir: str


class HealthJsonPayload(TypedDict):
    ui: str
    api: str
    muxDaemons: int
    upstreamReady: bool
    wsStampMatch: bool
    shellHot: bool
    clientHot: bool
    stackEpoch: int | None
    attachMode: bool
    runtimeId: str
    backendEpoch: BackendEpoch | None
    frontendEpoch: FrontendEpoch | None
    chromeEpoch: ChromeEpoch | None
    muxEpoch: MuxEpoch | None


def attach_health_errors(payload: HealthJsonPayload) -> list[str]:
    """Return every reason a read-only parallel attach is unsafe."""
    errors: list[str] = []
    if payload["muxDaemons"] != 1:
        errors.append(f"muxDaemons={payload['muxDaemons']}")
    checks = (
        ("upstreamReady", payload["upstreamReady"]),
        ("wsStampMatch", payload["wsStampMatch"]),
        ("shellHot", payload["shellHot"]),
        ("clientHot", payload["clientHot"]),
    )
    errors.extend(f"{name}=false" for name, ready in checks if not ready)
    if not payload["runtimeId"]:
        errors.append("runtimeId=empty")
    epochs = (
        ("backendEpoch", payload["backendEpoch"]),
        ("frontendEpoch", payload["frontendEpoch"]),
        ("chromeEpoch", payload["chromeEpoch"]),
        ("muxEpoch", payload["muxEpoch"]),
    )
    errors.extend(f"{name}=missing" for name, epoch in epochs if epoch is None)
    return errors


def stack_core_health_errors(payload: HealthJsonPayload) -> list[str]:
    """Stack liveness for stack-core keepalive — ignore compile-time shell/client warmth."""
    errors: list[str] = []
    if payload["muxDaemons"] != 1:
        errors.append(f"muxDaemons={payload['muxDaemons']}")
    for name, ready in (
        ("upstreamReady", payload["upstreamReady"]),
        ("wsStampMatch", payload["wsStampMatch"]),
    ):
        if not ready:
            errors.append(f"{name}=false")
    if not payload["runtimeId"]:
        errors.append("runtimeId=empty")
    for name, epoch in (
        ("backendEpoch", payload["backendEpoch"]),
        ("frontendEpoch", payload["frontendEpoch"]),
        ("chromeEpoch", payload["chromeEpoch"]),
        ("muxEpoch", payload["muxEpoch"]),
    ):
        if epoch is None:
            errors.append(f"{name}=missing")
    return errors


def _http_url_ok(url: str, *, timeout_sec: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as response:
            return 200 <= response.status < 300
    except (OSError, TimeoutError, urllib.error.URLError):
        return False


def api_health_errors(api_base: str) -> list[str]:
    """Probe API health only — used by stack-core keepalive."""
    api_timeout = 10.0 if os.getenv("MYRM_E2E_ISOLATED") == "1" else 5.0
    url = api_base.rstrip("/") + "/api/v1/health"
    if _http_url_ok(url, timeout_sec=api_timeout):
        return []
    return ["api=unreachable"]


def attach_endpoint_errors(ui_base: str, api_base: str) -> list[str]:
    """Probe UI and API concurrently for the attach-only fast path."""
    ui_timeout = 30.0 if os.getenv("MYRM_E2E_ISOLATED") == "1" else 5.0
    api_timeout = 10.0 if os.getenv("MYRM_E2E_ISOLATED") == "1" else 5.0
    endpoints = (
        ("ui", ui_base.rstrip("/") + "/", ui_timeout),
        ("api", api_base.rstrip("/") + "/api/v1/health", api_timeout),
    )
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="attach-health") as pool:
        ready = tuple(
            pool.submit(_http_url_ok, url, timeout_sec=timeout).result()
            for _, url, timeout in endpoints
        )
    return [f"{name}=unreachable" for (name, _, _), ok in zip(endpoints, ready, strict=True) if not ok]


_BROWSER_ID_RE = re.compile(r"/devtools/browser/([0-9a-f-]{36})")


def _state_dir() -> Path:
    override = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".local/state/myrm-dev"


def _stack_epoch_file() -> Path:
    override = os.getenv("MYRM_STACK_EPOCH_FILE", "").strip()
    if override:
        return Path(override)
    return _state_dir() / "stack-epoch.json"


def _mux_state_dir() -> Path:
    override = os.getenv("CDMCP_MUX_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".local/state/cdmcp-mux"


def _default_chrome_data_dir() -> Path:
    from_env = os.getenv("MYRM_CHROME_E2E_DATA_DIR", "").strip() or os.getenv(
        "CHROME_DATA_DIR", ""
    ).strip()
    if from_env:
        return Path(from_env)
    if os.name == "nt":
        return Path.home() / "AppData/Local/Myrm/ChromeE2E"
    if platform.system() == "Darwin":
        return Path.home() / "Library/Application Support/Myrm/ChromeE2E"
    return Path.home() / ".local/share/myrm/chrome-e2e"


def _resolve_e2e_port() -> int:
    raw = os.getenv("MYRM_CHROME_E2E_PORT", "9333").strip()
    if raw.isdigit():
        return int(raw)
    return 9333


def _read_json_file(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def read_backend_epoch() -> BackendEpoch | None:
    raw = _read_json_file(_stack_epoch_file())
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
    source_fingerprint = _backend_source_fingerprint()
    return {
        "epoch": epoch,
        "backend_pid": backend_pid,
        "started_at": started_at,
        "harness_fingerprint": harness_fingerprint,
        "source_fingerprint": source_fingerprint,
    }


def _backend_source_fingerprint() -> str:
    """Hash backend and harness source changes that do not restart the server."""
    root = Path(__file__).resolve().parents[3]
    server_dir = Path(os.environ.get("MYRM_SERVER_DIR", root / "myrm-agent-server"))
    harness_dir = Path(os.environ.get("MYRM_HARNESS_DIR", root.parent / "myrm-agent-harness"))
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
                ["git", "-C", str(repo), "diff", "--no-ext-diff", "--binary", "HEAD", "--", *paths],
                check=False,
                capture_output=True,
                timeout=10,
            ).stdout
            untracked = subprocess.run(
                ["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard", "--", *paths],
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


def _frontend_next_dir(frontend_dir: Path) -> Path:
    override = os.getenv("MYRM_NEXT_DIST_DIR", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else frontend_dir / override
    return frontend_dir / ".next"


def read_frontend_epoch(frontend_dir: Path | None = None) -> FrontendEpoch | None:
    root = frontend_dir
    if root is None:
        override = os.getenv("MYRM_FRONTEND_DIR", "").strip()
        if override:
            root = Path(override)
        else:
            return None
    next_dir = _frontend_next_dir(root)
    lock_path = next_dir / "dev-server.lock"
    raw = _read_json_file(lock_path)
    if raw is None:
        return None
    pid = raw.get("pid")
    if pid is not None and not isinstance(pid, int):
        pid = None
    started_at = raw.get("startedAt")
    if not isinstance(started_at, str):
        started_at = ""
    port = raw.get("port")
    if port is not None and not isinstance(port, int):
        port = None
    bundler_stamp = next_dir / "dev-bundler-mode"
    bundler_mode = ""
    if bundler_stamp.is_file():
        bundler_mode = bundler_stamp.read_text(encoding="utf-8").strip()
    # Must match frontend-warmup.sh _frontend_lock_generation (four colon-separated fields).
    generation = ":".join(
        [
            str(pid) if pid is not None else "",
            started_at,
            str(port) if port is not None else "",
            bundler_mode,
        ]
    )
    if generation == ":::":
        return None
    source_fingerprint = frontend_source_fingerprint(root)
    return {
        "generation": generation,
        "source_fingerprint": source_fingerprint,
        "pid": pid,
        "started_at": started_at,
        "port": port,
        "bundler_mode": bundler_mode,
    }


def read_frontend_hot_state(frontend: FrontendEpoch | None) -> tuple[bool, bool]:
    """Validate warmth by dev-server generation; HMR source edits keep it hot."""
    if frontend is None or frontend["pid"] is None:
        return False, False
    try:
        os.kill(frontend["pid"], 0)
    except (OSError, ProcessLookupError):
        return False, False
    warmth = _read_json_file(_state_dir() / "frontend-warmth.json")
    if warmth is None:
        return False, False
    # Source edits are served by HMR without replacing the dev server or its
    # hydrated client. Endpoint probes validate current reachability separately.
    current = warmth.get("generation") == frontend["generation"] and bool(
        frontend["source_fingerprint"]
    )
    return current, current and warmth.get("client_hot") is True


def frontend_source_fingerprint(frontend_dir: Path) -> str:
    """Hash tracked changes and untracked frontend sources for HMR drift detection."""
    try:
        probe = subprocess.run(
            ["git", "-C", str(frontend_dir), "rev-parse", "--is-inside-work-tree"],
            check=False,
            capture_output=True,
            timeout=2,
        )
        if probe.returncode != 0 or probe.stdout.strip() != b"true":
            return ""
    except (OSError, subprocess.TimeoutExpired):
        return ""
    tracked_paths = (
        "src",
        "locales",
        "public",
        "next.config.ts",
        "next.config.js",
        "next.config.mjs",
        "package.json",
        "bun.lock",
        "tsconfig.json",
        "postcss.config.mjs",
        "tailwind.config.ts",
        ".env.local",
    )
    try:
        diff = subprocess.run(
            [
                "git",
                "-C",
                str(frontend_dir),
                "diff",
                "--no-ext-diff",
                "--binary",
                "HEAD",
                "--",
                *tracked_paths,
            ],
            check=False,
            capture_output=True,
            timeout=10,
        ).stdout
        untracked = subprocess.run(
            [
                "git",
                "-C",
                str(frontend_dir),
                "ls-files",
                "--others",
                "--exclude-standard",
                "--",
                *tracked_paths,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.splitlines()
        tree = subprocess.run(
            ["git", "-C", str(frontend_dir), "rev-parse", "HEAD^{tree}"],
            check=False,
            capture_output=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""

    digest = hashlib.sha256(tree + diff)
    for relative_path in sorted(item for item in untracked if item):
        path = frontend_dir / relative_path
        try:
            digest.update(relative_path.encode("utf-8"))
            digest.update(path.read_bytes())
        except OSError:
            return ""
    return digest.hexdigest()[:16]


def _fetch_cdp_version(port: int) -> dict[str, object]:
    url = f"http://127.0.0.1:{port}/json/version"
    with urllib.request.urlopen(url, timeout=5) as resp:
        payload = json.load(resp)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid /json/version payload on port {port}")
    return payload


def _browser_id_from_ws_url(ws_url: str) -> str:
    match = _BROWSER_ID_RE.search(ws_url)
    if match:
        return match.group(1)
    return ws_url


def read_chrome_epoch(
    port: int | None = None,
    profile_dir: Path | None = None,
) -> ChromeEpoch | None:
    cdp_port = port if port is not None else _resolve_e2e_port()
    profile = profile_dir if profile_dir is not None else _default_chrome_data_dir()
    try:
        payload = _fetch_cdp_version(cdp_port)
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return None
    ws_url = payload.get("webSocketDebuggerUrl")
    if not isinstance(ws_url, str) or not ws_url.startswith("ws://"):
        return None
    return {
        "cdp_port": cdp_port,
        "browser_id": _browser_id_from_ws_url(ws_url),
        "web_socket_url": ws_url,
        "profile_dir": str(profile),
    }


def read_mux_epoch(
    *,
    upstream_ready: bool,
    ws_stamp_matches: bool,
    mux_daemon_count: int,
    upstream_generation: int = 0,
) -> MuxEpoch | None:
    if mux_daemon_count < 1:
        return None
    pid_path = _mux_state_dir() / "daemon.pid"
    daemon_pid: int | None = None
    if pid_path.is_file():
        try:
            parsed = int(pid_path.read_text(encoding="utf-8").strip())
            if parsed > 0:
                daemon_pid = parsed
        except (OSError, ValueError):
            daemon_pid = None
    ws_stamp_path = _mux_state_dir() / "upstream-ws-url"
    ws_url = ""
    if ws_stamp_path.is_file():
        ws_url = ws_stamp_path.read_text(encoding="utf-8").strip()
    if not ws_url and ws_stamp_matches:
        chrome = read_chrome_epoch()
        if chrome is not None:
            ws_url = chrome["web_socket_url"]
    return {
        "daemon_pid": daemon_pid,
        "ws_url": ws_url,
        "upstream_ready": upstream_ready,
        "upstream_generation": max(upstream_generation, 0),
    }


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
    canonical = json.dumps(_canonical_parts_for_hash(parts), sort_keys=True, separators=(",", ":"))
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
            "source_fingerprint": "",
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

    from runtime_probe import probe_runtime_context, run_drift_check

    parser = argparse.ArgumentParser(description="Runtime identity SSOT for Chrome MCP E2E")
    parser.add_argument("--drift", action="store_true", help="Compare current runtimeId to --expect")
    parser.add_argument("--expect", default="", help="Expected runtimeId for --drift")
    parser.add_argument(
        "--auto-probe",
        action="store_true",
        help="Probe mux/CDP/frontend paths (SSOT for preflight and runtime-drift)",
    )
    parser.add_argument("--ui", default=os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000"))
    parser.add_argument("--api", default=os.getenv("E2E_API_BASE", "http://127.0.0.1:8080"))
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
        errors = attach_health_errors(payload) + attach_endpoint_errors(args.ui, args.api)
        if errors:
            print("CHROME_E2E_ATTACH_NOT_READY: " + ", ".join(errors), file=sys.stderr)
            raise SystemExit(2)
    if args.require_stack_core:
        errors = stack_core_health_errors(payload) + api_health_errors(args.api)
        if errors:
            print("CHROME_E2E_STACK_CORE_NOT_READY: " + ", ".join(errors), file=sys.stderr)
            raise SystemExit(2)
    print(f"CHROME_E2E_HEALTH_JSON={json.dumps(payload, separators=(',', ':'))}")


if __name__ == "__main__":
    main()
