"""The packaged-shell launch smoke (`scripts/ci/desktop-release/smoke_launch_shell.py`) against stand-in bundles.

The smoke demands that the shell brings up the backend, which must serve the data it ships, and the bundled Next.js
server, keeps them up and takes them down when asked to quit. A smoke that cannot fail proves nothing, so each way the
product can misbehave is reproduced here by a stand-in bundle whose executable acts like the shell, or misacts on
purpose, and must be reported.
"""

from __future__ import annotations

import os
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
from typing import cast

import pytest

from tests.support.desktop_release import smoke_launch_shell_module
from tests.support.stand_in_shell_bundle import Ports, stand_in_bundle

_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="the smoke reads the POSIX process table and signals")


@pytest.fixture(scope="module")
def smoke() -> ModuleType:
    return smoke_launch_shell_module()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _free_ports(smoke: ModuleType) -> Ports:
    return cast("Ports", smoke.Ports(backend=_free_port(), frontend=_free_port()))


def _assert_ports_released(smoke: ModuleType, ports: Ports) -> None:
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


class TestBundledData:
    @pytest.mark.parametrize(
        ("body", "list_key", "expected"),
        [
            (b'{"skills": [{"id": "a"}, {"id": "b"}], "total": 2}', "skills", 2),
            (b'{"success": true, "data": [{"id": "a"}]}', None, 1),
            (b'{"success": true, "data": {"entries": [1, 2, 3], "total": 3}}', "entries", 3),
            (b'{"skills": []}', "skills", 0),
            (b'{"success": true, "data": []}', None, 0),
            (b'{"success": true, "data": {"entries": []}}', "entries", 0),
            (b'{"total": 5}', "skills", 0),
            (b'{"skills": {"a": 1}}', "skills", 0),
            (b'{"success": true, "data": null}', None, 0),
            (b"[1, 2]", None, 2),
            (b"not json", "skills", 0),
            (b"", None, 0),
        ],
    )
    def test_a_list_is_counted_in_either_response_shape(
        self, smoke: ModuleType, body: bytes, list_key: str | None, expected: int
    ) -> None:
        assert smoke.count_listed(body, list_key) == expected

    def test_every_list_the_backend_builds_from_bundled_data_is_asserted(self, smoke: ModuleType) -> None:
        assert [data.label for data in smoke.BUNDLED_DATA] == [
            "skills",
            "agent templates",
            "integration catalog",
            "search providers",
        ]

    def test_only_the_lists_that_are_empty_or_fail_are_reported(self, smoke: ModuleType) -> None:
        routes = {
            "/api/v1/skills/": (200, b'{"skills": [{"id": "s"}]}'),
            "/api/v1/agents/templates": (200, b'{"data": []}'),
            "/api/v1/integrations/catalog": (500, b"boom"),
            "/api/v1/integrations/search/providers": (200, b'{"data": {"providers": [{"slug": "p"}]}}'),
        }
        with _serve(routes) as base:
            unserved = smoke.unserved_data(base, smoke.BUNDLED_DATA)

        assert [data.label for data in unserved] == ["agent templates", "integration catalog"]

    def test_a_backend_that_does_not_answer_serves_nothing(self, smoke: ModuleType) -> None:
        unserved = smoke.unserved_data(f"http://127.0.0.1:{_free_port()}", smoke.BUNDLED_DATA)

        assert unserved == list(smoke.BUNDLED_DATA)


@pytest.fixture
def quick(smoke: ModuleType, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Short timers, and a launch PATH check that does not depend on what the test machine has installed."""
    monkeypatch.setattr(smoke, "STABLE_SEC", 1)
    monkeypatch.setattr(smoke, "DATA_TIMEOUT_SEC", 4)
    monkeypatch.setattr(smoke, "POLL_INTERVAL_SEC", 0.1)
    monkeypatch.setattr(smoke, "STOP_TIMEOUT_SEC", 3)
    monkeypatch.setattr(smoke, "shutil", types.SimpleNamespace(which=lambda *_args, **_kwargs: None))
    return smoke


@_POSIX_ONLY
class TestRunAgainstAStandInShell:
    def test_a_shell_that_serves_the_product_and_quits_cleanly_passes(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)

        quick.run(stand_in_bundle(tmp_path, ports), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_macos_shell_is_started_in_the_filesystem_root_as_under_finder(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)
        bundle = stand_in_bundle(tmp_path, ports, executable="Contents/MacOS/myrm-agent")

        quick.run(bundle, "darwin", ports=ports, ready_timeout_sec=30)

        assert (bundle / "Contents/MacOS/cwd.txt").read_text(encoding="utf-8") == "/"
        _assert_ports_released(quick, ports)

    def test_a_linux_shell_is_started_in_the_fresh_profile(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)
        bundle = stand_in_bundle(tmp_path, ports)

        quick.run(bundle, "linux", ports=ports, ready_timeout_sec=30)

        assert Path((bundle / "cwd.txt").read_text(encoding="utf-8")).name == "profile"
        _assert_ports_released(quick, ports)

    def test_children_left_behind_by_a_quitting_shell_are_reported_and_cleaned_up(
        self, quick: ModuleType, tmp_path: Path
    ) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match="left its children running"):
            quick.run(stand_in_bundle(tmp_path, ports, behaviour="leaky"), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_relative_bundle_path_is_launched(self, quick: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        ports = _free_ports(quick)
        bundle = stand_in_bundle(tmp_path, ports)
        monkeypatch.chdir(tmp_path)

        quick.run(Path(bundle.name), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_bundle_behind_a_symlink_is_launched_by_its_real_path(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)
        real = tmp_path / "real"
        real.mkdir()
        bundle = stand_in_bundle(real, ports, behaviour="canonical-path-only")
        alias = tmp_path / "alias"
        alias.symlink_to(real, target_is_directory=True)

        quick.run(alias / bundle.name, "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_shell_that_dies_at_startup_reports_what_it_printed(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match=r"(?s)exited with 3 after .*boom: cannot create the main window"):
            quick.run(stand_in_bundle(tmp_path, ports, behaviour="crash"), "linux", ports=ports, ready_timeout_sec=30)

    def test_a_shell_whose_next_server_never_comes_up_fails_the_smoke(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match="not ready after 3s: frontend"):
            quick.run(stand_in_bundle(tmp_path, ports, behaviour="backend-only"), "linux", ports=ports, ready_timeout_sec=3)

        _assert_ports_released(quick, ports)

    def test_a_page_that_references_no_built_assets_fails_the_smoke(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match="references no /_next/static asset"):
            quick.run(stand_in_bundle(tmp_path, ports, page="bare"), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_page_whose_assets_are_not_served_fails_the_smoke(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match="is not served"):
            quick.run(stand_in_bundle(tmp_path, ports, page="unserved"), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_backend_without_its_skills_fails_the_smoke(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match=r"no non-empty list from the backend 4s after it became ready: skills"):
            quick.run(stand_in_bundle(tmp_path, ports, data="no-skills"), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_data_that_appears_after_the_backend_answers_passes(self, quick: ModuleType, tmp_path: Path) -> None:
        # The stand-in serves an empty skills list for its first 1.5 s; the smoke asks again instead of failing on it.
        ports = _free_ports(quick)

        quick.run(stand_in_bundle(tmp_path, ports, data="late-skills"), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_data_endpoints_that_answer_with_an_error_fail_the_smoke_with_every_list_named(
        self, quick: ModuleType, tmp_path: Path
    ) -> None:
        ports = _free_ports(quick)

        with pytest.raises(quick.SmokeFailure, match=r"skills .*agent templates .*integration catalog .*search providers"):
            quick.run(stand_in_bundle(tmp_path, ports, data="broken"), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_shell_serving_without_child_processes_fails_the_smoke(
        self, quick: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ports = _free_ports(quick)
        monkeypatch.setattr(quick, "descendants", lambda *_args: [])

        with pytest.raises(quick.SmokeFailure, match="has no child process"):
            quick.run(stand_in_bundle(tmp_path, ports), "linux", ports=ports, ready_timeout_sec=30)

        _assert_ports_released(quick, ports)

    def test_a_port_already_served_by_something_else_refuses_to_run(self, quick: ModuleType, tmp_path: Path) -> None:
        ports = _free_ports(quick)
        with socket.socket() as squatter:
            squatter.bind(("127.0.0.1", ports.backend))
            squatter.listen()

            with pytest.raises(quick.SmokeFailure, match="already served by another process"):
                quick.run(stand_in_bundle(tmp_path, ports), "linux", ports=ports, ready_timeout_sec=30)

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
    bundle = stand_in_bundle(tmp_path, ports, executable="myrm-agent.exe")
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
