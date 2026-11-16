"""``require_memory_labs`` lets a Command Center node run only on a runtime that has Memory Labs on in backend and frontend."""

from __future__ import annotations

import pytest

from tests.support import memory_labs

_API_URL = "http://127.0.0.1:18080"
_LABS_PATH = f"/api/v1/memory{memory_labs.LABS_ONLY_ROUTE}"
_NODE = "tests/e2e/test_memory_command_center_chrome_e2e.py::test_memory_economics_panel_chrome_e2e"
_COMMAND = f"MYRM_MEMORY_LABS=1 NEXT_PUBLIC_MEMORY_LABS=1 ./myrm-dev test -m chrome_e2e myrm-agent/myrm-agent-server/{_NODE}"
_BACKEND_MISSING = "the backend does not mount the Labs routes"
_FRONTEND_MISSING = "the frontend does not render the Labs panels"


def _runtime(monkeypatch: pytest.MonkeyPatch, *, backend: bool, frontend: bool, running: str = _NODE) -> None:
    """A runtime whose backend lists the Labs route (or not) and whose frontend switch is set (or not), running ``running``."""
    paths: dict[str, object] = {"/api/v1/health": {"get": {}}}
    if backend:
        paths[_LABS_PATH] = {"get": {}, "post": {}}
    monkeypatch.setattr(memory_labs, "http_json", lambda *_args, **_kwargs: {"paths": paths})
    if frontend:
        monkeypatch.setenv("NEXT_PUBLIC_MEMORY_LABS", "1")
    else:
        monkeypatch.delenv("NEXT_PUBLIC_MEMORY_LABS", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", f"{running} (call)")


def _skip_reason() -> str:
    with pytest.raises(pytest.skip.Exception) as skipped:
        memory_labs.require_memory_labs(_API_URL)
    return str(skipped.value)


@pytest.mark.parametrize(
    ("backend", "frontend", "named", "not_named"),
    [
        (False, False, (_BACKEND_MISSING, _FRONTEND_MISSING), ()),
        (True, False, (_FRONTEND_MISSING,), (_BACKEND_MISSING,)),
        (False, True, (_BACKEND_MISSING,), (_FRONTEND_MISSING,)),
    ],
    ids=["neither", "backend-only", "frontend-only"],
)
def test_a_runtime_missing_a_switch_skips_naming_only_what_is_missing_and_the_command_for_a_complete_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend: bool,
    frontend: bool,
    named: tuple[str, ...],
    not_named: tuple[str, ...],
) -> None:
    _runtime(monkeypatch, backend=backend, frontend=frontend)

    reason = _skip_reason()

    assert all(part in reason for part in named), reason
    assert not any(part in reason for part in not_named), reason
    assert reason.endswith(f"Run: {_COMMAND}"), reason
    assert f"E2E_MEMORY_LABS_OFF: {reason}" in capsys.readouterr().out


@pytest.mark.parametrize(
    "running", [_NODE, f"myrm-agent/myrm-agent-server/{_NODE}"], ids=["server-relative", "monorepo-relative"]
)
def test_the_command_names_the_node_once_whichever_root_pytest_reports_it_from(
    monkeypatch: pytest.MonkeyPatch, running: str
) -> None:
    _runtime(monkeypatch, backend=False, frontend=False, running=running)

    assert _skip_reason().endswith(f"Run: {_COMMAND}")


def test_a_runtime_with_both_switches_runs_the_node(monkeypatch: pytest.MonkeyPatch) -> None:
    _runtime(monkeypatch, backend=True, frontend=True)

    memory_labs.require_memory_labs(_API_URL)


def test_a_backend_that_serves_no_route_table_fails_instead_of_skipping(monkeypatch: pytest.MonkeyPatch) -> None:
    _runtime(monkeypatch, backend=True, frontend=True)
    monkeypatch.setattr(memory_labs, "http_json", lambda *_args, **_kwargs: {"detail": "Not Found"})

    with pytest.raises(RuntimeError, match="carries no route table"):
        memory_labs.require_memory_labs(_API_URL)
