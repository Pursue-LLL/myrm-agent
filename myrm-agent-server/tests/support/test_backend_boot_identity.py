"""Backend boot identity: separates a hot-reloaded dev stack from a broken turn."""

from __future__ import annotations

import subprocess

import pytest

from tests.support import chrome_mcp_e2e as support


class _Completed:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def _fake_run(outputs: dict[str, str]):
    def run(command: list[str], **_kwargs: object) -> _Completed:
        return _Completed(outputs.get(command[0], ""))

    return run


def test_identity_combines_pid_and_process_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        support.subprocess,
        "run",
        _fake_run({"lsof": "12345\n", "ps": "Sat Oct 24 15:00:39 2026\n"}),
    )

    identity = support.backend_boot_identity("http://127.0.0.1:8080")

    assert identity == "12345:Sat Oct 24 15:00:39 2026"


def test_a_restart_changes_the_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        support.subprocess,
        "run",
        _fake_run({"lsof": "12345\n", "ps": "Sat Oct 24 15:00:39 2026\n"}),
    )
    before = support.backend_boot_identity("http://127.0.0.1:8080")

    monkeypatch.setattr(
        support.subprocess,
        "run",
        _fake_run({"lsof": "22222\n", "ps": "Sat Oct 24 15:07:02 2026\n"}),
    )
    after = support.backend_boot_identity("http://127.0.0.1:8080")

    assert before and after and before != after


@pytest.mark.parametrize(
    "outputs",
    [
        {"lsof": ""},
        {"lsof": "not-a-pid\n"},
        {"lsof": "12345\n", "ps": ""},
    ],
)
def test_unknown_identity_is_empty_instead_of_inventing_a_restart(
    monkeypatch: pytest.MonkeyPatch, outputs: dict[str, str]
) -> None:
    monkeypatch.setattr(support.subprocess, "run", _fake_run(outputs))

    assert support.backend_boot_identity("http://127.0.0.1:8080") == ""


def test_missing_port_is_empty() -> None:
    assert support.backend_boot_identity("not-a-url") == ""


def test_probe_failure_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="lsof", timeout=5)

    monkeypatch.setattr(support.subprocess, "run", boom)

    assert support.backend_boot_identity("http://127.0.0.1:8080") == ""
