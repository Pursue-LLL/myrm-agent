"""The channel check of the packaged-shell launch smoke (`scripts/ci/desktop-release/smoke_channels.py`).

The channel registry loads its providers by a computed module name, so a bundle can start, answer `/health` and serve
its data while the backend refuses most channel types. Only a request that creates a channel shows it. These tests
show the check against a fake backend that answers the way the real one does: created, refused, database locked.
The check's pins to the channel registry and to the bundle inventory are in `test_desktop_sidecar_modules.py`.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import ModuleType
from typing import cast

import pytest

from tests.support.desktop_release import smoke_channels_module

_API = "/api/v1/channels/manage"


@dataclass
class _Backend:
    """What a fake backend answers on the channel API, and what it was asked."""

    refuse: dict[str, tuple[int, str]] = field(default_factory=dict)
    unavailable: tuple[str, ...] = ()
    locked_answers: int = 0
    delete_status: int = 204
    status_code: int = 200
    attempts: list[str] = field(default_factory=list)
    bodies: list[dict[str, str]] = field(default_factory=list)
    created_ids: list[str] = field(default_factory=list)
    deleted_ids: list[str] = field(default_factory=list)
    content_types: set[str] = field(default_factory=set)


def _handler(backend: _Backend) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: object | None = None) -> None:
            body = b"" if payload is None else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != f"{_API}/instances":
                self._send(404)
                return
            body = cast("dict[str, str]", json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            backend.content_types.add(self.headers.get("Content-Type", ""))
            channel_type = body["channelType"]
            backend.attempts.append(channel_type)
            if backend.locked_answers > 0:
                backend.locked_answers -= 1
                self._send(503, {"detail": "database is locked"})
            elif channel_type in backend.refuse:
                status, detail = backend.refuse[channel_type]
                self._send(status, {"detail": detail})
            else:
                backend.bodies.append(body)
                instance_id = f"i{len(backend.created_ids)}"
                backend.created_ids.append(instance_id)
                self._send(
                    201,
                    {
                        "instanceId": instance_id,
                        "channelType": channel_type,
                        "channelName": f"{channel_type}_{instance_id}",
                        "displayName": "",
                        "status": "idle",
                    },
                )

        def do_DELETE(self) -> None:
            prefix = f"{_API}/instances/"
            if not self.path.startswith(prefix):
                self._send(404)
                return
            backend.deleted_ids.append(self.path.removeprefix(prefix))
            self._send(backend.delete_status)

        def do_GET(self) -> None:
            if self.path != f"{_API}/status":
                self._send(404)
                return
            entries = [{"name": "webhook", "status": "disabled", "channelType": "webhook", "connected": False, "issues": []}]
            entries += [
                {"name": name, "status": "unavailable", "channelType": name, "connected": False, "issues": []}
                for name in backend.unavailable
            ]
            self._send(backend.status_code, entries)

        def log_message(self, *_args: object) -> None:
            pass

    return Handler


@contextmanager
def _serve(backend: _Backend) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(backend))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def channels(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = smoke_channels_module()
    monkeypatch.setattr(module, "LOCKED_RETRY_SEC", 2.0)
    monkeypatch.setattr(module, "RETRY_INTERVAL_SEC", 0.02)
    return module


def _designed(channels: ModuleType) -> _Backend:
    """A backend that behaves like the desktop bundle: every type is created except the one whose SDK is left out."""
    return _Backend(refuse={"discord": (400, "Channel type 'discord' unavailable (missing SDK?)")}, unavailable=("discord",))


def test_every_channel_type_is_created_once_and_removed_again(channels: ModuleType) -> None:
    backend = _designed(channels)

    with _serve(backend) as base:
        check = channels.create_every_channel(base)

    assert check.problems == ()
    assert check.created == tuple(name for name in channels.CHANNEL_TYPES if name != "discord")
    assert check.unavailable == ("discord",)
    assert check.leftovers == ()
    assert backend.attempts == list(channels.CHANNEL_TYPES)
    assert backend.bodies == [{"channelType": name} for name in check.created]
    assert backend.content_types == {"application/json"}
    assert sorted(backend.deleted_ids) == sorted(backend.created_ids)


def test_a_channel_type_the_backend_refuses_is_reported_with_its_answer_and_the_rest_is_still_checked(
    channels: ModuleType,
) -> None:
    detail = "Channel type 'telegram' unavailable (missing SDK?)"
    backend = _designed(channels)
    backend.refuse.update({"telegram": (400, detail), "slack": (500, "boom")})

    with _serve(backend) as base:
        check = channels.create_every_channel(base)

    assert [problem.split(":")[0] for problem in check.problems] == [
        name for name in channels.CHANNEL_TYPES if name in {"telegram", "slack"}
    ]
    assert any("telegram" in problem and "HTTP 400" in problem and detail in problem for problem in check.problems)
    assert any("slack" in problem and "HTTP 500" in problem and "boom" in problem for problem in check.problems)
    assert "telegram" not in check.created and "slack" not in check.created
    assert len(check.created) == len(channels.CHANNEL_TYPES) - 3
    assert sorted(backend.deleted_ids) == sorted(backend.created_ids)


def test_the_type_whose_sdk_is_left_out_must_be_listed_as_unavailable_when_it_is_refused(channels: ModuleType) -> None:
    backend = _designed(channels)
    backend.unavailable = ()

    with _serve(backend) as base:
        check = channels.create_every_channel(base)

    assert check.unavailable == ()
    assert [problem.split(":")[0] for problem in check.problems] == ["discord"]
    assert "unavailable" in check.problems[0]


def test_a_status_that_does_not_answer_lists_nothing_as_unavailable(channels: ModuleType) -> None:
    backend = _designed(channels)
    backend.status_code = 500

    with _serve(backend) as base:
        check = channels.create_every_channel(base)

    assert [problem.split(":")[0] for problem in check.problems] == ["discord"]


def test_the_type_whose_sdk_is_left_out_may_be_created_when_the_bundle_ships_it_after_all(channels: ModuleType) -> None:
    backend = _Backend()

    with _serve(backend) as base:
        check = channels.create_every_channel(base)

    assert check.problems == ()
    assert check.created == tuple(channels.CHANNEL_TYPES)
    assert check.unavailable == ()


def test_a_type_that_is_not_left_out_is_a_problem_even_when_the_backend_lists_it_as_unavailable(channels: ModuleType) -> None:
    # `feishu` is listed as unavailable whenever its SDK cannot be imported: the bundle must hold that SDK.
    backend = _designed(channels)
    backend.refuse["feishu"] = (400, "Channel type 'feishu' unavailable (missing SDK?)")
    backend.unavailable = ("discord", "feishu")

    with _serve(backend) as base:
        check = channels.create_every_channel(base)

    assert [problem.split(":")[0] for problem in check.problems] == ["feishu"]
    assert check.unavailable == ("discord",)


def test_a_locked_database_is_asked_again_instead_of_failing_the_type(channels: ModuleType) -> None:
    # The backend's own start-up work holds the SQLite lock for a moment after it answers `/health`.
    backend = _designed(channels)
    backend.locked_answers = 3

    with _serve(backend) as base:
        check = channels.create_every_channel(base)

    assert check.problems == ()
    assert backend.attempts[:4] == [channels.CHANNEL_TYPES[0]] * 4
    assert len(check.created) == len(channels.CHANNEL_TYPES) - 1


def test_a_database_that_stays_locked_is_reported_for_every_type_without_waiting_for_each_one(
    channels: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(channels, "LOCKED_RETRY_SEC", 0.3)
    backend = _designed(channels)
    backend.locked_answers = 10**6

    started = time.monotonic()
    with _serve(backend) as base:
        check = channels.create_every_channel(base)
    elapsed = time.monotonic() - started

    assert len(check.problems) == len(channels.CHANNEL_TYPES)
    assert all("HTTP 503" in problem for problem in check.problems)
    assert elapsed < 5.0, "the window for a locked database is shared by all types, not granted to each"


def test_a_backend_that_does_not_answer_ends_the_check_with_one_problem(channels: ModuleType) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    check = channels.create_every_channel(f"http://127.0.0.1:{port}")

    assert len(check.problems) == 1
    assert check.problems[0].startswith(f"{channels.CHANNEL_TYPES[0]}:")
    assert "no answer" in check.problems[0]
    assert check.created == ()


def test_instances_that_cannot_be_removed_are_reported_but_are_no_failure(channels: ModuleType) -> None:
    backend = _designed(channels)
    backend.delete_status = 500

    with _serve(backend) as base:
        check = channels.create_every_channel(base)

    assert check.problems == ()
    assert len(check.leftovers) == len(check.created)
    assert all(name in leftover for name, leftover in zip(check.created, check.leftovers, strict=True))
