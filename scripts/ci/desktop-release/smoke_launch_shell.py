"""Launch a built desktop bundle the way a user does and prove the product comes up.

The shell is started from its install location with the working directory and environment of a Finder,
Start-menu or desktop launch: no Node.js on PATH and, on macOS and Linux, a fresh profile directory (the
slowest, first launch). It has to bring up the Python backend and the bundled Next.js server on their fixed
ports, serve a page whose static assets resolve, serve the data the backend ships (skills, agent templates,
integration catalog, search providers), stay up, and shut its children down when asked to quit.

Usage:
    python smoke_launch_shell.py --bundle <MyrmAgent.app | AppImage squashfs-root | install directory>
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import plistlib
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

HOST = "127.0.0.1"
# Fixed by the shell: BackendConfig's default port and `DESKTOP_FRONTEND_PORT` in src-tauri/src/config.rs.
BACKEND_PORT = 8080
FRONTEND_PORT = 13000
# Cargo package name, which Tauri uses for the main binary; tests/architecture/test_desktop_launch_smoke_script.py pins it.
MAIN_BINARY = "myrm-agent"

# The shell gives the backend 120 s (python_backend.rs) and the Next server 45 s, started in parallel; the rest is
# slack for a cold hosted runner.
READY_TIMEOUT_SEC = 180
# A fresh profile serves each list from the backend's first answer; the window is for a request that is slow or fails
# once on a loaded runner, which must not fail the run.
DATA_TIMEOUT_SEC = 60
DATA_REQUEST_TIMEOUT_SEC = 20.0
STABLE_SEC = 5
STOP_TIMEOUT_SEC = 30
POLL_INTERVAL_SEC = 1.0
LOG_TAIL_LINES = 150

# What a Finder (launchd) launch gives an application; a Linux desktop launcher is no richer in practice.
UNIX_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
# Display and session variables a Linux shell needs from the virtual X server the workflow runs it under.
LINUX_SESSION_VARS = ("DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")

_STATIC_ASSET = re.compile(r'(?:src|href)="(/_next/static/[^"]+\.(?:js|css))"')


class SmokeFailure(Exception):
    """The bundle did not behave like a working product."""


@dataclass(frozen=True)
class Ports:
    backend: int = BACKEND_PORT
    frontend: int = FRONTEND_PORT

    @property
    def backend_root(self) -> str:
        return f"http://{HOST}:{self.backend}"

    @property
    def backend_health(self) -> str:
        return f"{self.backend_root}/health"

    @property
    def frontend_root(self) -> str:
        return f"http://{HOST}:{self.frontend}"


DEFAULT_PORTS = Ports()


@dataclass(frozen=True)
class Process:
    pid: int
    ppid: int
    command: str


def windows_path(system_root: str) -> str:
    """The system directories a Start-menu launch always has; a user-installed Node.js is not among them."""
    return ";".join([rf"{system_root}\System32", system_root, rf"{system_root}\System32\Wbem"])


def launch_path(platform: str, inherited: Mapping[str, str]) -> str:
    return windows_path(inherited.get("SYSTEMROOT", r"C:\Windows")) if platform == "win32" else UNIX_PATH


def launch_env(platform: str, profile: Path, inherited: Mapping[str, str]) -> dict[str, str]:
    """The environment the shell is started with.

    Windows keeps the user's environment (an Explorer launch does) and only narrows PATH. macOS and Linux
    start from nothing, as launchd and desktop launchers do, so nothing a CI image exports leaks in.
    """
    if platform == "win32":
        env = dict(inherited)
        env["PATH"] = launch_path(platform, inherited)
        return env
    env = {
        "PATH": launch_path(platform, inherited),
        "HOME": str(profile),
        "USER": inherited.get("USER", "runner"),
        "LANG": "en_US.UTF-8",
        "TMPDIR": str(profile / "tmp"),
    }
    env.update({name: inherited[name] for name in LINUX_SESSION_VARS if name in inherited})
    return env


def launch_cwd(platform: str, bundle: Path, profile: Path) -> Path:
    """The working directory a launcher gives the shell, which the product must not depend on.

    Finder (launchd) starts an application in `/`, a directory nothing can write to, and a Start-menu shortcut
    starts it in the install directory. On Linux AppRun moves the shell into the image's `usr` directory whatever
    it was started in, so the profile stands in for the launcher's directory there.
    """
    if platform == "darwin":
        return Path("/")
    if platform == "win32":
        return bundle
    return profile


def shell_command(platform: str, bundle: Path) -> list[str]:
    """The executable a user starts, located inside the unpacked bundle."""
    if platform == "darwin":
        info = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
        return [str(bundle / "Contents/MacOS" / str(info["CFBundleExecutable"]))]
    if platform == "win32":
        return [str(bundle / f"{MAIN_BINARY}.exe")]
    return [str(bundle / "AppRun")]


def parse_process_table(ps_output: str) -> list[Process]:
    """Rows of `ps -axo pid=,ppid=,command=`."""
    table: list[Process] = []
    for line in ps_output.splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            table.append(Process(int(fields[0]), int(fields[1]), fields[2]))
    return table


def descendants(table: list[Process], root: int) -> list[Process]:
    """Every process below `root`, however deep."""
    children: dict[int, list[Process]] = {}
    for process in table:
        children.setdefault(process.ppid, []).append(process)
    found: list[Process] = []
    pending = [root]
    while pending:
        for child in children.get(pending.pop(), []):
            found.append(child)
            pending.append(child.pid)
    return found


def process_table() -> list[Process]:
    completed = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True, check=True)
    return parse_process_table(completed.stdout)


# Requests must reach 127.0.0.1 directly, whatever proxy a developer machine or runner exports.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url: str, timeout: float = 5.0) -> bytes | None:
    """The body of a successful response, or None while the server is not (yet) answering with success."""
    try:
        with _OPENER.open(url, timeout=timeout) as response:
            return response.read() if 200 <= response.status < 300 else None
    except (OSError, http.client.HTTPException):
        return None


def check_static_assets(base_url: str) -> None:
    """The page must reference built assets that the same server serves; a server without `.next/static` serves a black window."""
    page = fetch(f"{base_url}/")
    if page is None:
        raise SmokeFailure(f"{base_url}/ stopped answering")
    asset = _STATIC_ASSET.search(page.decode("utf-8", errors="replace"))
    if asset is None:
        raise SmokeFailure(f"{base_url}/ references no /_next/static asset")
    body = fetch(f"{base_url}{asset.group(1)}")
    if not body:
        raise SmokeFailure(f"{base_url}{asset.group(1)} is not served")


@dataclass(frozen=True)
class BundledData:
    """A list the backend builds from files it ships next to its code; `list_key` names the list inside the response."""

    label: str
    path: str
    list_key: str | None


# PyInstaller archives Python only, so a data directory the bundle forgot leaves the backend healthy and these lists
# empty. A fresh profile must already serve each of them; tests/architecture/test_desktop_sidecar_data.py pins the
# bundle list, this proves the built app really has the data.
BUNDLED_DATA = (
    BundledData("skills", "/api/v1/skills/", "skills"),
    BundledData("agent templates", "/api/v1/agents/templates", None),
    BundledData("integration catalog", "/api/v1/integrations/catalog", "entries"),
    BundledData("search providers", "/api/v1/integrations/search/providers", "providers"),
)


def count_listed(body: bytes, list_key: str | None) -> int:
    """How many items a list endpoint returned, whether or not the API wraps the list in a `data` envelope."""
    try:
        payload = json.loads(body)
    except ValueError:
        return 0
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    if list_key is not None and isinstance(payload, dict):
        payload = payload.get(list_key)
    return len(payload) if isinstance(payload, list) else 0


def unserved_data(base_url: str, wanted: Iterable[BundledData]) -> list[BundledData]:
    """The entries of `wanted` for which the backend at `base_url` does not (yet) return a non-empty list."""
    unserved: list[BundledData] = []
    for data in wanted:
        body = fetch(f"{base_url}{data.path}", timeout=DATA_REQUEST_TIMEOUT_SEC)
        if body is None or count_listed(body, data.list_key) == 0:
            unserved.append(data)
    return unserved


def check_bundled_data(shell: subprocess.Popen[bytes], log: Path, ports: Ports) -> None:
    """Every bundled list must be non-empty within DATA_TIMEOUT_SEC of the backend answering; the shell must stay up."""
    deadline = time.monotonic() + DATA_TIMEOUT_SEC
    pending = unserved_data(ports.backend_root, BUNDLED_DATA)
    while pending and time.monotonic() < deadline:
        if shell.poll() is not None:
            raise SmokeFailure(
                f"the shell exited with {shell.returncode} while the backend was loading its data\n{log_tail(log)}"
            )
        time.sleep(POLL_INTERVAL_SEC)
        pending = unserved_data(ports.backend_root, pending)
    if pending:
        lists = ", ".join(f"{data.label} ({data.path})" for data in pending)
        raise SmokeFailure(
            f"no non-empty list from the backend {DATA_TIMEOUT_SEC:.0f}s after it became ready: {lists}\n{log_tail(log)}"
        )


def served_ports(ports: Ports) -> list[int]:
    """The ports of `ports` that currently accept a connection."""
    served: list[int] = []
    for port in (ports.backend, ports.frontend):
        with socket.socket() as probe:
            probe.settimeout(1.0)
            if probe.connect_ex((HOST, port)) == 0:
                served.append(port)
    return served


def ensure_ports_free(ports: Ports) -> None:
    """A server that already answers on a port would make the shell's own servers look healthy."""
    served = served_ports(ports)
    if served:
        raise SmokeFailure(f"{HOST}:{served[0]} is already served by another process; the smoke would prove nothing")


def wait_ports_released(ports: Ports, timeout_sec: float) -> None:
    """After the shell is gone no process of its tree may still serve a port; a survivor blocks the next launch."""
    deadline = time.monotonic() + timeout_sec
    served = served_ports(ports)
    while served and time.monotonic() < deadline:
        time.sleep(0.5)
        served = served_ports(ports)
    if served:
        raise SmokeFailure(f"the shell is gone but a process still serves {HOST}:{served[0]}")


def log_tail(log: Path) -> str:
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-LOG_TAIL_LINES:])


def wait_until_ready(shell: subprocess.Popen[bytes], log: Path, ports: Ports, timeout_sec: float) -> None:
    """Block until the backend and the Next server answer; the shell must stay up meanwhile."""
    started = time.monotonic()
    ready: dict[str, float] = {}
    endpoints = {"backend": ports.backend_health, "frontend": f"{ports.frontend_root}/"}
    while len(ready) < len(endpoints):
        elapsed = time.monotonic() - started
        if shell.poll() is not None:
            raise SmokeFailure(f"the shell exited with {shell.returncode} after {elapsed:.0f}s\n{log_tail(log)}")
        if elapsed > timeout_sec:
            missing = ", ".join(name for name in endpoints if name not in ready)
            raise SmokeFailure(f"not ready after {timeout_sec:.0f}s: {missing}\n{log_tail(log)}")
        for name, url in endpoints.items():
            if name not in ready and fetch(url, timeout=2.0) is not None:
                ready[name] = time.monotonic() - started
                print(f"[shell-smoke] {name} ready in {ready[name]:.1f}s ({url})")
        time.sleep(POLL_INTERVAL_SEC)


def stay_up(shell: subprocess.Popen[bytes], log: Path, ports: Ports) -> None:
    deadline = time.monotonic() + STABLE_SEC
    while time.monotonic() < deadline:
        if shell.poll() is not None:
            raise SmokeFailure(f"the shell exited with {shell.returncode} right after becoming ready\n{log_tail(log)}")
        time.sleep(0.5)
    for url in (ports.backend_health, f"{ports.frontend_root}/"):
        if fetch(url) is None:
            raise SmokeFailure(f"{url} stopped answering within {STABLE_SEC}s of becoming ready\n{log_tail(log)}")


def quit_gracefully(shell: subprocess.Popen[bytes], children: list[Process]) -> None:
    """SIGTERM the shell, as a logout or a package manager does: nothing of its subtree may outlive it."""
    shell.send_signal(signal.SIGTERM)
    try:
        shell.wait(timeout=STOP_TIMEOUT_SEC)
    except subprocess.TimeoutExpired as exc:
        raise SmokeFailure(f"the shell did not quit within {STOP_TIMEOUT_SEC}s of SIGTERM") from exc
    deadline = time.monotonic() + STOP_TIMEOUT_SEC
    alive = children
    while alive and time.monotonic() < deadline:
        running = {process.pid for process in process_table()}
        alive = [process for process in children if process.pid in running]
        if alive:
            time.sleep(0.5)
    if alive:
        names = ", ".join(f"{process.pid}:{process.command[:80]}" for process in alive)
        raise SmokeFailure(f"the shell quit but left its children running: {names}")


def kill_tree(shell: subprocess.Popen[bytes], platform: str) -> None:
    """Last resort on every path out: nothing the smoke started may outlive it."""
    if platform == "win32":
        subprocess.run(["taskkill", "/PID", str(shell.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        try:
            os.killpg(shell.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    shell.wait()


def run(bundle: Path, platform: str, *, ports: Ports = DEFAULT_PORTS, ready_timeout_sec: float = READY_TIMEOUT_SEC) -> None:
    # The shell is started in another working directory, so a relative path would not find it; and Tauri on macOS
    # refuses a starting binary whose path crosses a symlink (`/var`, where `mktemp -d` lives, is one), which
    # leaves the shell without its resource directory.
    bundle = bundle.resolve()
    node = shutil.which("node", path=launch_path(platform, os.environ))
    if node is not None:
        raise SmokeFailure(f"the launch PATH still finds a Node.js at {node}; the smoke would prove nothing")
    ensure_ports_free(ports)

    command = shell_command(platform, bundle)
    if not Path(command[0]).is_file():
        listing = ", ".join(sorted(entry.name for entry in bundle.iterdir())) if bundle.is_dir() else "<missing>"
        raise SmokeFailure(f"no shell executable at {command[0]} (bundle holds: {listing})")

    with tempfile.TemporaryDirectory(prefix="myrm-shell-smoke-") as workdir:
        profile = Path(workdir) / "profile"
        (profile / "tmp").mkdir(parents=True)
        log = Path(workdir) / "shell.log"
        env = launch_env(platform, profile, os.environ)
        print(f"[shell-smoke] launching {command[0]} with PATH={env['PATH']}")
        with log.open("wb") as sink:
            shell = subprocess.Popen(  # noqa: S603 - the command is the bundle's own executable
                command,
                env=env,
                cwd=launch_cwd(platform, bundle, profile),
                stdin=subprocess.DEVNULL,
                stdout=sink,
                stderr=subprocess.STDOUT,
                start_new_session=platform != "win32",
            )
        try:
            wait_until_ready(shell, log, ports, ready_timeout_sec)
            check_static_assets(ports.frontend_root)
            check_bundled_data(shell, log, ports)
            stay_up(shell, log, ports)
            if platform == "win32":
                # Windows has no SIGTERM to send, so the graceful quit is not exercised here; the tree kill is
                # the stop, and a process that escaped it shows up as a port that is still served.
                kill_tree(shell, platform)
                wait_ports_released(ports, STOP_TIMEOUT_SEC)
                print("[shell-smoke] OK (quit path not exercised on Windows)")
                return
            children = descendants(process_table(), shell.pid)
            if not children:
                raise SmokeFailure("the shell has no child process while it serves the backend and the page")
            quit_gracefully(shell, children)
            print("[shell-smoke] OK")
        finally:
            kill_tree(shell, platform)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--bundle", type=Path, required=True, help="the unpacked bundle: .app, squashfs-root or install directory"
    )
    args = parser.parse_args(argv)
    try:
        run(args.bundle, sys.platform)
    except SmokeFailure as exc:
        print(f"[shell-smoke] FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
