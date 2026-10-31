"""The packaged-shell launch smoke (`scripts/ci/desktop-release/smoke_launch_shell.py`) against stand-in bundles.

The smoke demands that the shell brings up the backend and the bundled Next.js server, keeps them up and takes them
down when asked to quit. A smoke that cannot fail proves nothing, so each way the product can misbehave is reproduced
here by a stand-in bundle whose executable acts like the shell, or misacts on purpose, and must be reported.
"""

from __future__ import annotations

import os
import plistlib
import signal
import socket
import subprocess
import sys
import threading
import types
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

import pytest

from tests.support.desktop_release import smoke_launch_shell_module

_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="the smoke reads the POSIX process table and signals")


@pytest.fixture(scope="module")
def smoke() -> ModuleType:
    return smoke_launch_shell_module()


class _Ports(Protocol):
    backend: int
    frontend: int


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _free_ports(smoke: ModuleType) -> _Ports:
    return cast("_Ports", smoke.Ports(backend=_free_port(), frontend=_free_port()))


def _assert_ports_released(smoke: ModuleType, ports: _Ports) -> None:
    """Nothing the smoke started still listens; the kernel closes the sockets of a killed process a moment later."""
    smoke.wait_ports_released(ports, 5.0)


@contextmanager
def _serve(routes: dict[str, tuple[int, bytes]]) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, body = routes.get(self.path, (404, b""))
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class TestStaticAssets:
    page = b'<html><script src="/_next/static/chunks/app.js" async></script></html>'

    def test_a_page_whose_asset_is_served_passes(self, smoke: ModuleType) -> None:
        with _serve({"/": (200, self.page), "/_next/static/chunks/app.js": (200, b"//")}) as base:
            smoke.check_static_assets(base)

    def test_a_page_without_built_assets_fails(self, smoke: ModuleType) -> None:
        with (
            _serve({"/": (200, b"<html></html>")}) as base,
            pytest.raises(smoke.SmokeFailure, match="references no /_next/static asset"),
        ):
            smoke.check_static_assets(base)

    def test_an_asset_the_server_cannot_serve_fails(self, smoke: ModuleType) -> None:
        with _serve({"/": (200, self.page)}) as base, pytest.raises(smoke.SmokeFailure, match="chunks/app.js is not served"):
            smoke.check_static_assets(base)

    def test_a_server_that_stopped_answering_fails(self, smoke: ModuleType) -> None:
        with pytest.raises(smoke.SmokeFailure, match="stopped answering"):
            smoke.check_static_assets(f"http://127.0.0.1:{_free_port()}")


_SERVER = """
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

role, port, frontend = sys.argv[1], int(sys.argv[2]), sys.argv[3]
PAGE = b'<script src="/_next/static/app.js"></script>' if frontend != "bare" else b"<html></html>"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if role == "backend" and self.path == "/health":
            self.reply(b"ok")
        elif role == "frontend" and self.path == "/":
            self.reply(PAGE)
        elif role == "frontend" and self.path == "/_next/static/app.js" and frontend == "complete":
            self.reply(b"//")
        else:
            self.send_error(404)

    def reply(self, body):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""

_SHELL = """#!{python}
import os
import signal
import subprocess
import sys
import time

BEHAVIOUR = "{behaviour}"
# Where the shell was started, for the test to read back; next to the executable is the one place a stand-in may write.
with open(os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "cwd.txt"), "w") as record:
    record.write(os.getcwd())
if BEHAVIOUR == "crash":
    print("boom: cannot create the main window", flush=True)
    sys.exit(3)
if BEHAVIOUR == "canonical-path-only" and os.path.realpath(sys.argv[0]) != sys.argv[0]:
    # What Tauri does on macOS: a starting binary behind a symlink leaves the shell without its resources.
    print("Failed to resolve sidecar path: unknown path", flush=True)
    sys.exit(3)

SERVERS = [("backend", {backend})] + ([] if BEHAVIOUR == "backend-only" else [("frontend", {frontend})])
children = [subprocess.Popen([sys.executable, "-c", {server!r}, role, str(port), "{page}"]) for role, port in SERVERS]


def quit_(*_args):
    if BEHAVIOUR != "leaky":
        for child in children:
            child.terminate()
            child.wait()
    sys.exit(0)


signal.signal(signal.SIGTERM, quit_)
while True:
    time.sleep(0.2)
"""


def _stand_in_bundle(
    tmp_path: Path, ports: _Ports, *, behaviour: str = "healthy", page: str = "complete", executable: str = "AppRun"
) -> Path:
    """A bundle whose executable acts like the shell: it starts the backend and the Next server as children."""
    is_app = executable.startswith("Contents/")
    bundle = tmp_path / ("MyrmAgent.app" if is_app else "squashfs-root")
    shell = bundle / executable
    shell.parent.mkdir(parents=True)
    if is_app:
        (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": shell.name}))
    shell.write_text(
        _SHELL.format(
            python=sys.executable,
            behaviour=behaviour,
            backend=ports.backend,
            frontend=ports.frontend,
            server=_SERVER,
            page=page,
        ),
        encoding="utf-8",
    )
    shell.chmod(0o755)
    return bundle


@pytest.fixture
def quick(smoke: ModuleType, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Short timers, and a launch PATH check that does not depend on what the test machine has installed."""
    monkeypatch.setattr(smoke, "STABLE_SEC", 1)
    monkeypatch.setattr(smoke, "POLL_INTERVAL_SEC", 0.1)
    monkeypatch.setattr(smoke, "STOP_TIMEOUT_SEC", 3)
    monkeypatch.setattr(smoke, "shutil", types.SimpleNamespace(which=lambda *_args, **_kwargs: None))
    return smoke


@_POSIX_ONLY
class TestRunAgainstAStandInShell:
    def test_a_shell_that_serves_the_product_and_quits_cleanly_passes(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)

        quick.run(_stand_in_bundle(tmp_path, ports), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_macos_shell_is_started_in_the_filesystem_root_as_under_finder(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)
        bundle = _stand_in_bundle(tmp_path, ports, executable="Contents/MacOS/myrm-agent")

        quick.run(bundle, "darwin", ports=ports, ready_timeout_sec=30)

        assert (bundle / "Contents/MacOS/cwd.txt").read_text(encoding="utf-8") == "/"
        _assert_ports_released(quick, ports)

    def test_a_linux_shell_is_started_in_the_fresh_profile(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)
        bundle = _stand_in_bundle(tmp_path, ports)

        quick.run(bundle, "linux", ports=ports, ready_timeout_sec=30)

        assert Path((bundle / "cwd.txt").read_text(encoding="utf-8")).name == "profile"
        _assert_ports_released(quick, ports)

    def test_children_left_behind_by_a_quitting_shell_are_reported_and_cleaned_up(
        self, quick: ModuleType, tmp_path: Path
    ) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match="left its children running"):
            quick.run(_stand_in_bundle(tmp_path, ports, behaviour="leaky"), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_relative_bundle_path_is_launched(self, quick: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = _free_ports(quick)
        bundle = _stand_in_bundle(tmp_path, ports)
        monkeypatch.chdir(tmp_path)

        quick.run(Path(bundle.name), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_bundle_behind_a_symlink_is_launched_by_its_real_path(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)
        real = tmp_path / "real"
        real.mkdir()
        bundle = _stand_in_bundle(real, ports, behaviour="canonical-path-only")
        alias = tmp_path / "alias"
        alias.symlink_to(real, target_is_directory=True)

        quick.run(alias / bundle.name, "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_shell_that_dies_at_startup_reports_what_it_printed(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match=r"(?s)exited with 3 after .*boom: cannot create the main window"):
            quick.run(_stand_in_bundle(tmp_path, ports, behaviour="crash"), "linux", ports=ports, ready_timeout_sec=30)

    def test_a_shell_whose_next_server_never_comes_up_fails_the_smoke(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match="not ready after 3s: frontend"):
            quick.run(_stand_in_bundle(tmp_path, ports, behaviour="backend-only"), "linux", ports=ports, ready_timeout_sec=3)

        _assert_ports_released(quick, ports)

    def test_a_page_that_references_no_built_assets_fails_the_smoke(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match="references no /_next/static asset"):
            quick.run(_stand_in_bundle(tmp_path, ports, page="bare"), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_page_whose_assets_are_not_served_fails_the_smoke(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match="is not served"):
            quick.run(_stand_in_bundle(tmp_path, ports, page="unserved"), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_shell_serving_without_child_processes_fails_the_smoke(
        self, quick: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ports = _free_ports(quick)
        monkeypatch.setattr(quick, "descendants", lambda *_args: [])

        with pytest.raises(quick.SmokeFailure, match="has no child process"):
            quick.run(_stand_in_bundle(tmp_path, ports), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_port_already_served_by_something_else_refuses_to_run(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)
        with socket.socket() as squatter:
            squatter.bind(("127.0.0.1", ports.backend))
            squatter.listen()

            with pytest.raises(quick.SmokeFailure, match="already served by another process"):
                quick.run(_stand_in_bundle(tmp_path, ports), "linux", ports=ports, ready_timeout_sec=30)

    def test_a_bundle_without_the_shell_lists_what_it_holds(self, quick: ModuleType, tmp_path: Path) -> None:
        (tmp_path / "usr").mkdir()

        with pytest.raises(quick.SmokeFailure, match=r"no shell executable at .*AppRun \(bundle holds: usr\)"):
            quick.run(tmp_path, "linux", ports=_free_ports(quick))


class TestPortsReleased:
    def test_ports_nothing_serves_pass_at_once(self, smoke: ModuleType) -> None:
        smoke.wait_ports_released(_free_ports(smoke), 1.0)

    def test_a_port_still_served_when_the_shell_is_gone_fails(self, smoke: ModuleType) -> None:
        ports = _free_ports(smoke)
        with socket.socket() as survivor:
            survivor.bind(("127.0.0.1", ports.frontend))
            survivor.listen()

            with pytest.raises(smoke.SmokeFailure, match=rf"still serves 127\.0\.0\.1:{ports.frontend}"):
                smoke.wait_ports_released(ports, 1.0)

    def test_a_port_given_back_while_waiting_passes(self, smoke: ModuleType) -> None:
        ports = _free_ports(smoke)
        survivor = socket.socket()
        survivor.bind(("127.0.0.1", ports.backend))
        survivor.listen()
        closer = threading.Timer(0.6, survivor.close)
        closer.start()
        try:
            smoke.wait_ports_released(ports, 10.0)
        finally:
            closer.join()


@_POSIX_ONLY
def test_windows_stops_the_tree_and_then_demands_the_ports_back(
    quick: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ports = _free_ports(quick)
    bundle = _stand_in_bundle(tmp_path, ports, executable="myrm-agent.exe")
    calls: list[str] = []

    def tree_kill(shell: subprocess.Popen[bytes], _platform: str) -> None:
        # Stands in for `taskkill /T /F`, which a POSIX test host does not have.
        calls.append("kill_tree")
        for child in quick.descendants(quick.process_table(), shell.pid):
            os.kill(child.pid, signal.SIGKILL)
        shell.kill()
        shell.wait()

    released = quick.wait_ports_released

    def wait_released(*args: object) -> None:
        calls.append("wait_ports_released")
        released(*args)

    monkeypatch.setattr(quick, "kill_tree", tree_kill)
    monkeypatch.setattr(quick, "wait_ports_released", wait_released)

    quick.run(bundle, "win32", ports=ports, ready_timeout_sec=30)

    assert calls[:2] == ["kill_tree", "wait_ports_released"]


def test_a_launch_path_that_still_finds_node_refuses_to_run(
    smoke: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(smoke, "shutil", types.SimpleNamespace(which=lambda *_args, **_kwargs: "/usr/bin/node"))

    with pytest.raises(smoke.SmokeFailure, match=r"launch PATH still finds a Node.js at /usr/bin/node"):
        smoke.run(tmp_path, "linux")
